# LSFG Frame Generation — Decky Plugin for ROCKNIX

A [Decky Loader](https://decky.xyz/) plugin that provides per-game configuration UI for [LSFG-VK](https://github.com/PancakeTAS/lsfg-vk) frame generation on ROCKNIX.

## Requirements

- ROCKNIX with Steam and [Decky Loader](https://decky.xyz/) installed
- [Lossless Scaling](https://store.steampowered.com/app/993090/Lossless_Scaling/) installed via Steam
- WiFi connection (for first-time install)

No custom OS image or rebuild required — the plugin handles all installation at runtime.

## How It Works

The plugin includes a runtime installer (`install.sh`) that:
- Downloads the x86_64 Vulkan layer from the lsfg-vk release
- Deploys it into the FEX RootFS (where pressure-vessel discovers it)
- Installs the `lsfg` launch wrapper to `~/`
- Deploys `user_settings.py` into existing GE-Proton installs
- Creates a default config with sensible settings

The plugin UI handles:
- Per-game settings (multiplier, FPS limit, flow scale, performance mode)
- Default settings editor
- Status indicators (layer deployed, DLL detected)
- "Reinstall Layer" button (re-runs setup after Proton updates)

## Usage

1. Install this plugin via Decky Loader
2. Open the plugin and press "Install LSFG-VK"
3. Reboot when prompted
4. Set Steam launch options to `~/lsfg %command%` (or use the plugin's "Copy Launch Options" button)
5. Configure frame generation per-game via the plugin's slider UI

## Configuration

Per-game configs are stored at `/storage/.config/lsfg-vk/games/<APPID>.json`:

```json
{"multiplier": 2, "fps_limit": 30, "flow_scale": 0.3, "performance_mode": 1}
```

Default config at `/storage/.config/lsfg-vk/default.json` applies to any game without a per-game override.

## Known Issues

- **LSFG is not working with Snapdragon Elite devices.**

## Building

```bash
npm install
npm run build
```

Output is in `dist/`. Install by copying the `rocknix-lsfg-vk/` directory (with `plugin.json`, `main.py`, `install.sh`, `dist/`) to `~/homebrew/plugins/` on the device.

## License

GPL-2.0
