#!/bin/bash
# Stop the web UI server
# Usage: ./ui_stop.sh [--loc /path]
#
# Note: When using MCP UI, simply close the browser tab.
# The server auto-terminates after inactivity.

echo "Web UI runs through MCP server."
echo "To stop: close the browser tab or terminate the MCP server."

source "$(dirname "$0")/_check_deps.sh" && check_memov

mem ui stop "$@"
