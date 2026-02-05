#!/bin/bash
# List, create, or delete branches
# Usage: ./branch.sh [name] [--delete name]

source "$(dirname "$0")/_check_deps.sh" && check_memov

mem branch "$@"
