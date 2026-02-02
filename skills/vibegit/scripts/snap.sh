#!/bin/bash
# Record a code change snapshot
# Usage: ./snap.sh --files "file1.py,file2.py" --prompt "What was asked" --response "What was done"

source "$(dirname "$0")/_check_deps.sh" && check_memov

FILES=""
PROMPT=""
RESPONSE=""
BY_USER=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --files)
            FILES="$2"
            shift 2
            ;;
        -p|--prompt)
            PROMPT="$2"
            shift 2
            ;;
        -r|--response)
            RESPONSE="$2"
            shift 2
            ;;
        -u|--by-user)
            BY_USER="--by_user"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

CMD="mem snap"

if [ -n "$FILES" ]; then
    CMD="$CMD --files $FILES"
fi

if [ -n "$PROMPT" ]; then
    CMD="$CMD -p \"$PROMPT\""
fi

if [ -n "$RESPONSE" ]; then
    CMD="$CMD -r \"$RESPONSE\""
fi

if [ -n "$BY_USER" ]; then
    CMD="$CMD $BY_USER"
fi

eval $CMD
