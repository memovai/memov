#!/bin/bash
# Start the visual history browser
# Usage: ./ui_start.sh [--port 38888] [--foreground] [--loc /path]

echo "Starting memov UI via: mem ui start ..."
echo "Tip: if you're using Claude Code MCP, you can also open via mcp__mem-mcp__mem_ui"
echo ""

source "$(dirname "$0")/_check_deps.sh" && check_memov

mem ui start "$@"
