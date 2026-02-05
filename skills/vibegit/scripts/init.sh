#!/bin/bash
# Initialize memov in the current directory
# Usage: ./init.sh [--loc /path/to/project]

source "$(dirname "$0")/_check_deps.sh" && check_memov

mem init "$@"
