<p align="center">
  <a href="https://github.com/memovai/memov">
    <img src="docs/images/memov-banner.png" width="800px" alt="MemoV - The Memory Layer for AI Coding Agents">
  </a>
</p>

<p align="center">
  <b>English</b> | <a href="README_CN.md">简体中文</a> | <a href="README_JA.md">日本語</a>
</p>

<h4 align="center">VibeGit🤌: Auto-track your prompts, context & code diffs.</h4>

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Discord](https://img.shields.io/badge/Discord-Join%20Server-7289da?logo=discord&logoColor=white)](https://discord.gg/un54aD7Hug)
[![Twitter Follow](https://img.shields.io/twitter/follow/ssslvky?style=social)](https://x.com/ssslvky)

</div>

Traceable, Git-powered memory for AI coding. Prompts, context, and code diffs **auto versioned** - it's VibeGit!🤌

Persistent. Rollback anytime, branch freely, explore different solutions.

Avoid 1000+ **manual** commits, your **.git** still stays clean.


<div align="center">

| MemoV | Checkpoints |
|-------|-------------|
| Branch exploration | Linear timeline |
| Cross-session | Session-bound |
| Rollback preserves all | Rollback erases history |
| Every jump tracked | No trajectory |

</div>

<!-- <p align="center">
  <img src="docs/images/readme.gif" alt="MemoV Demo" width="800px">
</p> -->

- 💬 [Join our Discord](https://discord.gg/un54aD7Hug) and dive into smarter vibe engineering

<!-- <div align="center">

[![Add to VS Code](https://img.shields.io/badge/Add%20to%20VS%20Code-007ACC?style=for-the-badge&logo=visual-studio-code&logoColor=white)](https://memov.ai/set-mcp)
[![Add to Cursor](https://img.shields.io/badge/Add%20to%20CURSOR-000000?style=for-the-badge&logo=visual-studio-code&logoColor=white)](https://memov.ai/set-mcp)

</div> -->

## Features

- ⚡ **One-click MCP** — Works with any AI coding agent
- 🧠 **Full context** — Every prompt → agent plan → code diff is captured in real time
- ⏪ **Version Control** — Branch, rollback, replay any interaction
- 🧼 **Keep Git Clean** — Shadow `.mem` timeline, zero pollution on `.git` 
- 🔍 **Visual UI** — Browse your AI coding history at http://localhost:38888
- 🔒 **Private-first** — Local, no database, no overhead. Use .memignore to exclude


## Quick Start (MCP Installation)

### Prerequisites

Install `uv` first:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Claude Code

Run in your project root directory:

```bash
claude mcp add mem-mcp --scope project -- uvx --from git+https://github.com/memovai/memov.git mem-mcp-launcher stdio $(pwd)
```

### Codex

Run in your project root directory:

```bash
codex mcp add mem-mcp -- uvx --from git+https://github.com/memovai/memov.git mem-mcp-launcher stdio $(pwd)
```

### VS Code

Create `.vscode/mcp.json` in your project root:

```json
{
  "servers": {
    "mem-mcp": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/memovai/memov.git",
        "mem-mcp-launcher",
        "stdio",
        "${workspaceFolder}"
      ]
    }
  }
}
```

### Cursor

Go to **Files > Preferences > Cursor Settings > MCP**, then add:

```json
{
  "mcpServers": {
    "mem-mcp": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/memovai/memov.git",
        "mem-mcp-launcher",
        "stdio",
        "${workspaceFolder}"
      ]
    }
  }
}
```

### Web UI

Just say **"use mem ui"** in the chat — opens at `http://localhost:38888` with timeline view, branch filtering, diff viewer, and jump to any snapshot.

### With VectorDB (RAG mode)

To enable semantic search, validation, and debugging tools, install with `[rag]` extras:

**Claude Code:**
```bash
claude mcp add mem-mcp --scope project -- uvx --from "git+https://github.com/memovai/memov.git[rag]" mem-mcp-launcher stdio $(pwd)
```

**VS Code / Cursor:** Change the `--from` argument to:
```
"git+https://github.com/memovai/memov.git[rag]"
```

## CLI Installation (Optional)

If you want to use the `mem` CLI tool directly (for manual tracking, history viewing, etc.):

### One-Line Install

```bash
curl -fsSL https://raw.githubusercontent.com/memovai/memov/main/install.sh | bash
```

Or with wget:

```bash
wget -qO- https://raw.githubusercontent.com/memovai/memov/main/install.sh | bash
```

### Package Managers

<details>
<summary><b>Homebrew (macOS/Linux)</b></summary>

```bash
brew tap memovai/mem
brew install memov
```

</details>

<details>
<summary><b>APT (Debian/Ubuntu)</b></summary>

```bash
echo "deb [trusted=yes] https://memovai.github.io/memov/apt stable main" | sudo tee /etc/apt/sources.list.d/mem.list
sudo apt update
sudo apt install mem
```

</details>

<details>
<summary><b>YUM/DNF (Fedora/RHEL/CentOS)</b></summary>

```bash
sudo curl -o /etc/yum.repos.d/mem.repo https://memovai.github.io/memov/yum/mem.repo
sudo dnf install mem
```

</details>

<details>
<summary><b>Direct Download</b></summary>

Download the latest release for your platform:

| Platform | Download |
|----------|----------|
| Linux x86_64 | [mem-linux-x86_64.tar.gz](https://github.com/memovai/memov/releases/latest/download/mem-linux-x86_64.tar.gz) |
| macOS Intel | [mem-macos-x86_64.tar.gz](https://github.com/memovai/memov/releases/latest/download/mem-macos-x86_64.tar.gz) |
| macOS Apple Silicon | [mem-macos-arm64.tar.gz](https://github.com/memovai/memov/releases/latest/download/mem-macos-arm64.tar.gz) |
| Windows x86_64 | [mem-windows-x86_64.exe.zip](https://github.com/memovai/memov/releases/latest/download/mem-windows-x86_64.exe.zip) |

**Linux / macOS:**

```bash
curl -LO https://github.com/memovai/memov/releases/latest/download/mem-linux-x86_64.tar.gz
tar -xzf mem-linux-x86_64.tar.gz
sudo mv mem-linux-x86_64 /usr/local/bin/mem
mem --help
```

**Windows (PowerShell):**

```powershell
Invoke-WebRequest -Uri "https://github.com/memovai/memov/releases/latest/download/mem-windows-x86_64.exe.zip" -OutFile "mem.zip"
Expand-Archive -Path "mem.zip" -DestinationPath "."
New-Item -ItemType Directory -Force -Path "$env:ProgramFiles\mem"
Move-Item -Path "mem-windows-x86_64.exe" -Destination "$env:ProgramFiles\mem\mem.exe"
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";$env:ProgramFiles\mem", "Machine")
mem --help
```

</details>

<details>
<summary><b>From Source</b></summary>

Requires Python 3.10+ and [uv](https://github.com/astral-sh/uv):

```bash
git clone https://github.com/memovai/memov.git
cd memov
uv sync
uv pip install -e .
mem --help
```

</details>

## Installation for Contributors

Please see [docs/installation_for_dev.md](docs/installation_for_dev.md) for detailed installation instructions.

## MCP Tools

These are available to MCP clients through the server:

### Core Operations

- `snap(user_prompt: str, original_response: str, agent_plan: list[str], files_changed: str)`
  - Record every user interaction with automatic file tracking. Handles untracked vs modified files intelligently.

- `mem_ui(port: int = 38888)`
  - Launch the Web UI at `http://localhost:38888` to visually browse history, view diffs, and jump to any snapshot.

- `mem_history(limit: int = 20, commit_hash: str = "")`
  - View memov history with prompts, responses, and file changes.

- `mem_jump(commit_hash: str)`
  - Jump to a specific snapshot, restoring all tracked files and creating a new branch.

### RAG Tools (requires `[rag]` extras)

These tools are only available when installed with `[rag]` extras.

- `mem_sync()`
  - Sync all pending operations to VectorDB for semantic search capabilities.

- `validate_commit(commit_hash: str, detailed: bool = True)`
  - Validate a specific commit by comparing prompt/response with actual code changes. Detects context drift and alignment issues.

- `validate_recent(n: int = 5)`
  - Validate the N most recent commits for alignment patterns. Useful for session reviews and quality assurance.

- `vibe_debug(query: str, error_message: str = "", stack_trace: str = "", user_logs: str = "", models: str = "", n_results: int = 5)`
  - Debug issues using RAG search + multi-model LLM comparison. Searches code history for relevant context and queries multiple AI models (GPT-4, Claude, Gemini) in parallel for diverse debugging insights.

- `vibe_search(query: str, n_results: int = 5, content_type: str = "")`
  - Fast semantic search through code history (prompts, responses, agent plans, code changes) without LLM analysis. Perfect for quick context lookup.

### Health Check

- `GET /health`
  - Returns "OK". Useful for IDE/agent readiness checks.


## License

MIT License. See `LICENSE`.
