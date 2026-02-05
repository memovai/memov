#!/bin/bash
# Check web UI server status
# Usage: ./ui_status.sh [--loc /path]
#
# Note: UI status is managed by MCP server in Claude Code.

echo "Web UI status is managed by MCP server."
echo "Check if a browser tab is open with the memov UI."


source "$(dirname "$0")/_check_deps.sh" && check_memov

mem ui status "$@"
