# LSFG Frame Generation for Armada OS

Decky Loader plugin for installing and configuring **LSFG-VK frame generation** on Armada OS / Fedora ARM64 handhelds.

This fork is adapted for devices such as the **AYN Odin 3** running Armada OS.

## What It Does

The plugin provides a Decky UI for LSFG-VK and installs a working Armada runtime:

- Downloads the ARM64 `liblsfg-vk` library
- Installs LSFG launch wrappers:
  - `~/lsfg`
  - `~/lsfg-force`
- Installs the Vulkan implicit layer manifest
- Enables FEX Vulkan thunks
- Creates default and per-game LSFG config files
- Provides per-game LSFG settings through Decky

## Requirements

- Armada OS / Fedora ARM64
- Decky Loader
- Steam
- Lossless Scaling installed through Steam
- Internet connection for first-time runtime install

## Installation

Install the plugin through Decky Loader.

Open:

```text
LSFG Frame Generation (Armada)
```

Press:

```text
Install LSFG-VK
```

The installer will deploy the LSFG-VK runtime and wrappers automatically.

## Steam Launch Options

Default launch option:

```text
~/lsfg %command%
```

Optional forced-layer launch option:

```text
~/lsfg-force %command%
```

Use the default wrapper first. Try the forced wrapper only if the game does not detect or load the LSFG Vulkan layer.

## Configuration

Default config:

```text
/var/home/armada/.config/lsfg-vk/default.json
```

Per-game configs:

```text
/var/home/armada/.config/lsfg-vk/games/<APPID>.json
```

Example config:

```json
{
  "multiplier": 2,
  "fps_limit": 60,
  "flow_scale": 0.8,
  "performance_mode": 1
}
```

## Installed Runtime Paths

The Armada installer creates:

```text
/var/home/armada/.config/lsfg-vk/bin/lsfg
/var/home/armada/.config/lsfg-vk/bin/lsfg-force
/var/home/armada/.config/lsfg-vk/default.json
/var/home/armada/.local/lib/lsfg-vk/liblsfg-vk-arm64.so
/var/home/armada/.local/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation_arm64.json
/var/home/armada/lsfg
/var/home/armada/lsfg-force
```

## Manual Runtime Install

The Decky UI runs the Armada installer automatically, but it can also be run manually over SSH:

```bash
sudo bash /var/home/armada/homebrew/plugins/armada-lsfg-vk/install-armada.sh
sudo systemctl restart plugin_loader.service
```

Verify install:

```bash
find /var/home/armada/.config/lsfg-vk -maxdepth 4 -type f -o -type l 2>/dev/null
find /var/home/armada/.local/lib/lsfg-vk -maxdepth 3 -type f -o -type l 2>/dev/null
ls -l /var/home/armada/lsfg /var/home/armada/lsfg-force 2>/dev/null
ls -l /var/home/armada/.local/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation_arm64.json 2>/dev/null
```

## Clean Uninstall

```bash
sudo systemctl stop plugin_loader.service

sudo rm -rf /var/home/armada/homebrew/plugins/armada-lsfg-vk
sudo rm -rf /var/home/armada/.config/lsfg-vk
sudo rm -rf /var/home/armada/.local/lib/lsfg-vk

rm -f /var/home/armada/lsfg
rm -f /var/home/armada/lsfg-force
rm -f /var/home/armada/.local/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation_arm64.json
rm -f /var/home/armada/.local/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation.json

sudo systemctl disable --now lsfg-vk-overlay.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/lsfg-vk-overlay.service
sudo systemctl daemon-reload
```

## Building

Install dependencies:

```bash
npm install
```

Build the Decky frontend:

```bash
npm run build
```

Build output is written to:

```text
dist/
```

## Packaging

From the parent directory:

```bash
zip -r armada-lsfg-vk.zip armada-lsfg-vk \
  -x "armada-lsfg-vk/.git/*" \
  -x "armada-lsfg-vk/node_modules/*"
```

Verify the installer inside the ZIP:

```bash
unzip -p armada-lsfg-vk.zip armada-lsfg-vk/install-armada.sh | grep -nE "uname -m|aarch64|x86_64|unsupported"
```

Expected installer check:

```bash
case "$(uname -m)" in
  aarch64|arm64|x86_64) ;;
  *) log "ERROR: unsupported arch/context; got $(uname -m)"; exit 1 ;;
esac
```

Decky may report `x86_64` in the plugin install context on Armada OS, so the installer allows that context while still installing the ARM64 LSFG-VK runtime.

## Troubleshooting

Check Decky plugin logs:

```bash
sudo journalctl -u plugin_loader.service -n 180 --no-pager -l | grep -Ei "lsfg|install|status|traceback|error|failed|arch|unsupported"
```

Restart Decky:

```bash
sudo systemctl restart plugin_loader.service
```

Check runtime files:

```bash
find /var/home/armada/.config/lsfg-vk -maxdepth 4 -type f -o -type l 2>/dev/null
find /var/home/armada/.local/lib/lsfg-vk -maxdepth 3 -type f -o -type l 2>/dev/null
ls -l /var/home/armada/lsfg /var/home/armada/lsfg-force 2>/dev/null
ls -l /var/home/armada/.local/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation_arm64.json 2>/dev/null
```

## Notes

Some games may work with:

```text
~/lsfg %command%
```

Others may require:

```text
~/lsfg-force %command%
```

Compatibility depends on the game, Proton build, WineVulkan, vkd3d, Gamescope, FEX, and the Armada OS runtime.

## Known Issues

- Some games may load the LSFG layer but not generate frames.
- Forced-layer mode may crash some Wine/Proton titles.
- Compatibility on Snapdragon Elite / ARM64 devices is still experimental.
- Results vary depending on Proton and the game’s graphics API.

## Credits

Forked from:

```text
seilent/rocknix-lsfg-vk
```

Adapted for Armada OS by:

```text
IA0011
```

## License

GPL-2.0
