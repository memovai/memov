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
mem --version
```

### Initialize in Your Project

```bash
cd your-project
mem init
```

## Commands

All commands should be run from the skill directory using the scripts provided.

### Core Operations

| Script | Description | Usage |
|--------|-------------|-------|
| `snap.sh` | Record a code change | `./scripts/snap.sh --files "file1.py,file2.py" --prompt "What was asked" --response "What was done"` |
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

| Script | Description | Usage |
|--------|-------------|-------|
| `ui_start.sh` | Start visual history browser | `./scripts/ui_start.sh [--port 38888]` |
| `ui_stop.sh` | Stop the web server | `./scripts/ui_stop.sh` |
| `ui_status.sh` | Check server status | `./scripts/ui_status.sh` |

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

### Open visual timeline
```bash
./scripts/ui_start.sh
# Opens browser at http://localhost:38888
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

# Start Web UI
mem ui
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
- **Visual timeline**: Browse history in a web UI

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
