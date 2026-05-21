import os
import json
import shutil
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

# ARM64 native paths
ARM64_SO = "/usr/lib/liblsfg-vk-arm64.so"
ARM64_MANIFEST_DIR = "/usr/lib/pressure-vessel/overrides/share/vulkan/implicit_layer.d"
ARM64_MANIFEST = os.path.join(ARM64_MANIFEST_DIR, "VkLayer_LS_frame_generation.json")
ARM64_WRAPPER = os.path.join(LSFG_DIR, "bin/lsfg")

# Lossless Scaling DLL paths
LOSSLESS_DLL_PATH = (
    "/storage/games-internal/roms/steam/steamapps/common/"
    "Lossless Scaling/Lossless.dll"
)
LOSSLESS_DLL_SYMLINK = (
    "/storage/.local/share/Steam/steamapps/common/"
    "Lossless Scaling/Lossless.dll"
)

DEFAULT_SETTINGS = {
    "multiplier": 2,
    "fps_limit": 30,
    "flow_scale": 0.3,
    "performance_mode": 1,
}


def _system_installed():
    """Check that lsfg-vk ARM64 native setup is fully functional."""
    return (
        os.path.exists(ARM64_SO)
        and os.path.exists(ARM64_MANIFEST)
        and _thunks_enabled()
        and os.path.exists(ARM64_WRAPPER)
    )


def _layer_deployed():
    """Check that the ARM64 native layer SO exists."""
    return os.path.exists(ARM64_SO)


def _manifest_deployed():
    """Check that the manifest is in the pressure-vessel overrides dir."""
    return os.path.exists(ARM64_MANIFEST)


def _dll_detected():
    return os.path.exists(LOSSLESS_DLL_PATH) or os.path.exists(LOSSLESS_DLL_SYMLINK)


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


def _enable_thunks():
    """Enable FEX Vulkan thunks in Config.json."""
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


class Plugin:

    async def get_status(self):
        return {
            "system_installed": _system_installed(),
            "layer_deployed": _layer_deployed(),
            "manifest_deployed": _manifest_deployed(),
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

    async def deploy_arm64(self):
        """Deploy ARM64 native layer: manifest, thunks, DLL symlink, wrapper."""
        try:
            # 1. Install manifest to pressure-vessel overrides
            os.makedirs(ARM64_MANIFEST_DIR, exist_ok=True)
            manifest_src = os.path.join(decky.DECKY_PLUGIN_DIR, "defaults/VkLayer_LS_frame_generation.json")
            shutil.copy2(manifest_src, ARM64_MANIFEST)

            # 2. Enable FEX Vulkan thunks
            _enable_thunks()

            # 2b. Persist thunks in ROCKNIX system.cfg (survives reboot)
            system_cfg = "/storage/.config/system/configs/system.cfg"
            setting_line = "steam.vulkan_host_library=1"
            if os.path.exists(system_cfg):
                with open(system_cfg, "r") as f:
                    lines = f.readlines()
                found = False
                for i, line in enumerate(lines):
                    if line.startswith("steam.vulkan_host_library"):
                        lines[i] = setting_line + "\n"
                        found = True
                        break
                if not found:
                    lines.append(setting_line + "\n")
                with open(system_cfg, "w") as f:
                    f.writelines(lines)

            # 3. Create Lossless.dll symlink
            dll_dir = os.path.dirname(LOSSLESS_DLL_SYMLINK)
            os.makedirs(dll_dir, exist_ok=True)
            if not os.path.exists(LOSSLESS_DLL_SYMLINK):
                if os.path.exists(LOSSLESS_DLL_PATH):
                    os.symlink(LOSSLESS_DLL_PATH, LOSSLESS_DLL_SYMLINK)
                else:
                    # Create placeholder so the layer doesn't error
                    open(LOSSLESS_DLL_SYMLINK, "a").close()

            # 4. Install lsfg wrapper
            bin_dir = os.path.join(LSFG_DIR, "bin")
            os.makedirs(bin_dir, exist_ok=True)
            wrapper_src = os.path.join(decky.DECKY_PLUGIN_DIR, "defaults/lsfg")
            shutil.copy2(wrapper_src, ARM64_WRAPPER)
            os.chmod(ARM64_WRAPPER, 0o755)

            # 5. Create ~/lsfg symlink
            home_link = os.path.expanduser("~/lsfg")
            if os.path.lexists(home_link):
                os.remove(home_link)
            os.symlink(ARM64_WRAPPER, home_link)

            decky.logger.info("ARM64 layer deployed successfully")
            return True
        except Exception as e:
            decky.logger.error(f"deploy_arm64 failed: {e}")
            return False

    async def reinstall_layer(self):
        """Deploy ARM64 native layer (preferred) or fall back to legacy setup."""
        # Try ARM64 native approach first
        if os.path.exists(ARM64_SO):
            return await self.deploy_arm64()

        # Legacy fallback: run setup script
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
            _enable_thunks()
            decky.logger.info("FEX Vulkan thunks enabled")
            return True
        except Exception as e:
            decky.logger.error(f"enable_thunks failed: {e}")
            return False

    async def install_runtime(self):
        """Schedule lsfg-vk install on next boot (runs natively, outside FEX)."""
        install_script = os.path.join(
            decky.DECKY_PLUGIN_DIR, "install-arm64.sh"
        )
        if not os.path.exists(install_script):
            decky.logger.error("install-arm64.sh not found in plugin directory")
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
