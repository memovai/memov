# Installation Instructions

### One-Click Setup (Recommended, two clicks for now😅)

<div align="center">

[![Add to VS Code](https://img.shields.io/badge/Add%20to%20VS%20Code-007ACC?style=for-the-badge&logo=visual-studio-code&logoColor=white)](https://memov-vscode.vercel.app/)
[![Add to Cursor](https://img.shields.io/badge/Add%20to%20CURSOR-000000?style=for-the-badge&logo=visual-studio-code&logoColor=white)](https://memov-vscode.vercel.app/)

</div>


### Manual Configuration

1. **Install uv** - [Modern Python package and project manager](https://docs.astral.sh/uv/getting-started/installation/)

   **Linux / macOS:**

   Using `curl`:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   Or using `wget`:
   ```bash
   wget -qO- https://astral.sh/uv/install.sh | sh
   ```

   **Windows:**
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. **Configure your IDE**

    **VS Code:** Create `.vscode/mcp.json` in your project root:
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
      },
      "inputs": []
    }
    ```


    **Cursor:** Go to Files > Preferences > Cursor Settings > MCP, then add a new MCP server with the following config:
    ```json
    {
      "mcpServers": {
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


    **Claude Code:** Run the following command in your terminal to add the MCP server:
    > Note: Make sure you are in your project root directory when running this command, like where your `.git` folder is located.
    ```bash
    claude mcp add mem-mcp --scope project -- uvx --from git+https://github.com/memovai/memov.git mem-mcp-launcher stdio $(pwd)
    ```