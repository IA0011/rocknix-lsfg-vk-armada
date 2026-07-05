#!/usr/bin/env bash
# LSFG-VK installer for Armada OS / Fedora ARM64
set -euo pipefail
LSFG_SO_URL="${LSFG_SO_URL:-https://github.com/seilent/lsfg-vk/releases/download/latest/lsfg-vk-arm64.tar.gz}"
TARGET_USER="${SUDO_USER:-${USER:-armada}}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[ -n "$TARGET_HOME" ] || TARGET_HOME="/home/$TARGET_USER"
LSFG_DIR="$TARGET_HOME/.config/lsfg-vk"
BIN_DIR="$LSFG_DIR/bin"
USER_LIB_DIR="$TARGET_HOME/.local/lib/lsfg-vk"
GAMES_DIR="$LSFG_DIR/games"
XDG_LAYER_DIR="$TARGET_HOME/.local/share/vulkan/implicit_layer.d"
OVERLAY_UPPER="$TARGET_HOME/.local/share/lsfg-vk/pv-upper"
OVERLAY_WORK="$TARGET_HOME/.local/share/lsfg-vk/pv-work"
FEX_CONFIG="$TARGET_HOME/.config/fex-emu/Config.json"
TMP_DIR="/tmp/lsfg-vk-install"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
log() { echo "[lsfg-vk-armada] $*"; }
run_root() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi; }
case "$(uname -m)" in
  aarch64|arm64|x86_64) ;;
  *) log "ERROR: unsupported arch/context; got $(uname -m)"; exit 1 ;;
esac
log "Installing for user $TARGET_USER at $TARGET_HOME"
mkdir -p "$BIN_DIR" "$USER_LIB_DIR" "$GAMES_DIR" "$XDG_LAYER_DIR" "$OVERLAY_UPPER" "$OVERLAY_WORK" "$TMP_DIR" "$(dirname "$FEX_CONFIG")"
rm -rf "$GAMES_DIR"
mkdir -p "$GAMES_DIR"
echo '{"multiplier": 2, "fps_limit": 60, "flow_scale": 0.8, "performance_mode": 1}' > "$LSFG_DIR/default.json"
log "Downloading ARM64 liblsfg-vk..."
curl -fL --retry 3 --connect-timeout 20 "$LSFG_SO_URL" -o "$TMP_DIR/lsfg-vk-arm64.tar.gz"
tar -xzf "$TMP_DIR/lsfg-vk-arm64.tar.gz" -C "$TMP_DIR"
LIB_SRC="$(find "$TMP_DIR" -name liblsfg-vk-arm64.so -type f | head -n1)"
[ -n "$LIB_SRC" ] || { log "ERROR: liblsfg-vk-arm64.so not found in archive"; exit 1; }
install -m 0644 "$LIB_SRC" "$USER_LIB_DIR/liblsfg-vk-arm64.so"
rm -rf "$TMP_DIR"
log "Writing Vulkan manifests..."
cat > "$XDG_LAYER_DIR/VkLayer_LS_frame_generation_arm64.json" <<EOF
{
  "file_format_version": "1.0.0",
  "layer": {
    "name": "VK_LAYER_LSFGVK_frame_generation",
    "type": "GLOBAL",
    "library_path": "$USER_LIB_DIR/liblsfg-vk-arm64.so",
    "api_version": "1.4.328",
    "implementation_version": "2",
    "description": "LSFG frame generation (ARM64 native, Armada user install)",
    "enable_environment": { "LSFG_ENABLE": "1" },
    "disable_environment": { "DISABLE_LSFGVK": "1" }
  }
}
EOF
install -m 0644 "$USER_LIB_DIR/liblsfg-vk-arm64.so" "$OVERLAY_UPPER/liblsfg-vk-arm64.so"
mkdir -p "$OVERLAY_UPPER/pressure-vessel/overrides/share/vulkan/implicit_layer.d"
cat > "$OVERLAY_UPPER/pressure-vessel/overrides/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation_arm64.json" <<EOF
{
  "file_format_version": "1.0.0",
  "layer": {
    "name": "VK_LAYER_LSFGVK_frame_generation",
    "type": "GLOBAL",
    "library_path": "/usr/lib/liblsfg-vk-arm64.so",
    "api_version": "1.4.328",
    "implementation_version": "2",
    "description": "LSFG frame generation (ARM64 native, pressure-vessel override)",
    "enable_environment": { "LSFG_ENABLE": "1" },
    "disable_environment": { "DISABLE_LSFGVK": "1" }
  }
}
EOF
log "Installing wrappers..."
if [ -f "$SCRIPT_DIR/defaults/lsfg" ]; then
  install -m 0755 "$SCRIPT_DIR/defaults/lsfg" "$BIN_DIR/lsfg"
else
  printf '#!/usr/bin/env bash\nexport LSFG_ENABLE=1 LSFGVK_ENV=1\nexec "$@"\n' > "$BIN_DIR/lsfg" && chmod +x "$BIN_DIR/lsfg"
fi
if [ -f "$SCRIPT_DIR/defaults/lsfg-force" ]; then
  install -m 0755 "$SCRIPT_DIR/defaults/lsfg-force" "$BIN_DIR/lsfg-force"
fi
ln -sf "$BIN_DIR/lsfg" "$TARGET_HOME/lsfg"
[ -f "$BIN_DIR/lsfg-force" ] && ln -sf "$BIN_DIR/lsfg-force" "$TARGET_HOME/lsfg-force"
log "Enabling FEX Vulkan thunks..."
python3 - <<PYINNER
import json, os
c = "$FEX_CONFIG"
os.makedirs(os.path.dirname(c), exist_ok=True)
cfg = json.load(open(c)) if os.path.exists(c) else {}
cfg.setdefault('ThunksDB', {})['Vulkan'] = 1
json.dump(cfg, open(c, 'w'), indent=2)
PYINNER
log "Installing Fedora systemd overlay service..."
SERVICE=/etc/systemd/system/lsfg-vk-overlay.service
run_root tee "$SERVICE" >/dev/null <<EOF
[Unit]
Description=Mount /usr/lib overlay for LSFG-VK pressure-vessel discovery
DefaultDependencies=no
After=local-fs.target
Before=steam.service gamescope-session.service graphical.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/bash -lc 'mkdir -p "$OVERLAY_UPPER" "$OVERLAY_WORK" && mountpoint -q /usr/lib || mount -t overlay overlay -o lowerdir=/usr/lib,upperdir="$OVERLAY_UPPER",workdir="$OVERLAY_WORK" /usr/lib'
ExecStop=/usr/bin/umount -l /usr/lib

[Install]
WantedBy=multi-user.target
EOF
run_root systemctl daemon-reload
run_root systemctl enable --now lsfg-vk-overlay.service || log "WARNING: overlay service failed. Native XDG manifest is still installed; check: systemctl status lsfg-vk-overlay.service"
chown -R "$TARGET_USER:$TARGET_USER" "$LSFG_DIR" "$TARGET_HOME/.local/lib/lsfg-vk" "$TARGET_HOME/.local/share/vulkan" "$TARGET_HOME/.local/share/lsfg-vk" "$TARGET_HOME/lsfg" "$TARGET_HOME/lsfg-force" 2>/dev/null || true
log "Done. Default Steam launch option: ~/lsfg %command%"
log "Optional forced-layer launch option: ~/lsfg-force %command%"
log "Check overlay: systemctl status lsfg-vk-overlay.service --no-pager"
