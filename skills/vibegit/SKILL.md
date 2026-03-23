---
name: vibegit
description: "AI-assisted version control using the Memov CLI (`mem`). Create snapshots of AI coding sessions, track file changes with prompts and responses, view interaction history, and time-travel to previous states. Use when the user mentions Memov, wants to record AI code changes, needs to review AI-assisted modifications, or asks to track prompts and responses for coding sessions."
---

# VibeGit - AI Coding History

Record AI coding sessions as snapshots using the Memov CLI. Each snapshot captures the prompt, response, changed files, and diffs.

## Prerequisites

The `memov` Python package provides the `mem` CLI command.

```bash
# Install
curl -fsSL https://raw.githubusercontent.com/memovai/memov/main/install.sh | bash

# Verify
mem

# Initialize in a project
mem init
```

## Usage Modes

1. **Skill scripts**: run `./scripts/*.sh` — thin wrappers over `mem` CLI.
2. **MCP tools (Claude Code)**: use tools like `mcp__mem-mcp__snap` — may add extra behavior (auto-track untracked files, auto-sync for RAG).

## Core Operations

| Script | Description | Usage |
|--------|-------------|-------|
| `init.sh` | Initialize memov in a project | `./scripts/init.sh` |
| `track.sh` | Track new files | `./scripts/track.sh file1.py file2.py -p "..." -r "..."` |
| `snap.sh` | Record a code change | `./scripts/snap.sh --files "file1.py,file2.py" -p "What was asked" -r "What was done"` |
| `history.sh` | View AI coding history | `./scripts/history.sh [--limit 20]` |
| `show.sh` | Show commit details | `./scripts/show.sh <commit_hash>` |
| `status.sh` | Check working directory status | `./scripts/status.sh` |

### Snap Parameters

- `--files`: Comma-separated list of modified files
- `--prompt` or `-p`: The user's original request
- `--response` or `-r`: Summary of what was done
- `--by-user` or `-u`: Mark as human edit (vs AI)

### Verify a Snapshot

After recording, confirm it was captured:

```bash
./scripts/history.sh --limit 1
```

## Navigation

| Script | Description | Usage |
|--------|-------------|-------|
| `jump.sh` | Jump to a specific snapshot | `./scripts/jump.sh <commit_hash>` |
| `branch.sh` | List/create/delete branches | `./scripts/branch.sh [name] [--delete name]` |
| `switch.sh` | Switch branches | `./scripts/switch.sh <branch_name>` |

## Web UI

Before starting, confirm the target project directory. If unsure, run `pwd` and pass `--loc <path>`.

| Script | Description | Usage |
|--------|-------------|-------|
| `ui_start.sh` | Start visual history browser | `./scripts/ui_start.sh [--loc /path] [--port 38888] [--foreground]` |
| `ui_stop.sh` | Stop the web server | `./scripts/ui_stop.sh [--loc /path]` |
| `ui_status.sh` | Check server status | `./scripts/ui_status.sh [--loc /path]` |

## Examples

### Record a bug fix

```bash
./scripts/snap.sh \
  --files "auth.py" \
  --prompt "Fix null pointer in login" \
  --response "Added null check for user object at L45"
```

### Record a feature addition

```bash
./scripts/snap.sh \
  --files "api.py,tests/test_api.py" \
  --prompt "Add authentication endpoint" \
  --response "Added /login POST endpoint with JWT token generation"
```

### View recent history

```bash
./scripts/history.sh --limit 10
```

### Jump to previous state

```bash
./scripts/jump.sh a1b2c3d
```

## RAG Features (Optional)

Semantic search, validate, and vibe_debug/vibe_search tools require extra dependencies:

```bash
pip install memov[rag]
mem sync
```

## Troubleshooting

### "memov CLI not found" error

```bash
./install.sh
# Or: pip install memov
```

### Scripts not executable

```bash
chmod +x scripts/*.sh install.sh
```
