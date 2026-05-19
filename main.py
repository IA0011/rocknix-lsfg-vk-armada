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

# FEX RootFS install targets (deployed by lsfg-vk-setup.service)
FEX_ROOTFS = "/storage/.local/share/fex-emu/RootFS/ArchLinux"
FEX_SO = os.path.join(FEX_ROOTFS, "usr/lib/liblsfg-vk.so")
FEX_JSON = os.path.join(
    FEX_ROOTFS,
    "usr/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation.x86_64.json",
)

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
    """Check that ROCKNIX has installed the lsfg-vk package."""
    return (
        os.path.exists(SYSTEM_SO)
        and os.path.exists(SYSTEM_JSON)
        and os.path.exists(SYSTEM_WRAPPER)
    )


def _layer_deployed():
    """Check that the layer has been deployed into FEX RootFS."""
    return os.path.exists(FEX_SO) and os.path.exists(FEX_JSON)


def _dll_detected():
    return os.path.exists(LOSSLESS_DLL_PATH)


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
        """Re-run the system setup script (e.g. after Proton update)."""
        if not os.path.exists(SYSTEM_SETUP):
            return False
        try:
            subprocess.run([SYSTEM_SETUP], check=True, timeout=30)
            return True
        except Exception as e:
            decky.logger.error(f"reinstall_layer failed: {e}")
            return False

    async def _main(self):
        os.makedirs(LSFG_DIR, exist_ok=True)
        os.makedirs(GAMES_DIR, exist_ok=True)
        decky.logger.info("LSFG Frame Generation plugin loaded")

    async def _unload(self):
        decky.logger.info("LSFG Frame Generation plugin unloaded")
