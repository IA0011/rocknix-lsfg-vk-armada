#!/bin/sh
# LSFG-VK ARM64 native installer (via FEX Vulkan thunks)
#
# Follows same pattern as main branch install.sh:
#   1. Downloads ARM64 liblsfg-vk .so to /storage/.config/lsfg-vk/lib/
#   2. Deploys manifest to pressure-vessel overrides path
#   3. Enables FEX Vulkan thunks (+ persists in system.cfg)
#   4. Installs the lsfg launch wrapper

set -euo pipefail

LSFG_SO_URL="${LSFG_SO_URL:-https://github.com/seilent/lsfg-vk/releases/download/latest/lsfg-vk-arm64.tar.gz}"
LSFG_DIR="/storage/.config/lsfg-vk"
BIN_DIR="${LSFG_DIR}/bin"
SRC_DIR="${LSFG_DIR}/lib"
GAMES_DIR="${LSFG_DIR}/games"
FEX_CONFIG="/storage/.config/fex-emu/Config.json"
SYSTEM_CFG="/storage/.config/system/configs/system.cfg"
MANIFEST_DIR="/storage/.config/lsfg-vk/manifests"
TMP_DIR="/tmp/lsfg-vk-install"

log() { echo "[lsfg-vk-arm64] $*"; }

# Check architecture
if [ "$(uname -m)" != "aarch64" ]; then
    log "ERROR: This script is for aarch64 only (got: $(uname -m))"
    exit 1
fi

# Create directories
mkdir -p "${BIN_DIR}" "${SRC_DIR}" "${GAMES_DIR}" "${MANIFEST_DIR}" "${TMP_DIR}"

# Create default config if not present
if [ ! -f "${LSFG_DIR}/default.json" ]; then
    echo '{"multiplier": 2, "fps_limit": 30, "flow_scale": 0.3, "performance_mode": 1}' > "${LSFG_DIR}/default.json"
fi

# Download ARM64 .so
log "Downloading ARM64 liblsfg-vk..."
curl -sSL "${LSFG_SO_URL}" -o "${TMP_DIR}/lsfg-vk-arm64.tar.gz"
tar -xzf "${TMP_DIR}/lsfg-vk-arm64.tar.gz" -C "${TMP_DIR}"
cp "${TMP_DIR}/liblsfg-vk-arm64.so" "${SRC_DIR}/liblsfg-vk-arm64.so"
rm -rf "${TMP_DIR}"

# Deploy layer manifest
log "Installing layer manifest..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "${SCRIPT_DIR}/defaults/VkLayer_LS_frame_generation.json" ]; then
    cp "${SCRIPT_DIR}/defaults/VkLayer_LS_frame_generation.json" "${MANIFEST_DIR}/VkLayer_LS_frame_generation_arm64.json"
else
    cat > "${MANIFEST_DIR}/VkLayer_LS_frame_generation_arm64.json" << EOF
{
    "file_format_version": "1.0.0",
    "layer": {
        "name": "VK_LAYER_LSFGVK_frame_generation",
        "type": "GLOBAL",
        "library_path": "${SRC_DIR}/liblsfg-vk-arm64.so",
        "api_version": "1.4.328",
        "implementation_version": "2",
        "description": "LSFG frame generation (ARM64 native)",
        "enable_environment": { "LSFG_ENABLE": "1" },
        "disable_environment": { "DISABLE_LSFGVK": "1" }
    }
}
EOF
fi
# Update library_path in manifest to point to our writable location
sed -i "s|\"library_path\":.*|\"library_path\": \"${SRC_DIR}/liblsfg-vk-arm64.so\",|" \
    "${MANIFEST_DIR}/VkLayer_LS_frame_generation_arm64.json"

# Deploy manifest to pressure-vessel overrides (recreated on each boot since /usr is read-only)
PV_LAYER_DIR="/usr/lib/pressure-vessel/overrides/share/vulkan/implicit_layer.d"
mkdir -p "${PV_LAYER_DIR}" 2>/dev/null || true
cp "${MANIFEST_DIR}/VkLayer_LS_frame_generation_arm64.json" "${PV_LAYER_DIR}/" 2>/dev/null || true

# Create setup script that re-deploys on boot (since /usr/lib is tmpfs)
cat > "${BIN_DIR}/lsfg-vk-setup" << 'SETUP'
#!/bin/sh
LSFG_DIR="/storage/.config/lsfg-vk"
PV_DIR="/usr/lib/pressure-vessel/overrides/share/vulkan/implicit_layer.d"
mkdir -p "$PV_DIR"
cp "${LSFG_DIR}/manifests/VkLayer_LS_frame_generation_arm64.json" "$PV_DIR/"
SETUP
chmod +x "${BIN_DIR}/lsfg-vk-setup"

# Install systemd service to run setup on boot
mkdir -p /storage/.config/system.d/multi-user.target.wants
cat > /storage/.config/system.d/lsfg-vk-arm64.service << EOF
[Unit]
Description=Deploy LSFG-VK ARM64 layer manifest
After=local-fs.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=${BIN_DIR}/lsfg-vk-setup

[Install]
WantedBy=multi-user.target
EOF
ln -sf /storage/.config/system.d/lsfg-vk-arm64.service \
    /storage/.config/system.d/multi-user.target.wants/lsfg-vk-arm64.service

# Enable FEX Vulkan thunks
log "Enabling FEX Vulkan thunks..."
mkdir -p "$(dirname "${FEX_CONFIG}")"
if [ -f "${FEX_CONFIG}" ]; then
    python3 -c "
import json
with open('${FEX_CONFIG}', 'r') as f:
    cfg = json.load(f)
if 'ThunksDB' not in cfg:
    cfg['ThunksDB'] = {}
cfg['ThunksDB']['Vulkan'] = 1
with open('${FEX_CONFIG}', 'w') as f:
    json.dump(cfg, f, indent=2)
"
else
    cat > "${FEX_CONFIG}" << 'EOF'
{
  "ThunksDB": {
    "Vulkan": 1
  }
}
EOF
fi

# Persist thunks setting so it survives reboot
if grep -q "steam.vulkan_host_library" "$SYSTEM_CFG" 2>/dev/null; then
    sed -i "s/steam.vulkan_host_library=.*/steam.vulkan_host_library=1/" "$SYSTEM_CFG"
else
    echo "steam.vulkan_host_library=1" >> "$SYSTEM_CFG"
fi

# Install wrapper script
log "Installing lsfg wrapper..."
if [ -f "${SCRIPT_DIR}/defaults/lsfg" ]; then
    cp "${SCRIPT_DIR}/defaults/lsfg" "${BIN_DIR}/lsfg"
else
    curl -sSL "https://raw.githubusercontent.com/seilent/rocknix-lsfg-vk/arm64-thunks/defaults/lsfg" -o "${BIN_DIR}/lsfg"
fi
chmod +x "${BIN_DIR}/lsfg"
cp "${BIN_DIR}/lsfg" ~/lsfg
chmod +x ~/lsfg

# Create Lossless.dll symlink for standard path discovery
DLL_SRC="/storage/games-internal/roms/steam/steamapps/common/Lossless Scaling/Lossless.dll"
DLL_DST="/storage/.local/share/Steam/steamapps/common/Lossless Scaling"
if [ -f "$DLL_SRC" ]; then
    mkdir -p "$DLL_DST"
    ln -sf "$DLL_SRC" "$DLL_DST/Lossless.dll"
fi

log ""
log "Installation complete!"
log "  Layer: ${SRC_DIR}/liblsfg-vk-arm64.so"
log "  Manifest: ${PV_LAYER_DIR}/"
log "  Thunks: enabled"
log ""
log "Usage: Set Steam launch options to:"
log "  ~/lsfg %command%"
