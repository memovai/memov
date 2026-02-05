#!/bin/bash
# Track files for version control
# Usage: ./track.sh file1.py file2.py [-p "prompt"] [-r "response"]

source "$(dirname "$0")/_check_deps.sh" && check_memov

mem track "$@"
