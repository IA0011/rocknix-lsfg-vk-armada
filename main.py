import os
import json
import subprocess
import decky

LSFG_DIR = "/storage/.config/lsfg-vk"
GAMES_DIR = os.path.join(LSFG_DIR, "games")
DEFAULT_CONF = os.path.join(LSFG_DIR, "default.json")

# System-managed paths (installed by ROCKNIX lsfg-vk package)
SYSTEM_SO = "/usr/share/lsfg-vk/liblsfg-vk.so"
SYSTEM_JSON = "/usr/share/lsfg-vk/VkLayer_LS_frame_generation.json"
SYSTEM_WRAPPER = "/usr/bin/lsfg"
SYSTEM_SETUP = "/usr/bin/lsfg-vk-setup"

# Runtime-install paths (overlay mode, no rebuild required)
RUNTIME_SO = os.path.join(LSFG_DIR, "lib/liblsfg-vk.so")
RUNTIME_JSON = os.path.join(LSFG_DIR, "lib/VkLayer_LS_frame_generation.json")
RUNTIME_WRAPPER = os.path.join(LSFG_DIR, "bin/lsfg")
RUNTIME_SETUP = os.path.join(LSFG_DIR, "bin/lsfg-vk-setup")

# FEX RootFS install targets (deployed by lsfg-vk-setup.service)
FEX_ROOTFS = "/storage/.local/share/fex-emu/RootFS/ArchLinux"
FEX_SO = os.path.join(FEX_ROOTFS, "usr/lib/liblsfg-vk.so")
FEX_JSON = os.path.join(
    FEX_ROOTFS,
    "usr/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation.x86_64.json",
)

# FEX config (for Vulkan thunks)
FEX_CONFIG = "/storage/.config/fex-emu/Config.json"

# Lossless Scaling DLL detection (for user warning only)
LOSSLESS_DLL_PATH = (
    "/storage/games-internal/roms/steam/steamapps/common/"
    "Lossless Scaling/Lossless.dll"
)

DEFAULT_SETTINGS = {
    "multiplier": 2,
    "fps_limit": 30,
    "flow_scale": 0.3,
    "performance_mode": 1,
}


def _system_installed():
    """Check that lsfg-vk is available (system package or runtime install)."""
    return (
        (os.path.exists(SYSTEM_SO) and os.path.exists(SYSTEM_WRAPPER))
        or (os.path.exists(RUNTIME_SO) and os.path.exists(RUNTIME_WRAPPER))
    )


def _layer_deployed():
    """Check that the layer has been deployed into FEX RootFS."""
    return os.path.exists(FEX_SO) and os.path.exists(FEX_JSON)


def _dll_detected():
    return os.path.exists(LOSSLESS_DLL_PATH)


def _thunks_enabled():
    """Check if FEX Vulkan thunks are enabled."""
    if not os.path.exists(FEX_CONFIG):
        return False
    try:
        with open(FEX_CONFIG, "r") as f:
            cfg = json.load(f)
        return cfg.get("ThunksDB", {}).get("Vulkan") == 1
    except Exception:
        return False


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
            "thunks_enabled": _thunks_enabled(),
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
        """Re-run the setup script (e.g. after Proton update)."""
        setup = SYSTEM_SETUP if os.path.exists(SYSTEM_SETUP) else RUNTIME_SETUP
        if not os.path.exists(setup):
            return False
        try:
            subprocess.run([setup], check=True, timeout=30)
            return True
        except Exception as e:
            decky.logger.error(f"reinstall_layer failed: {e}")
            return False

    async def enable_thunks(self):
        """Enable FEX Vulkan thunks in Config.json."""
        try:
            os.makedirs(os.path.dirname(FEX_CONFIG), exist_ok=True)
            if os.path.exists(FEX_CONFIG):
                with open(FEX_CONFIG, "r") as f:
                    cfg = json.load(f)
            else:
                cfg = {}
            if "ThunksDB" not in cfg:
                cfg["ThunksDB"] = {}
            cfg["ThunksDB"]["Vulkan"] = 1
            with open(FEX_CONFIG, "w") as f:
                json.dump(cfg, f, indent=2)
            decky.logger.info("FEX Vulkan thunks enabled")
            return True
        except Exception as e:
            decky.logger.error(f"enable_thunks failed: {e}")
            return False

    async def install_runtime(self):
        """Schedule lsfg-vk install on next boot (runs natively, outside FEX)."""
        install_script = os.path.join(
            decky.DECKY_PLUGIN_DIR, "install.sh"
        )
        if not os.path.exists(install_script):
            decky.logger.error("install.sh not found in plugin directory")
            return False
        try:
            svc_dir = "/storage/.config/system.d"
            svc_path = os.path.join(svc_dir, "lsfg-vk-install.service")
            wants_dir = os.path.join(svc_dir, "multi-user.target.wants")
            os.makedirs(wants_dir, exist_ok=True)
            with open(svc_path, "w") as f:
                f.write(f"""[Unit]
Description=LSFG-VK one-time install
After=network-online.target plugin_loader.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStartPre=/bin/sh -c 'for i in $(seq 1 30); do getent hosts github.com >/dev/null 2>&1 && exit 0; sleep 2; done; exit 1'
ExecStart=/bin/sh {install_script}
ExecStartPost=/bin/rm -f {svc_path} {wants_dir}/lsfg-vk-install.service
""")
            link = os.path.join(wants_dir, "lsfg-vk-install.service")
            if os.path.exists(link):
                os.remove(link)
            os.symlink(svc_path, link)
            decky.logger.info("lsfg-vk install scheduled for next boot")
            return True
        except Exception as e:
            decky.logger.error(f"install_runtime failed: {e}")
            return False

    async def _main(self):
        os.makedirs(LSFG_DIR, exist_ok=True)
        os.makedirs(GAMES_DIR, exist_ok=True)
        decky.logger.info("LSFG Frame Generation plugin loaded")

    async def _unload(self):
        decky.logger.info("LSFG Frame Generation plugin unloaded")
