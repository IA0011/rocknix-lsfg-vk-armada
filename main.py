import os
import json
import shutil
import decky

LSFG_DIR = "/storage/.config/lsfg-vk"
GAMES_DIR = os.path.join(LSFG_DIR, "games")
DEFAULT_CONF = os.path.join(LSFG_DIR, "default.json")

# ARM64 native paths (all under writable /storage)
ARM64_SO = os.path.join(LSFG_DIR, "lib/liblsfg-vk-arm64.so")
ARM64_MANIFEST = os.path.join(LSFG_DIR, "manifests/VkLayer_LS_frame_generation_arm64.json")
ARM64_WRAPPER = os.path.join(LSFG_DIR, "bin/lsfg")

# FEX config
FEX_CONFIG = "/storage/.config/fex-emu/Config.json"

# Lossless Scaling DLL
LOSSLESS_DLL_PATH = "/storage/games-internal/roms/steam/steamapps/common/Lossless Scaling/Lossless.dll"
LOSSLESS_DLL_SYMLINK = "/storage/.local/share/Steam/steamapps/common/Lossless Scaling/Lossless.dll"

DEFAULT_SETTINGS = {
    "multiplier": 2,
    "fps_limit": 30,
    "flow_scale": 0.3,
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
    """All components present for ARM64 frame gen to work."""
    return (
        os.path.exists(ARM64_SO)
        and os.path.exists(ARM64_MANIFEST)
        and os.path.exists(ARM64_WRAPPER)
    )


def _layer_deployed():
    """Layer .so and manifest both exist."""
    return os.path.exists(ARM64_SO) and os.path.exists(ARM64_MANIFEST)


def _dll_detected():
    return os.path.exists(LOSSLESS_DLL_PATH) or os.path.exists(LOSSLESS_DLL_SYMLINK)


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
    path = os.path.join(GAMES_DIR, f"{app_id}.json")
    settings = _load_settings(path)
    if settings is not None:
        return settings
    settings = _load_settings(DEFAULT_CONF)
    if settings is not None:
        return settings
    return dict(DEFAULT_SETTINGS)


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

    async def save_game_settings(self, app_id: str, settings: str):
        path = os.path.join(GAMES_DIR, f"{app_id}.json")
        _save_json(path, json.loads(settings))
        return True

    async def get_default_settings(self):
        cfg = _load_settings(DEFAULT_CONF)
        if cfg is not None:
            return cfg
        return dict(DEFAULT_SETTINGS)

    async def save_default_settings(self, settings: str):
        _save_json(DEFAULT_CONF, json.loads(settings))
        return True

    async def reinstall_layer(self):
        """Re-run deploy: copy wrapper, manifest, enable thunks."""
        try:
            os.makedirs(os.path.join(LSFG_DIR, "bin"), exist_ok=True)
            os.makedirs(os.path.join(LSFG_DIR, "manifests"), exist_ok=True)

            # Copy wrapper
            wrapper_src = os.path.join(decky.DECKY_PLUGIN_DIR, "defaults/lsfg")
            shutil.copy2(wrapper_src, ARM64_WRAPPER)
            os.chmod(ARM64_WRAPPER, 0o755)
            home_link = os.path.expanduser("~/lsfg")
            if os.path.lexists(home_link):
                os.remove(home_link)
            os.symlink(ARM64_WRAPPER, home_link)

            # Copy manifest
            manifest_src = os.path.join(decky.DECKY_PLUGIN_DIR, "defaults/VkLayer_LS_frame_generation.json")
            shutil.copy2(manifest_src, ARM64_MANIFEST)

            # Enable thunks
            _enable_thunks()

            # DLL symlink
            dll_dir = os.path.dirname(LOSSLESS_DLL_SYMLINK)
            os.makedirs(dll_dir, exist_ok=True)
            if os.path.exists(LOSSLESS_DLL_PATH) and not os.path.exists(LOSSLESS_DLL_SYMLINK):
                os.symlink(LOSSLESS_DLL_PATH, LOSSLESS_DLL_SYMLINK)

            return True
        except Exception as e:
            decky.logger.error(f"reinstall_layer failed: {e}")
            return False

    async def install_runtime(self):
        """Schedule install-arm64.sh on next boot."""
        install_script = os.path.join(decky.DECKY_PLUGIN_DIR, "install-arm64.sh")
        if not os.path.exists(install_script):
            decky.logger.error("install-arm64.sh not found")
            return False
        try:
            svc_dir = "/storage/.config/system.d"
            svc_path = os.path.join(svc_dir, "lsfg-vk-install.service")
            wants_dir = os.path.join(svc_dir, "multi-user.target.wants")
            os.makedirs(wants_dir, exist_ok=True)
            with open(svc_path, "w") as f:
                f.write(f"""[Unit]
Description=LSFG-VK ARM64 install
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStartPre=/bin/sh -c 'for i in $(seq 1 30); do getent hosts github.com >/dev/null 2>&1 && exit 0; sleep 2; done; exit 1'
ExecStart=/bin/sh {install_script}
ExecStartPost=/bin/rm -f {svc_path} {wants_dir}/lsfg-vk-install.service
""")
            link = os.path.join(wants_dir, "lsfg-vk-install.service")
            if os.path.lexists(link):
                os.remove(link)
            os.symlink(svc_path, link)
            return True
        except Exception as e:
            decky.logger.error(f"install_runtime failed: {e}")
            return False

    async def _main(self):
        os.makedirs(LSFG_DIR, exist_ok=True)
        os.makedirs(GAMES_DIR, exist_ok=True)

    async def _unload(self):
        pass
