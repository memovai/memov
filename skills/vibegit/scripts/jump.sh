#!/bin/bash
# Jump to a specific snapshot
# Usage: ./jump.sh <commit_hash>

source "$(dirname "$0")/_check_deps.sh" && check_memov

if [ -z "$1" ]; then
    echo "Usage: ./jump.sh <commit_hash>"
    exit 1
fi

mem jump "$1"
