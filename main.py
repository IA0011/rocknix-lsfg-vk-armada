import os
import json
import urllib.request
import tarfile
import decky
import subprocess

LSFG_DIR = "/var/home/armada/.config/lsfg-vk"
GAMES_DIR = os.path.join(LSFG_DIR, "games")
DEFAULT_CONF = os.path.join(LSFG_DIR, "default.json")

OVERLAY_UPPER = "/var/home/armada/.tmp/pv-upper"
XDG_LAYER_DIR = "/var/home/armada/.local/share/vulkan/implicit_layer.d"
ARM64_SO = os.path.join(LSFG_DIR, "lib/liblsfg-vk-arm64.so")
ARM64_MANIFEST = os.path.join(XDG_LAYER_DIR, "VkLayer_LS_frame_generation_arm64.json")
ARM64_WRAPPER = os.path.join(LSFG_DIR, "bin/lsfg")

FEX_CONFIG = "/var/home/armada/.config/fex-emu/Config.json"
DOWNLOAD_URL = "https://github.com/seilent/lsfg-vk/releases/download/latest/lsfg-vk-arm64.tar.gz"

LOSSLESS_DLL_PATHS = [
    "/var/home/armada/.local/share/Steam/steamapps/common/Lossless Scaling/Lossless.dll",
    "/var/home/armada/games-internal/roms/steam/steamapps/common/Lossless Scaling/Lossless.dll",
    "/var/home/armada/roms/steam/steamapps/common/Lossless Scaling/Lossless.dll",
]

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
        """Schedule deploy service for next boot (just local file ops, no download)."""
        deploy_script = os.path.join(LSFG_DIR, "bin/deploy.sh")
        os.makedirs(os.path.dirname(deploy_script), exist_ok=True)

        # Write deploy script that does local-only operations
        plugin_dir = decky.DECKY_PLUGIN_DIR
        with open(deploy_script, "w") as f:
            f.write(f"""#!/bin/sh
set -eu
LSFG_DIR="/var/home/armada/.config/lsfg-vk"
OVERLAY_UPPER="/var/home/armada/.tmp/pv-upper"
OVERLAY_WORK="/var/home/armada/.tmp/pv-work"
FEX_ROOTFS="/var/home/armada/.local/share/fex-emu/RootFS/ArchLinux"

# Clean old installs
rm -f "${{FEX_ROOTFS}}/usr/lib/liblsfg-vk.so" "${{FEX_ROOTFS}}/usr/lib/liblsfg-vk-arm64.so"
rm -f "${{FEX_ROOTFS}}/usr/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation"*.json
rm -rf "$OVERLAY_UPPER" "$OVERLAY_WORK"
umount -l /usr/lib 2>/dev/null || true

# Deploy to overlay
mkdir -p "$OVERLAY_UPPER/pressure-vessel/overrides/share/vulkan/implicit_layer.d" "$OVERLAY_WORK"
cp "$LSFG_DIR/lib/liblsfg-vk-arm64.so" "$OVERLAY_UPPER/liblsfg-vk-arm64.so"
cp "{plugin_dir}/defaults/VkLayer_LS_frame_generation.json" \
    "$OVERLAY_UPPER/pressure-vessel/overrides/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation_arm64.json"

# Mount overlay
mount -t overlay overlay -o "lowerdir=/usr/lib,upperdir=$OVERLAY_UPPER,workdir=$OVERLAY_WORK" /usr/lib

# XDG manifest for native ARM64 Proton
mkdir -p /var/home/armada/.local/share/vulkan/implicit_layer.d
cp "$OVERLAY_UPPER/pressure-vessel/overrides/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation_arm64.json" \
    /var/home/armada/.local/share/vulkan/implicit_layer.d/

# Wrapper
cp "{plugin_dir}/defaults/lsfg" "$LSFG_DIR/bin/lsfg"
chmod +x "$LSFG_DIR/bin/lsfg"
ln -sf "$LSFG_DIR/bin/lsfg" ~/lsfg

# Thunks
python3 -c "
import json, os
c='/var/home/armada/.config/fex-emu/Config.json'
os.makedirs(os.path.dirname(c), exist_ok=True)
cfg = json.load(open(c)) if os.path.exists(c) else {{}}
cfg.setdefault('ThunksDB', {{}})['Vulkan'] = 1
json.dump(cfg, open(c, 'w'), indent=2)
"

# Default config
[ -f "$LSFG_DIR/default.json" ] || echo '{{"multiplier": 2, "fps_limit": 30, "flow_scale": 0.3, "performance_mode": 1}}' > "$LSFG_DIR/default.json"
""")
        os.chmod(deploy_script, 0o755)

        # Armada: Decky runs this plugin as root, so deploy immediately.
        # Do not rely on a post-reboot systemd service.
        subprocess.run(["/bin/bash", deploy_script], check=True)
        return True


        # Create boot service for overlay mount (persistent across reboots)
        svc_dir = "/var/home/armada/.config/system.d"
        wants_dir = os.path.join(svc_dir, "multi-user.target.wants")
        os.makedirs(wants_dir, exist_ok=True)

        # One-shot install service (runs deploy.sh once, then overlay service handles reboots)
        svc_path = os.path.join(svc_dir, "lsfg-vk-install.service")
        with open(svc_path, "w") as f:
            f.write(f"""[Unit]
Description=LSFG-VK ARM64 deploy
After=local-fs.target

[Service]
Type=oneshot
ExecStart={deploy_script}
ExecStartPost=/bin/rm -f {svc_path} {wants_dir}/lsfg-vk-install.service
""")
        link = os.path.join(wants_dir, "lsfg-vk-install.service")
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(svc_path, link)

        # Persistent overlay service (re-mounts on every boot)
        overlay_svc = os.path.join(svc_dir, "lsfg-vk-overlay.service")
        with open(overlay_svc, "w") as f:
            f.write(f"""[Unit]
Description=Mount /usr/lib overlay for LSFG-VK
DefaultDependencies=no
After=local-fs.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'mkdir -p /var/home/armada/.tmp/pv-upper /var/home/armada/.tmp/pv-work && mount -t overlay overlay -o lowerdir=/usr/lib,upperdir=/var/home/armada/.tmp/pv-upper,workdir=/var/home/armada/.tmp/pv-work /usr/lib'

[Install]
WantedBy=multi-user.target
""")
        link2 = os.path.join(wants_dir, "lsfg-vk-overlay.service")
        if os.path.lexists(link2):
            os.remove(link2)
        os.symlink(overlay_svc, link2)

        decky.logger.info("Deploy scheduled for next boot")
        return True

    async def reinstall_layer(self):
        """Download fresh .so and re-schedule deploy (user must reboot)."""
        result = await self.download_layer()
        if not result.get("success"):
            return False
        return await self.install_runtime()

    async def uninstall_lsfg(self):
        """Remove all LSFG-VK artifacts and services. Reboot required."""
        import shutil
        try:
            # Remove overlay and work dirs
            for d in [OVERLAY_UPPER, "/var/home/armada/.tmp/pv-work"]:
                if os.path.exists(d):
                    shutil.rmtree(d)

            # Unmount overlay
            os.system("umount -l /usr/lib 2>/dev/null || true")

            # Remove systemd services
            svc_dir = "/var/home/armada/.config/system.d"
            wants_dir = os.path.join(svc_dir, "multi-user.target.wants")
            for svc in ["lsfg-vk-install.service", "lsfg-vk-overlay.service"]:
                for p in [os.path.join(svc_dir, svc), os.path.join(wants_dir, svc)]:
                    if os.path.lexists(p):
                        os.remove(p)

            # Remove XDG manifest
            xdg_manifest = "/var/home/armada/.local/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation_arm64.json"
            if os.path.exists(xdg_manifest):
                os.remove(xdg_manifest)

            # Remove wrapper symlink
            home_lsfg = os.path.expanduser("~/lsfg")
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
