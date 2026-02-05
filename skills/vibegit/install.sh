#!/bin/bash
# Install memov CLI
# Delegates to the official installation script

set -e

echo "Installing memov..."

# Check if already installed
if command -v mem &> /dev/null; then
    echo "memov is already installed!"
    mem 2>/dev/null || true
    exit 0
fi

# Use official install script
curl -fsSL https://raw.githubusercontent.com/memovai/memov/main/install.sh | bash
