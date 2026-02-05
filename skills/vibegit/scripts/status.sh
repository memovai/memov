#!/bin/bash
# Show working directory status
# Usage: ./status.sh

source "$(dirname "$0")/_check_deps.sh" && check_memov

mem status "$@"
