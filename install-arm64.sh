#!/bin/sh
# LSFG-VK ARM64 installer
# Same pattern as main branch: downloads .so, deploys to FEX RootFS, installs wrapper.
# With thunks enabled, the native ARM64 loader finds the layer in FEX RootFS paths.

set -euo pipefail

LSFG_SO_URL="${LSFG_SO_URL:-https://github.com/seilent/lsfg-vk/releases/download/latest/lsfg-vk-arm64.tar.gz}"
LSFG_DIR="/storage/.config/lsfg-vk"
BIN_DIR="${LSFG_DIR}/bin"
SRC_DIR="${LSFG_DIR}/lib"
GAMES_DIR="${LSFG_DIR}/games"
FEX_ROOTFS="/storage/.local/share/fex-emu/RootFS/ArchLinux"
FEX_CONFIG="/storage/.config/fex-emu/Config.json"
TMP_DIR="/tmp/lsfg-vk-install"

log() { echo "[lsfg-vk-arm64] $*"; }

if [ "$(uname -m)" != "aarch64" ]; then
    log "ERROR: aarch64 only"; exit 1
fi

# Create directories
mkdir -p "${BIN_DIR}" "${SRC_DIR}" "${GAMES_DIR}" "${TMP_DIR}"

# Default config
[ -f "${LSFG_DIR}/default.json" ] || echo '{"multiplier": 2, "fps_limit": 30, "flow_scale": 0.3, "performance_mode": 1}' > "${LSFG_DIR}/default.json"

# Download ARM64 .so
log "Downloading ARM64 liblsfg-vk..."
curl -sSL "${LSFG_SO_URL}" -o "${TMP_DIR}/lsfg-vk-arm64.tar.gz"
tar -xzf "${TMP_DIR}/lsfg-vk-arm64.tar.gz" -C "${TMP_DIR}"
cp "${TMP_DIR}/liblsfg-vk-arm64.so" "${SRC_DIR}/liblsfg-vk-arm64.so"
rm -rf "${TMP_DIR}"

# Deploy to FEX RootFS (same pattern as main branch)
if [ -d "$FEX_ROOTFS" ]; then
    log "Deploying layer into FEX RootFS..."
    install -D -m 0644 "${SRC_DIR}/liblsfg-vk-arm64.so" "${FEX_ROOTFS}/usr/lib/liblsfg-vk-arm64.so"

    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    if [ -f "${SCRIPT_DIR}/defaults/VkLayer_LS_frame_generation.json" ]; then
        install -D -m 0644 "${SCRIPT_DIR}/defaults/VkLayer_LS_frame_generation.json" \
            "${FEX_ROOTFS}/usr/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation_arm64.json"
    else
        cat > "${FEX_ROOTFS}/usr/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation_arm64.json" << EOF
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
else
    log "WARNING: FEX RootFS not found at ${FEX_ROOTFS}"
fi

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

# Create Lossless.dll symlink
DLL_SRC="/storage/games-internal/roms/steam/steamapps/common/Lossless Scaling/Lossless.dll"
DLL_DIR="/storage/.local/share/Steam/steamapps/common/Lossless Scaling"
if [ -f "$DLL_SRC" ]; then
    mkdir -p "$DLL_DIR"
    ln -sf "$DLL_SRC" "$DLL_DIR/Lossless.dll"
fi

log "Done! Use: ~/lsfg %command%"
