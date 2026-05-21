#!/bin/sh
# LSFG-VK ARM64 native installer (via FEX Vulkan thunks)
#
# Instead of deploying into FEX RootFS, this installs an ARM64-native layer
# on the host system. With Vulkan thunks enabled, x86_64 game Vulkan calls
# route through the native ARM64 loader, so the host layer intercepts frames.
#
# Usage: sh install-arm64.sh

set -euo pipefail

LSFG_SO_URL="${LSFG_SO_URL:-https://github.com/seilent/lsfg-vk/releases/download/latest/lsfg-vk-arm64.tar.gz}"
LSFG_DIR="/storage/.config/lsfg-vk"
FEX_CONFIG="/storage/.config/fex-emu/Config.json"
LAYER_JSON="/usr/lib/pressure-vessel/overrides/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation.json"
LAYER_SO="/usr/lib/liblsfg-vk-arm64.so"

log() { echo "[lsfg-vk-arm64] $*"; }

# Check architecture
if [ "$(uname -m)" != "aarch64" ]; then
    log "ERROR: This script is for aarch64 only (got: $(uname -m))"
    exit 1
fi

# Download ARM64 .so
log "Downloading ARM64 liblsfg-vk..."
curl -sSL "${LSFG_SO_URL}" -o /tmp/lsfg-vk-arm64.tar.gz
tar -xzf /tmp/lsfg-vk-arm64.tar.gz -C /tmp liblsfg-vk-arm64.so
install -D -m 0644 /tmp/liblsfg-vk-arm64.so "${LAYER_SO}"
rm -f /tmp/lsfg-vk-arm64.tar.gz /tmp/liblsfg-vk-arm64.so

# Deploy layer JSON
log "Installing layer manifest..."
mkdir -p "$(dirname "${LAYER_JSON}")"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "${SCRIPT_DIR}/defaults/VkLayer_LS_frame_generation.json" ]; then
    install -m 0644 "${SCRIPT_DIR}/defaults/VkLayer_LS_frame_generation.json" "${LAYER_JSON}"
else
    cat > "${LAYER_JSON}" << 'EOF'
{
    "file_format_version": "1.0.0",
    "layer": {
        "name": "VK_LAYER_LS_frame_generation",
        "type": "GLOBAL",
        "library_path": "/usr/lib/liblsfg-vk-arm64.so",
        "api_version": "1.3.0",
        "implementation_version": "1",
        "description": "LSFG frame generation (ARM64 native via thunks)",
        "enable_environment": { "LSFG_ENABLE": "1" },
        "disable_environment": { "DISABLE_LSFG": "1" }
    }
}
EOF
fi

# Enable FEX Vulkan thunks
log "Enabling FEX Vulkan thunks..."
mkdir -p "$(dirname "${FEX_CONFIG}")"
if [ -f "${FEX_CONFIG}" ]; then
    # Use python to safely modify JSON
    python3 -c "
import json, sys
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

# Persist thunks setting so it survives reboot (ROCKNIX start_steam.sh reads this)
SYSTEM_CFG="/storage/.config/system/configs/system.cfg"
if grep -q "steam.vulkan_host_library" "$SYSTEM_CFG" 2>/dev/null; then
    sed -i "s/steam.vulkan_host_library=.*/steam.vulkan_host_library=1/" "$SYSTEM_CFG"
else
    echo "steam.vulkan_host_library=1" >> "$SYSTEM_CFG"
fi

# Create wrapper script
log "Creating lsfg wrapper..."
mkdir -p "${LSFG_DIR}/bin"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "${SCRIPT_DIR}/defaults/lsfg" ]; then
    cp "${SCRIPT_DIR}/defaults/lsfg" "${LSFG_DIR}/bin/lsfg"
else
    curl -sSL "https://raw.githubusercontent.com/seilent/rocknix-lsfg-vk/arm64-thunks/defaults/lsfg" -o "${LSFG_DIR}/bin/lsfg"
fi
chmod +x "${LSFG_DIR}/bin/lsfg"
ln -sf "${LSFG_DIR}/bin/lsfg" ~/lsfg

# Create systemd service
log "Installing systemd service..."
mkdir -p /storage/.config/system.d/multi-user.target.wants
cat > /storage/.config/system.d/lsfg-vk-arm64.service << EOF
[Unit]
Description=Ensure LSFG-VK ARM64 layer is deployed
After=local-fs.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c '[ -f ${LAYER_SO} ] || echo "[lsfg-vk] WARNING: layer .so missing"'

[Install]
WantedBy=multi-user.target
EOF
ln -sf /storage/.config/system.d/lsfg-vk-arm64.service \
    /storage/.config/system.d/multi-user.target.wants/lsfg-vk-arm64.service

# Default config
if [ ! -f "${LSFG_DIR}/default.json" ]; then
    echo '{"multiplier": 2, "fps_limit": 30, "flow_scale": 0.3, "performance_mode": 1}' > "${LSFG_DIR}/default.json"
fi

log ""
log "Installation complete!"
log "  Layer: ${LAYER_SO}"
log "  Manifest: ${LAYER_JSON}"
log "  Thunks: enabled in ${FEX_CONFIG}"
log ""
log "Usage: Set Steam launch options to:"
log "  /storage/.config/lsfg-vk/bin/lsfg %command%"
