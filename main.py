import os
import json
import urllib.request
import tarfile
import decky

def _decky_user_home():
    user = os.environ.get("DECKY_USER") or os.environ.get("SUDO_USER") or "armada"
    home = os.environ.get("HOME")
    if home and home not in ("/root", ""):
        return home
    try:
        import pwd
        return pwd.getpwnam(user).pw_dir
    except Exception:
        return f"/home/{user}"

USER_HOME = _decky_user_home()
LSFG_DIR = os.path.join(USER_HOME, ".config/lsfg-vk")
GAMES_DIR = os.path.join(LSFG_DIR, "games")
DEFAULT_CONF = os.path.join(LSFG_DIR, "default.json")
USER_LIB_DIR = os.path.join(USER_HOME, ".local/lib/lsfg-vk")
OVERLAY_UPPER = os.path.join(USER_HOME, ".local/share/lsfg-vk/pv-upper")
OVERLAY_WORK = os.path.join(USER_HOME, ".local/share/lsfg-vk/pv-work")
ARM64_SO = os.path.join(USER_LIB_DIR, "liblsfg-vk-arm64.so")
ARM64_WRAPPER = os.path.join(LSFG_DIR, "bin/lsfg")
ARM64_MANIFEST = os.path.join(USER_HOME, ".local/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation_arm64.json")
PV_ARM64_MANIFEST = os.path.join(OVERLAY_UPPER, "pressure-vessel/overrides/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation_arm64.json")
FEX_CONFIG = os.path.join(USER_HOME, ".config/fex-emu/Config.json")
DOWNLOAD_URL = "https://github.com/seilent/lsfg-vk/releases/download/latest/lsfg-vk-arm64.tar.gz"
DLL_CANDIDATES = [
    os.path.join(USER_HOME, ".local/share/Steam/steamapps/common/Lossless Scaling/Lossless.dll"),
    os.path.join(USER_HOME, ".steam/steam/steamapps/common/Lossless Scaling/Lossless.dll"),
    os.path.join(USER_HOME, ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/Lossless Scaling/Lossless.dll"),
]
LOSSLESS_DLL_PATHS = DLL_CANDIDATES

DEFAULT_SETTINGS = {
    "multiplier": 2,
    "fps_limit": 60,
    "flow_scale": 0.8,
    "performance_mode": 1,
}


def _thunks_enabled():
    if not os.path.exists(FEX_CONFIG):
        return False
    try:
        with open(FEX_CONFIG, "r") as f:
            cfg = json.load(f)
        return cfg.get("ThunksDB", {}).get("Vulkan") == 1
    except Exception:
        return False


def _system_installed():
    return (
        os.path.exists(ARM64_SO)
        and os.path.exists(ARM64_MANIFEST)
        and os.path.exists(ARM64_WRAPPER)
    )


def _layer_deployed():
    return os.path.exists(ARM64_SO) and os.path.exists(ARM64_MANIFEST)


def _dll_detected():
    return any(os.path.isfile(p) for p in LOSSLESS_DLL_PATHS)


def _enable_thunks():
    os.makedirs(os.path.dirname(FEX_CONFIG), exist_ok=True)
    if os.path.exists(FEX_CONFIG):
        with open(FEX_CONFIG, "r") as f:
            cfg = json.load(f)
    else:
        cfg = {}
    cfg.setdefault("ThunksDB", {})["Vulkan"] = 1
    with open(FEX_CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)


def _load_settings(path):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _load_game_settings(app_id):
    if not app_id or app_id == "0" or app_id == "None":
        settings = _load_settings(DEFAULT_CONF)
        return settings if settings else dict(DEFAULT_SETTINGS)
    path = os.path.join(GAMES_DIR, f"{app_id}.json")
    settings = _load_settings(path)
    if settings is not None:
        return settings
    # Auto-create from defaults on first access
    settings = _load_settings(DEFAULT_CONF)
    if settings is None:
        settings = dict(DEFAULT_SETTINGS)
    _save_json(path, settings)
    return settings


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


class Plugin:

    async def get_status(self):
        return {
            "system_installed": _system_installed(),
            "layer_deployed": _layer_deployed(),
            "dll_detected": _dll_detected(),
        }

    async def get_game_settings(self, app_id: str):
        return _load_game_settings(app_id)

    async def list_game_profiles(self):
        profiles = []
        if os.path.isdir(GAMES_DIR):
            for f in os.listdir(GAMES_DIR):
                if f.endswith(".json"):
                    profiles.append(f.replace(".json", ""))
        return profiles

    async def save_game_settings(self, app_id: str, settings: str):
        path = os.path.join(GAMES_DIR, f"{app_id}.json")
        _save_json(path, json.loads(settings))
        return True

    async def delete_game_profile(self, app_id: str):
        path = os.path.join(GAMES_DIR, f"{app_id}.json")
        if os.path.exists(path):
            os.remove(path)
        return True

    async def get_default_settings(self):
        cfg = _load_settings(DEFAULT_CONF)
        if cfg is not None:
            return cfg
        return dict(DEFAULT_SETTINGS)

    async def save_default_settings(self, settings: str):
        _save_json(DEFAULT_CONF, json.loads(settings))
        return True

    async def download_layer(self):
        """Download ARM64 .so from GitHub. Returns progress dict or error."""
        import ssl
        lib_dir = os.path.join(LSFG_DIR, "lib")
        os.makedirs(lib_dir, exist_ok=True)
        tar_path = os.path.join(lib_dir, "lsfg-vk-arm64.tar.gz")

        try:
            # SSL workaround for devices with invalid clock/date
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(DOWNLOAD_URL)
            with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
                with open(tar_path, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)

            # Extract .so (handle archives with or without ./ prefix)
            extracted = os.path.join(lib_dir, "liblsfg-vk-arm64.so")
            with tarfile.open(tar_path, "r:gz") as tar:
                for m in tar.getmembers():
                    if os.path.basename(m.name) == "liblsfg-vk-arm64.so":
                        tar.extract(m, path=lib_dir)
                        src = os.path.join(lib_dir, m.name)
                        if src != extracted:
                            os.rename(src, extracted)
                        break
                else:
                    raise FileNotFoundError("liblsfg-vk-arm64.so not found in archive")

            os.remove(tar_path)
            decky.logger.info(f"Downloaded ARM64 .so ({os.path.getsize(extracted)} bytes)")
            return {"success": True, "size": os.path.getsize(extracted)}
        except Exception as e:
            if os.path.exists(tar_path):
                os.remove(tar_path)
            decky.logger.error(f"download_layer failed: {e}")
            return {"success": False, "error": str(e)}

    async def install_runtime(self):
        """Run the Armada/Fedora installer immediately.

        Armada updates may cause Decky/Steam to launch plugin methods with a
        polluted dynamic-library environment. In that state, invoking plain
        `bash` can load the wrong libreadline and fail with errors such as:

            bash: symbol lookup error: bash: undefined symbol: rl_trim_arg_from_keyseq

        Use the system shell by absolute path and a minimal environment so the
        installer runs like it does from a clean SSH session.
        """
        import subprocess
        import pwd

        plugin_dir = decky.DECKY_PLUGIN_DIR
        installer = os.path.join(plugin_dir, "install-armada.sh")
        if not os.path.exists(installer):
            decky.logger.error(f"install-armada.sh not found at {installer}")
            return False

        install_user = os.environ.get("DECKY_USER") or os.environ.get("SUDO_USER") or "armada"
        try:
            install_home = pwd.getpwnam(install_user).pw_dir
        except Exception:
            install_home = USER_HOME

        env = {
            "HOME": install_home,
            "USER": install_user,
            "LOGNAME": install_user,
            "SUDO_USER": install_user,
            "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        }

        try:
            result = subprocess.run(
                ["/usr/bin/bash", installer],
                cwd=plugin_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.stdout:
                decky.logger.info(result.stdout)
            if result.stderr:
                decky.logger.warning(result.stderr)
            if result.returncode != 0:
                decky.logger.error(f"install-armada.sh failed with exit code {result.returncode}")
                return False
            return True
        except Exception as e:
            decky.logger.error(f"install_runtime failed: {e}")
            return False

    async def reinstall_layer(self):
        """Re-run the Armada installer."""
        return await self.install_runtime()

    async def uninstall_lsfg(self):
        """Remove all LSFG-VK artifacts and services. Reboot required."""
        import shutil
        try:
            # Remove overlay and work dirs
            for d in [OVERLAY_UPPER, OVERLAY_WORK]:
                if os.path.exists(d):
                    shutil.rmtree(d)

            # Unmount overlay
            os.system("umount -l /usr/lib 2>/dev/null || true")

            # Remove systemd services
            svc_dir = "/etc/systemd/system"
            wants_dir = "/etc/systemd/system/multi-user.target.wants"
            for svc in ["lsfg-vk-install.service", "lsfg-vk-overlay.service"]:
                for p in [os.path.join(svc_dir, svc), os.path.join(wants_dir, svc)]:
                    if os.path.lexists(p):
                        os.remove(p)

            # Remove XDG manifest
            xdg_manifest = ARM64_MANIFEST
            if os.path.exists(xdg_manifest):
                os.remove(xdg_manifest)

            # Remove wrapper symlink
            home_lsfg = os.path.join(USER_HOME, "lsfg")
            if os.path.lexists(home_lsfg):
                os.remove(home_lsfg)

            # Remove lsfg-vk config dir (lib, bin, configs)
            if os.path.exists(LSFG_DIR):
                shutil.rmtree(LSFG_DIR)

            # Disable FEX Vulkan thunks
            if os.path.exists(FEX_CONFIG):
                with open(FEX_CONFIG, "r") as f:
                    cfg = json.load(f)
                if "ThunksDB" in cfg and "Vulkan" in cfg["ThunksDB"]:
                    del cfg["ThunksDB"]["Vulkan"]
                    if not cfg["ThunksDB"]:
                        del cfg["ThunksDB"]
                    with open(FEX_CONFIG, "w") as f:
                        json.dump(cfg, f, indent=2)

            decky.logger.info("LSFG-VK uninstalled. Reboot required.")
            return True
        except Exception as e:
            decky.logger.error(f"uninstall_lsfg failed: {e}")
            return False

    async def _main(self):
        os.makedirs(LSFG_DIR, exist_ok=True)
        os.makedirs(GAMES_DIR, exist_ok=True)

    async def _unload(self):
        pass
