#!/bin/bash
# Switch to a branch
# Usage: ./switch.sh <branch_name>

source "$(dirname "$0")/_check_deps.sh" && check_memov

if [ -z "$1" ]; then
    echo "Usage: ./switch.sh <branch_name>"
    exit 1
fi

mem switch "$1"
