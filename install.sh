#!/usr/bin/env bash
# install.sh — installs freefox as a systemd service
set -euo pipefail

INSTALL_PREFIX="${INSTALL_PREFIX:-/usr/local}"
CONFIG_DIR="${CONFIG_DIR:-/etc/freefox}"
DATA_DIR="${DATA_DIR:-/var/lib/freefox}"

# Use the invoking sudo user by default, fallback to current user.
DEFAULT_USER="${SUDO_USER:-$(id -un)}"
SERVICE_USER="${SERVICE_USER:-$DEFAULT_USER}"
SERVICE_GROUP="${SERVICE_GROUP:-$(id -gn "$SERVICE_USER")}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Installing freefox"
echo "  Service user:  $SERVICE_USER"
echo "  Service group: $SERVICE_GROUP"

# Must run as root for /etc, /var/lib and systemd install.
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Please run this script with sudo:"
    echo "  sudo ./install.sh"
    exit 1
fi

# Validate user/group
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    echo "ERROR: user '$SERVICE_USER' does not exist."
    echo "Create it first, or run with:"
    echo "  sudo SERVICE_USER=$DEFAULT_USER ./install.sh"
    exit 1
fi

if ! getent group "$SERVICE_GROUP" >/dev/null 2>&1; then
    echo "ERROR: group '$SERVICE_GROUP' does not exist."
    echo "Create it first, or set SERVICE_GROUP to an existing group."
    exit 1
fi

# Install Python package
python3 -m pip install --break-system-packages -e "$SCRIPT_DIR"

# Create directories
install -d -m 755 "$CONFIG_DIR"
install -d -m 755 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$DATA_DIR"

# Copy example config if none exists
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    install -m 640 -o root -g "$SERVICE_GROUP" \
        "$SCRIPT_DIR/config/config.example.yaml" \
        "$CONFIG_DIR/config.yaml"

    echo "  Config written to $CONFIG_DIR/config.yaml — edit before starting!"
fi

# Install systemd unit
install -m 644 "$SCRIPT_DIR/systemd/freefox.service" /etc/systemd/system/freefox.service

sed -i "s/^User=.*/User=$SERVICE_USER/" /etc/systemd/system/freefox.service
sed -i "s/^Group=.*/Group=$SERVICE_GROUP/" /etc/systemd/system/freefox.service

systemctl daemon-reload

echo ""
echo "==> Done. Next steps:"
echo "  1. Edit $CONFIG_DIR/config.yaml"
echo "  2. Place credentials.json in $CONFIG_DIR/"
echo "  3. sudo systemctl enable --now freefox"
echo "  4. journalctl -u freefox -f"