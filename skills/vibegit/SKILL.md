# VibeGit - AI Coding History

AI-assisted version control using Memov. Track every AI interaction with your codebase.

## Prerequisites

This skill requires the `memov` Python package which provides the `mem` CLI command.

### Installation Options

Choose one of the following methods:

```bash
# Option 1: Official install script (recommended)
curl -fsSL https://raw.githubusercontent.com/memovai/memov/main/install.sh | bash
```

### Verify Installation

```bash
mem
```

### Initialize in Your Project

```bash
cd your-project
mem init
```

## How to Use

There are two ways to use VibeGit:

1. **Skill scripts (this folder)**: run `./scripts/*.sh` to call the local `mem` CLI.
2. **MCP tools (Claude Code)**: use the MCP server tools like `mcp__mem-mcp__snap`.

They are related but not identical:

- Skill scripts are a thin wrapper over `mem` CLI.
- MCP tools may add extra behavior (e.g. auto-track untracked files, auto-sync for RAG features).

## Commands

All commands should be run from the skill directory using the scripts provided.

### Core Operations

| Script | Description | Usage |
|--------|-------------|-------|
| `init.sh` | Initialize memov in a project | `./scripts/init.sh` |
| `track.sh` | Track new files | `./scripts/track.sh file1.py file2.py -p "..." -r "..."` |
| `snap.sh` | Record a code change | `./scripts/snap.sh --files "file1.py,file2.py" -p "What was asked" -r "What was done"` |
| `history.sh` | View AI coding history | `./scripts/history.sh [--limit 20]` |
| `show.sh` | Show commit details | `./scripts/show.sh <commit_hash>` |
| `status.sh` | Check working directory status | `./scripts/status.sh` |

### Navigation

| Script | Description | Usage |
|--------|-------------|-------|
| `jump.sh` | Jump to a specific snapshot | `./scripts/jump.sh <commit_hash>` |
| `branch.sh` | List/create/delete branches | `./scripts/branch.sh [name] [--delete name]` |
| `switch.sh` | Switch branches | `./scripts/switch.sh <branch_name>` |

### Web UI

Before running `mem ui start`, confirm where you want to open the UI:

- Which project directory should the UI read from?
  - If not sure, run `pwd` and use `--loc <that path>`.

Suggested confirmation prompt:

| Script | Description | Usage |
|--------|-------------|-------|
| `ui_start.sh` | Start visual history browser | `./scripts/ui_start.sh [--loc /path] [--port 38888] [--foreground]` |
| `ui_stop.sh` | Stop the web server | `./scripts/ui_stop.sh [--loc /path]` |
| `ui_status.sh` | Check server status | `./scripts/ui_status.sh [--loc /path]` |

## Automatic Recording

After every AI coding session, record the interaction:

```bash
./scripts/snap.sh \
  --files "api.py,tests/test_api.py" \
  --prompt "Add authentication endpoint" \
  --response "Added /login POST endpoint with JWT token generation"
```

### Parameters

- `--files`: Comma-separated list of files that were modified
- `--prompt` or `-p`: The user's original request
- `--response` or `-r`: Summary of what was done
- `--by-user` or `-u`: Mark as human edit (vs AI)

## RAG Features (Optional)

Some features (semantic search, validate, vibe_debug/vibe_search tools) require installing extra dependencies.

- CLI: install with `pip install memov[rag]` then run `mem sync` once.
- MCP: those tools may not appear unless RAG dependencies are installed.

## Examples

### Record a bug fix

```bash
./scripts/snap.sh \
  --files "auth.py" \
  --prompt "Fix null pointer in login" \
  --response "Added null check for user object at L45"
```

### View recent history

```bash
./scripts/history.sh --limit 10
```

### Jump to previous state

```bash
./scripts/jump.sh a1b2c3d
```

## Direct CLI Usage

You can also use the `mem` CLI directly:

```bash
# Initialize
mem init

# Track new files
mem track file1.py file2.py -p "Initial tracking"

# Snapshot changes
mem snap --files file1.py -p "Added feature X" -r "Implemented..."

# View history
mem history

# Show specific commit
mem show a1b2c3d

# Jump to snapshot
mem jump a1b2c3d
```

## What Gets Recorded

Each snapshot captures:
- **Prompt**: What you asked the AI to do
- **Response**: What the AI said it did
- **Files**: Which files were changed
- **Diff**: Actual code changes
- **Timestamp**: When it happened
- **Source**: AI or human

## Benefits

- **Never lose context**: Every AI interaction is recorded
- **Time travel**: Jump to any point in your coding history
- **Understand changes**: See not just what changed, but why

## Troubleshooting

### "memov CLI not found" error

If you see this error when running any script, memov is not installed. Run:

```bash
# Quick check
./install.sh

# Or install manually
pip install memov
```

### Scripts not executable

```bash
chmod +x scripts/*.sh install.sh
```
