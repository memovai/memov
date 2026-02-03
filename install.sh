#!/bin/bash
#
# MEM Installation Script
# https://github.com/memovai/memov
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/memovai/memov/main/install.sh | bash
#   wget -qO- https://raw.githubusercontent.com/memovai/memov/main/install.sh | bash
#
# Environment variables:
#   MEM_VERSION   - Specific version to install (default: latest)
#   MEM_INSTALL_DIR - Binary/symlink directory (default: /usr/local/bin)
#   MEM_LIB_DIR   - Library directory for onedir mode (default: /usr/local/lib/mem)
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
GITHUB_REPO="memovai/memov"
BINARY_NAME="mem"
INSTALL_DIR="${MEM_INSTALL_DIR:-/usr/local/bin}"
LIB_DIR="${MEM_LIB_DIR:-/usr/local/lib/mem}"

# Functions
info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Detect OS and architecture
detect_platform() {
    local os arch

    case "$(uname -s)" in
        Linux*)  os="linux" ;;
        Darwin*) os="macos" ;;
        MINGW*|MSYS*|CYGWIN*) os="windows" ;;
        *)       error "Unsupported operating system: $(uname -s)" ;;
    esac

    case "$(uname -m)" in
        x86_64|amd64) arch="x86_64" ;;
        arm64|aarch64) arch="arm64" ;;
        *)            error "Unsupported architecture: $(uname -m)" ;;
    esac

    # macOS ARM uses arm64
    if [ "$os" = "macos" ] && [ "$arch" = "x86_64" ]; then
        # Check if running under Rosetta 2
        if [ "$(sysctl -n sysctl.proc_translated 2>/dev/null)" = "1" ]; then
            arch="arm64"
        fi
    fi

    echo "${os}-${arch}"
}

# Get latest version from GitHub
get_latest_version() {
    local version
    version=$(curl -fsSL "https://api.github.com/repos/${GITHUB_REPO}/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
    if [ -z "$version" ]; then
        error "Failed to get latest version from GitHub"
    fi
    echo "$version"
}

# Download and install
install_mem() {
    local platform version download_url temp_dir archive_name binary_path is_onedir

    platform=$(detect_platform)
    info "Detected platform: $platform"

    # Get version
    if [ -n "$MEM_VERSION" ]; then
        version="v${MEM_VERSION#v}"
        info "Installing specified version: $version"
    else
        version=$(get_latest_version)
        info "Installing latest version: $version"
    fi

    # Determine download URL and type
    # We use onedir mode for better startup performance on macOS
    is_onedir=true
    case "$platform" in
        linux-x86_64)
            archive_name="mem-linux-x86_64.tar.gz"
            ;;
        linux-arm64)
            archive_name="mem-linux-arm64.tar.gz"
            ;;
        macos-x86_64)
            archive_name="mem-macos-x86_64.tar.gz"
            ;;
        macos-arm64)
            archive_name="mem-macos-arm64.tar.gz"
            ;;
        windows-x86_64)
            archive_name="mem-windows-x86_64.zip"
            ;;
        *)
            error "No binary available for platform: $platform"
            ;;
    esac

    download_url="https://github.com/${GITHUB_REPO}/releases/download/${version}/${archive_name}"
    info "Downloading from: $download_url"

    # Create temp directory
    temp_dir=$(mktemp -d)
    trap "rm -rf $temp_dir" EXIT

    # Download
    if command -v curl &>/dev/null; then
        curl -fsSL "$download_url" -o "$temp_dir/$archive_name"
    elif command -v wget &>/dev/null; then
        wget -q "$download_url" -O "$temp_dir/$archive_name"
    else
        error "Neither curl nor wget found. Please install one of them."
    fi

    # Extract
    cd "$temp_dir"
    case "$archive_name" in
        *.tar.gz)
            tar -xzf "$archive_name"
            ;;
        *.zip)
            unzip -q "$archive_name"
            ;;
    esac

    # Detect if this is onedir (has mem/ directory) or single binary
    if [ -d "mem" ] && [ -f "mem/mem" ]; then
        # onedir mode - directory with mem/mem binary and mem/_internal/
        info "Detected onedir package (fast startup mode)"
        install_onedir "$temp_dir/mem"
    elif [ -d "mem" ] && [ -f "mem/_internal" ]; then
        # onedir mode variant
        info "Detected onedir package (fast startup mode)"
        install_onedir "$temp_dir/mem"
    else
        # Single binary mode (legacy or shiv)
        binary_path=$(find . -type f \( -name "mem" -o -name "mem-*" \) ! -name "*.tar.gz" ! -name "*.zip" | head -1)
        if [ -z "$binary_path" ] || [ ! -f "$binary_path" ]; then
            error "Failed to find binary in archive"
        fi
        info "Detected single binary package"
        install_single_binary "$binary_path"
    fi

    # Verify installation
    verify_installation
}

# Install onedir package (directory with binary + libraries)
install_onedir() {
    local source_dir="$1"

    info "Installing to $LIB_DIR (library files)"
    info "Creating symlink at $INSTALL_DIR/$BINARY_NAME"

    # Remove old installation if exists
    if [ -d "$LIB_DIR" ]; then
        warn "Removing old installation at $LIB_DIR"
        if [ -w "$(dirname "$LIB_DIR")" ]; then
            rm -rf "$LIB_DIR"
        else
            sudo rm -rf "$LIB_DIR"
        fi
    fi

    # Remove old symlink if exists
    if [ -L "$INSTALL_DIR/$BINARY_NAME" ] || [ -f "$INSTALL_DIR/$BINARY_NAME" ]; then
        if [ -w "$INSTALL_DIR" ]; then
            rm -f "$INSTALL_DIR/$BINARY_NAME"
        else
            sudo rm -f "$INSTALL_DIR/$BINARY_NAME"
        fi
    fi

    # Install library directory (ensure parent exists)
    if [ -w "$(dirname "$LIB_DIR")" ]; then
        mkdir -p "$(dirname "$LIB_DIR")"
        cp -r "$source_dir" "$LIB_DIR"
        chmod +x "$LIB_DIR/mem"
    else
        warn "Need sudo to install to $LIB_DIR"
        sudo mkdir -p "$(dirname "$LIB_DIR")"
        sudo cp -r "$source_dir" "$LIB_DIR"
        sudo chmod +x "$LIB_DIR/mem"
    fi

    # Create symlink
    if [ -w "$INSTALL_DIR" ]; then
        ln -sf "$LIB_DIR/mem" "$INSTALL_DIR/$BINARY_NAME"
    else
        sudo ln -sf "$LIB_DIR/mem" "$INSTALL_DIR/$BINARY_NAME"
    fi

    success "Installed library to: $LIB_DIR"
    success "Created symlink: $INSTALL_DIR/$BINARY_NAME -> $LIB_DIR/mem"
}

# Install single binary (legacy mode or shiv)
install_single_binary() {
    local binary_path="$1"

    info "Installing to $INSTALL_DIR/$BINARY_NAME"

    if [ -w "$INSTALL_DIR" ]; then
        mv "$binary_path" "$INSTALL_DIR/$BINARY_NAME"
        chmod +x "$INSTALL_DIR/$BINARY_NAME"
    else
        warn "Need sudo to install to $INSTALL_DIR"
        sudo mv "$binary_path" "$INSTALL_DIR/$BINARY_NAME"
        sudo chmod +x "$INSTALL_DIR/$BINARY_NAME"
    fi
}

# Verify installation
verify_installation() {
    if command -v "$BINARY_NAME" &>/dev/null; then
        success "MEM installed successfully!"
        echo ""
        "$INSTALL_DIR/$BINARY_NAME" version 2>/dev/null || "$INSTALL_DIR/$BINARY_NAME" --version 2>/dev/null || true
        echo ""
        info "Run 'mem --help' to get started"

        # Show startup time hint for first run
        echo ""
        info "Note: First run may take a few seconds (macOS security scan)."
        info "Subsequent runs will be fast (~0.2s)."
    else
        warn "MEM installed to $INSTALL_DIR/$BINARY_NAME but not in PATH"
        info "Add $INSTALL_DIR to your PATH or run: $INSTALL_DIR/$BINARY_NAME --help"
    fi
}

# Main
main() {
    echo ""
    echo "  ███╗   ███╗███████╗███╗   ███╗ ██████╗ ██╗   ██╗"
    echo "  ████╗ ████║██╔════╝████╗ ████║██╔═══██╗██║   ██║"
    echo "  ██╔████╔██║█████╗  ██╔████╔██║██║   ██║██║   ██║"
    echo "  ██║╚██╔╝██║██╔══╝  ██║╚██╔╝██║██║   ██║╚██╗ ██╔╝"
    echo "  ██║ ╚═╝ ██║███████╗██║ ╚═╝ ██║╚██████╔╝ ╚████╔╝ "
    echo "  ╚═╝     ╚═╝╚══════╝╚═╝     ╚═╝ ╚═════╝   ╚═══╝  "
    echo ""
    echo "  MemoV = Prompt + Agent Plan + CodeDiff"
    echo "  All auto-captured as you flow."
    echo ""
    echo "  Traceable memory for AI coding agents."
    echo ""

    install_mem
}

main "$@"
