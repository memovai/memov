#!/bin/bash
# Show details of a specific commit
# Usage: ./show.sh <commit_hash>

source "$(dirname "$0")/_check_deps.sh" && check_memov

if [ -z "$1" ]; then
    echo "Usage: ./show.sh <commit_hash>"
    exit 1
fi

mem show "$1"
