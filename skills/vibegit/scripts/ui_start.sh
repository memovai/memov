#!/bin/bash
# Start the visual history browser
# Usage: ./ui_start.sh [--port 38888]

source "$(dirname "$0")/_check_deps.sh" && check_memov

mem ui start "$@"
