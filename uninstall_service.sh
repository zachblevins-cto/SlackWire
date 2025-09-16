#!/bin/bash

# SlackWire Service Uninstallation Script

echo "🤖 Uninstalling SlackWire service..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Stop the service
echo "Stopping SlackWire service..."
systemctl stop slackwire.service

# Disable the service
echo "Disabling service..."
systemctl disable slackwire.service

# Remove service file
echo "Removing service file..."
rm -f /etc/systemd/system/slackwire.service

# Reload systemd
systemctl daemon-reload

echo "✅ SlackWire service has been uninstalled"
echo ""
echo "The bot files are still in the directory and can be run manually with:"
echo "  python3 main.py"