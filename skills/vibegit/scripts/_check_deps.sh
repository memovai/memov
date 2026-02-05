#!/bin/bash
# Shared dependency check for VibeGit scripts

check_memov() {
    if ! command -v mem &> /dev/null; then
        echo "Error: memov CLI not found"
        echo ""
        echo "Install with:"
        echo "  curl -fsSL https://raw.githubusercontent.com/memovai/memov/main/install.sh | bash"
        echo ""
        echo "Or alternatives:"
        echo "  uvx memov          # Run without install"
        echo "  pip install memov  # Global install"
        echo "  pipx install memov # Isolated install"
        exit 1
    fi
}
