#!/bin/sh
# LSFG-VK ARM64 installer
# Deploys ARM64 layer via /usr/lib overlay mount (immutable OS workaround).
# A boot service mounts the overlay before Steam starts.

set -euo pipefail

LSFG_SO_URL="${LSFG_SO_URL:-https://github.com/seilent/lsfg-vk/releases/download/latest/lsfg-vk-arm64.tar.gz}"
LSFG_DIR="/storage/.config/lsfg-vk"
BIN_DIR="${LSFG_DIR}/bin"
SRC_DIR="${LSFG_DIR}/lib"
GAMES_DIR="${LSFG_DIR}/games"
OVERLAY_UPPER="/storage/.tmp/pv-upper"
OVERLAY_WORK="/storage/.tmp/pv-work"
FEX_CONFIG="/storage/.config/fex-emu/Config.json"
TMP_DIR="/tmp/lsfg-vk-install"

log() { echo "[lsfg-vk-arm64] $*"; }

if [ "$(uname -m)" != "aarch64" ]; then
    log "ERROR: aarch64 only"; exit 1
fi

# Create directories
mkdir -p "${BIN_DIR}" "${SRC_DIR}" "${GAMES_DIR}" "${TMP_DIR}" "${OVERLAY_UPPER}" "${OVERLAY_WORK}"

# Default config
[ -f "${LSFG_DIR}/default.json" ] || echo '{"multiplier": 2, "fps_limit": 30, "flow_scale": 0.3, "performance_mode": 1}' > "${LSFG_DIR}/default.json"

# Download ARM64 .so
log "Downloading ARM64 liblsfg-vk..."
curl -sSL "${LSFG_SO_URL}" -o "${TMP_DIR}/lsfg-vk-arm64.tar.gz"
tar -xzf "${TMP_DIR}/lsfg-vk-arm64.tar.gz" -C "${TMP_DIR}"
cp "${TMP_DIR}/liblsfg-vk-arm64.so" "${SRC_DIR}/liblsfg-vk-arm64.so"
rm -rf "${TMP_DIR}"

# Deploy .so and manifest to overlay upper dir
log "Deploying to overlay..."
cp "${SRC_DIR}/liblsfg-vk-arm64.so" "${OVERLAY_UPPER}/liblsfg-vk-arm64.so"
mkdir -p "${OVERLAY_UPPER}/pressure-vessel/overrides/share/vulkan/implicit_layer.d"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "${SCRIPT_DIR}/defaults/VkLayer_LS_frame_generation.json" ]; then
    cp "${SCRIPT_DIR}/defaults/VkLayer_LS_frame_generation.json" \
        "${OVERLAY_UPPER}/pressure-vessel/overrides/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation_arm64.json"
else
    cat > "${OVERLAY_UPPER}/pressure-vessel/overrides/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation_arm64.json" << EOF
{
  "file_format_version": "1.0.0",
  "layer": {
    "name": "VK_LAYER_LSFGVK_frame_generation",
    "type": "GLOBAL",
    "library_path": "/usr/lib/liblsfg-vk-arm64.so",
    "api_version": "1.4.328",
    "implementation_version": "2",
    "description": "LSFG frame generation (ARM64 native)",
    "enable_environment": { "LSFG_ENABLE": "1" },
    "disable_environment": { "DISABLE_LSFGVK": "1" }
  }
}
EOF
fi

# Mount overlay now (if not already mounted)
if ! mount | grep -q "overlay on /usr/lib"; then
    mount -t overlay overlay -o "lowerdir=/usr/lib,upperdir=${OVERLAY_UPPER},workdir=${OVERLAY_WORK}" /usr/lib
    log "Overlay mounted"
fi

# Create boot service to mount overlay before Steam
log "Installing boot service..."
mkdir -p /storage/.config/system.d/multi-user.target.wants
cat > /storage/.config/system.d/lsfg-vk-overlay.service << EOF
[Unit]
Description=Mount /usr/lib overlay for LSFG-VK
DefaultDependencies=no
Before=steam-bigpicture.scope gamescope.service
After=local-fs.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'mkdir -p ${OVERLAY_UPPER} ${OVERLAY_WORK} && mount -t overlay overlay -o lowerdir=/usr/lib,upperdir=${OVERLAY_UPPER},workdir=${OVERLAY_WORK} /usr/lib'

[Install]
WantedBy=multi-user.target
EOF
ln -sf /storage/.config/system.d/lsfg-vk-overlay.service \
    /storage/.config/system.d/multi-user.target.wants/lsfg-vk-overlay.service

# Install wrapper
log "Installing wrapper..."
if [ -f "${SCRIPT_DIR}/defaults/lsfg" ]; then
    cp "${SCRIPT_DIR}/defaults/lsfg" "${BIN_DIR}/lsfg"
else
    curl -sSL "https://raw.githubusercontent.com/seilent/rocknix-lsfg-vk/arm64-thunks/defaults/lsfg" -o "${BIN_DIR}/lsfg"
fi
chmod +x "${BIN_DIR}/lsfg"
cp "${BIN_DIR}/lsfg" ~/lsfg
chmod +x ~/lsfg

# Enable FEX Vulkan thunks
log "Enabling FEX Vulkan thunks..."
python3 -c "
import json, os
os.makedirs(os.path.dirname('${FEX_CONFIG}'), exist_ok=True)
cfg = json.load(open('${FEX_CONFIG}')) if os.path.exists('${FEX_CONFIG}') else {}
cfg.setdefault('ThunksDB', {})['Vulkan'] = 1
json.dump(cfg, open('${FEX_CONFIG}', 'w'), indent=2)
"

# Create Lossless.dll symlink for standard path discovery
DLL_SRC="/storage/games-internal/roms/steam/steamapps/common/Lossless Scaling/Lossless.dll"
DLL_DIR="/storage/.local/share/Steam/steamapps/common/Lossless Scaling"
if [ -f "$DLL_SRC" ]; then
    mkdir -p "$DLL_DIR"
    ln -sf "$DLL_SRC" "$DLL_DIR/Lossless.dll"
fi

log "Done! Use: ~/lsfg %command%"
