#!/bin/bash
# View AI coding history
# Usage: ./history.sh [--limit 20]

source "$(dirname "$0")/_check_deps.sh" && check_memov

mem history "$@"
