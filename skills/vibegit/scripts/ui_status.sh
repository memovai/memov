#!/bin/bash
# Check web UI server status
# Usage: ./ui_status.sh

source "$(dirname "$0")/_check_deps.sh" && check_memov

mem ui status "$@"
