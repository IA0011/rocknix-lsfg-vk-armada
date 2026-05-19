# LSFG Frame Generation — Decky Plugin for ROCKNIX

A [Decky Loader](https://decky.xyz/) plugin that provides per-game configuration UI for [LSFG-VK](https://github.com/PancakeTAS/lsfg-vk) frame generation on ROCKNIX.

## Requirements

This plugin requires the `lsfg-vk` system package built into your ROCKNIX image. Apply the following commit to the ROCKNIX source tree before building:

- **Commit:** [`bb91778ec1`](https://github.com/seilent/distribution/commit/bb91778ec1) — `lsfg-vk: install layer into FEX RootFS via setup service`
- **Branch:** [`pocket-ace`](https://github.com/seilent/distribution/tree/pocket-ace)

Without this system package, the plugin has nothing to configure — the Vulkan layer and setup service must be present in the OS image.

## How It Works

The system package (`lsfg-vk`) handles:
- Installing the x86_64 Vulkan layer into the FEX RootFS (where pressure-vessel discovers it)
- Deploying `user_settings.py` to each GE-Proton install
- Providing the `lsfg` launch wrapper

This plugin handles:
- Per-game settings UI (multiplier, FPS limit, flow scale, performance mode)
- Default settings editor
- Status indicators (layer deployed, DLL detected)
- "Reinstall Layer" button (re-runs `lsfg-vk-setup` after Proton updates)

## Usage

1. Build ROCKNIX with the `lsfg-vk` commit applied
2. Install [Lossless Scaling](https://store.steampowered.com/app/993090/Lossless_Scaling/) via Steam
3. Install this plugin via Decky Loader
4. Set Steam launch options to `lsfg %command%` (or use the plugin's "Copy Launch Options" button)
5. Configure frame generation per-game via the plugin's slider UI

## Configuration

Per-game configs are stored at `/storage/.config/lsfg-vk/games/<APPID>.json`:

```json
{"multiplier": 2, "fps_limit": 30, "flow_scale": 0.3, "performance_mode": 1}
```

Default config at `/storage/.config/lsfg-vk/default.json` applies to any game without a per-game override.

## Building

```bash
npm install
npm run build
```

Output is in `dist/`. Install by copying the `rocknix-lsfg-vk/` directory (with `plugin.json`, `main.py`, `dist/`) to `~/homebrew/plugins/` on the device.

## License

GPL-2.0
