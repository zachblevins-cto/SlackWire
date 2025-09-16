#!/bin/bash

# SlackWire Service Installation Script

echo "🤖 Installing SlackWire as a system service..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Get the actual user who called sudo
ACTUAL_USER=${SUDO_USER:-$USER}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing for user: $ACTUAL_USER"
echo "Working directory: $SCRIPT_DIR"

# Update the service file with correct user
sed -i "s/User=zachary/User=$ACTUAL_USER/g" "$SCRIPT_DIR/slackwire.service"
sed -i "s/Group=zachary/Group=$ACTUAL_USER/g" "$SCRIPT_DIR/slackwire.service"
sed -i "s|/home/zachary|/home/$ACTUAL_USER|g" "$SCRIPT_DIR/slackwire.service"

# Kill any existing bot process
echo "Stopping any existing bot process..."
pkill -f "python3.*main.py" || true

# Copy service file to systemd
echo "Installing systemd service..."
cp "$SCRIPT_DIR/slackwire.service" /etc/systemd/system/

# Reload systemd
systemctl daemon-reload

# Enable service to start on boot
echo "Enabling service to start on boot..."
systemctl enable slackwire.service

# Start the service
echo "Starting SlackWire service..."
systemctl start slackwire.service

# Check status
sleep 2
if systemctl is-active --quiet slackwire.service; then
    echo "✅ SlackWire service is running!"
    echo ""
    echo "Useful commands:"
    echo "  Check status:  sudo systemctl status slackwire"
    echo "  View logs:     sudo journalctl -u slackwire -f"
    echo "  Stop service:  sudo systemctl stop slackwire"
    echo "  Start service: sudo systemctl start slackwire"
    echo "  Disable:       sudo systemctl disable slackwire"
else
    echo "❌ Service failed to start. Check logs with:"
    echo "  sudo systemctl status slackwire"
    echo "  sudo journalctl -u slackwire -n 50"
fi