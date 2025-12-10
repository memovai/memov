<p align="center">
  <a href="https://github.com/memovai/memov">
    <img src="docs/images/memov-banner.png" width="800px" alt="MemoV - The Memory Layer for AI Coding Agents">
  </a>
</p>

# VibeGit: Auto-manage your prompts, plans, and code diffs.

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Discord](https://img.shields.io/badge/Discord-Join%20Server-7289da?logo=discord&logoColor=white)](https://discord.gg/un54aD7Hug)
[![Twitter Follow](https://img.shields.io/twitter/follow/ssslvky?style=social)](https://x.com/ssslvky)

</div>

MemoV = Prompt + Agent Plan + CodeDiff

<p align="center">
  <img src="docs/images/readme.gif" alt="MemoV Demo" width="800px">
</p>

VibeGit: A shadow `.mem` timeline alongside git — every interaction (prompt, plan, diff) captured before you commit.

- 💬 [Join our Discord](https://discord.gg/un54aD7Hug) and dive into smarter context engineering
- 🌐 [Visit memov.ai](https://memov.ai) to visualize your coding memory and supercharge existing GitHub repos


<div align="center">

[![Add to VS Code](https://img.shields.io/badge/Add%20to%20VS%20Code-007ACC?style=for-the-badge&logo=visual-studio-code&logoColor=white)](https://memov.ai/set-mcp)
[![Add to Cursor](https://img.shields.io/badge/Add%20to%20CURSOR-000000?style=for-the-badge&logo=visual-studio-code&logoColor=white)](https://memov.ai/set-mcp)

</div>

## Features

- 📒 **Context-bound memory**: Automatically track user code diffs, prompts, and agent plans — independent of .git.
- ⏪ **Fine-grained rollback**: Built on git, revert to a specific agent plan within a single commit
- 🤝 **Team context sharing**: Real-time alignment with zero friction
- ♻️ **Change reuse**: Reapply past code edits by description to save tokens when iterating on a feature

## Installation

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
claude mcp add mem-mcp --scope project -- uvx --from git+https://github.com/memovai/memov.git mem stdio $(pwd)
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
        "mem",
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
        "mem",
        "stdio",
        "${workspaceFolder}"
      ]
    }
  }
}
```

## Installation for Contributors

Please see [docs/installation_for_dev.md](docs/installation_for_dev.md) for detailed installation instructions.

## MCP Tools

These are available to MCP clients through the server:

### Core Operations

- `snap(user_prompt: str, original_response: str, agent_plan: list[str], files_changed: str)`
  - Record every user interaction with automatic file tracking. Handles untracked vs modified files intelligently.

- `mem_sync()`
  - Sync all pending operations to VectorDB for semantic search capabilities.

### Validation & Debugging

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
