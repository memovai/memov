#!/bin/bash
# Stop the web UI server
# Usage: ./ui_stop.sh

source "$(dirname "$0")/_check_deps.sh" && check_memov

mem ui stop "$@"
