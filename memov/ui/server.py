"""
Memov UI Server - Local web interface for visualizing .mem git information
"""

import json
import logging
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
import uvicorn

from memov.core.git import GitManager

if TYPE_CHECKING:
    from memov.core.manager import MemovManager

LOGGER = logging.getLogger(__name__)


class MemovUIServer:
    """Web server data layer for Memov UI visualization."""

    def __init__(self, manager: "MemovManager"):
        self.manager = manager
        self.bare_repo = manager.bare_repo_path

    def get_commits_list(self, limit: int = 100, branch: str = None) -> list[dict]:
        """Get list of commits with metadata, optionally filtered by branch."""
        commits = []
        branches_data = self.manager._load_branches()

        if not branches_data:
            return commits

        all_branches = branches_data.get("branches", {})

        # If branch specified, only get commits from that branch
        if branch and branch in all_branches:
            tip_commit = all_branches[branch]
            history = GitManager.get_commit_history(self.bare_repo, tip_commit)

            for commit_hash in reversed(history):  # Most recent first
                commit_data = self._get_commit_metadata(commit_hash)
                commit_data["branches"] = [
                    name for name, tip in all_branches.items()
                    if commit_hash == tip
                ]
                commits.append(commit_data)

                if len(commits) >= limit:
                    break
        else:
            # Get all commits from all branches
            seen = set()
            for branch_name, tip_commit in all_branches.items():
                history = GitManager.get_commit_history(self.bare_repo, tip_commit)

                for commit_hash in reversed(history):  # Most recent first
                    if commit_hash in seen:
                        continue
                    seen.add(commit_hash)

                    commit_data = self._get_commit_metadata(commit_hash)
                    commit_data["branches"] = [
                        name for name, tip in all_branches.items()
                        if commit_hash == tip
                    ]
                    commits.append(commit_data)

                    if len(commits) >= limit:
                        break

        return commits

    def get_branch_info(self, branch_name: str) -> dict:
        """Get info for a specific branch."""
        branches_data = self.manager._load_branches()
        if not branches_data:
            return {"name": branch_name, "commit": None, "commit_full": None}

        all_branches = branches_data.get("branches", {})
        commit = all_branches.get(branch_name)

        return {
            "name": branch_name,
            "commit": commit[:7] if commit else None,
            "commit_full": commit,
        }

    def _parse_commit_content(self, content: str) -> dict:
        """Parse commit message or note content to extract metadata."""
        result = {"prompt": "", "response": "", "source": "", "agent_plan": "", "files": []}

        if not content:
            return result

        lines = content.splitlines()
        current_field = None
        multiline_buffer = []

        for line in lines:
            # Check for field prefixes
            if line.startswith("Prompt:"):
                if current_field and multiline_buffer:
                    result[current_field] = "\n".join(multiline_buffer).strip()
                current_field = "prompt"
                multiline_buffer = [line[len("Prompt:") :].strip()]
            elif line.startswith("Response:"):
                if current_field and multiline_buffer:
                    result[current_field] = "\n".join(multiline_buffer).strip()
                current_field = "response"
                multiline_buffer = [line[len("Response:") :].strip()]
            elif line.startswith("Source:"):
                if current_field and multiline_buffer:
                    result[current_field] = "\n".join(multiline_buffer).strip()
                current_field = "source"
                multiline_buffer = [line[len("Source:") :].strip()]
            elif line.startswith("Agent Plan:"):
                if current_field and multiline_buffer:
                    result[current_field] = "\n".join(multiline_buffer).strip()
                current_field = "agent_plan"
                multiline_buffer = [line[len("Agent Plan:") :].strip()]
            elif line.startswith("Files:"):
                if current_field and multiline_buffer:
                    result[current_field] = "\n".join(multiline_buffer).strip()
                files_str = line[len("Files:") :].strip()
                result["files"] = [f.strip() for f in files_str.split(",") if f.strip()]
                current_field = None
                multiline_buffer = []
            elif current_field:
                multiline_buffer.append(line)

        # Save any remaining multiline content
        if current_field and multiline_buffer:
            result[current_field] = "\n".join(multiline_buffer).strip()

        return result

    def _get_commit_metadata(self, commit_hash: str) -> dict:
        """Extract metadata from a single commit."""
        message = GitManager.get_commit_message(self.bare_repo, commit_hash)
        note = GitManager.get_commit_note(self.bare_repo, commit_hash)
        files, _ = GitManager.get_files_by_commit(self.bare_repo, commit_hash)

        # Parse commit message
        parsed_msg = self._parse_commit_content(message)

        # Override with git notes if present
        if note:
            parsed_note = self._parse_commit_content(note)
            if parsed_note["prompt"]:
                parsed_msg["prompt"] = parsed_note["prompt"]
            if parsed_note["response"]:
                parsed_msg["response"] = parsed_note["response"]
            if parsed_note["source"]:
                parsed_msg["source"] = parsed_note["source"]

        # Detect operation type
        first_line = message.splitlines()[0].lower() if message else ""
        operation_type = "unknown"
        if "track" in first_line:
            operation_type = "track"
        elif "snapshot" in first_line or "snap" in first_line:
            operation_type = "snap"
        elif "rename" in first_line:
            operation_type = "rename"
        elif "remove" in first_line:
            operation_type = "remove"

        # Clean up None values
        prompt = parsed_msg["prompt"]
        if prompt == "None" or prompt is None:
            prompt = ""
        response = parsed_msg["response"]
        if response == "None" or response is None:
            response = ""

        return {
            "hash": commit_hash,
            "short_hash": commit_hash[:7],
            "operation_type": operation_type,
            "message": message.splitlines()[0] if message else "",
            "full_message": message,
            "prompt": prompt,
            "response": response,
            "source": parsed_msg["source"],
            "agent_plan": parsed_msg["agent_plan"],
            "files": files,
            "file_count": len(files),
        }

    def get_commit_detail(self, commit_hash: str) -> dict:
        """Get detailed info for a single commit including diff."""
        # Support short hash lookup
        if len(commit_hash) < 40:
            full_hash = GitManager.get_commit_id_by_ref(
                self.bare_repo, commit_hash, verbose=False
            )
            if full_hash:
                commit_hash = full_hash

        metadata = self._get_commit_metadata(commit_hash)

        # Get diff
        diff = GitManager.git_show(self.bare_repo, commit_hash, return_output=True)
        metadata["diff"] = diff

        return metadata

    def get_branches_list(self) -> dict:
        """Get all branches and current branch."""
        branches = self.manager._load_branches()
        if not branches:
            return {"current": None, "branches": []}

        return {
            "current": branches.get("current"),
            "branches": [
                {"name": name, "commit": commit[:7]}
                for name, commit in branches.get("branches", {}).items()
            ],
        }

    def get_status(self) -> dict:
        """Get current repository status."""
        head_commit = GitManager.get_commit_id_by_ref(
            self.bare_repo, "refs/memov/HEAD", verbose=False
        )
        branches = self.manager._load_branches()

        return {
            "head": head_commit[:7] if head_commit else None,
            "head_full": head_commit,
            "current_branch": branches.get("current") if branches else None,
            "project_path": self.manager.project_path,
        }


def create_app(manager: "MemovManager") -> Starlette:
    """Create the Starlette application."""
    server = MemovUIServer(manager)
    static_dir = Path(__file__).parent / "static"

    async def index(request):
        """Serve main HTML page."""
        html_path = static_dir / "index.html"
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    async def api_commits(request):
        """GET /api/commits - List commits, optionally filtered by branch."""
        limit = int(request.query_params.get("limit", 100))
        branch = request.query_params.get("branch")
        commits = server.get_commits_list(limit=limit, branch=branch)
        return JSONResponse(commits)

    async def api_commit_detail(request):
        """GET /api/commits/{hash} - Get single commit details."""
        commit_hash = request.path_params["hash"]
        try:
            detail = server.get_commit_detail(commit_hash)
            return JSONResponse(detail)
        except Exception as e:
            LOGGER.error(f"Error getting commit detail: {e}")
            return JSONResponse({"error": str(e)}, status_code=404)

    async def api_commit_diff(request):
        """GET /api/commits/{hash}/diff - Get diff for commit."""
        commit_hash = request.path_params["hash"]
        try:
            diff = GitManager.git_show(
                manager.bare_repo_path, commit_hash, return_output=True
            )
            return JSONResponse({"diff": diff})
        except Exception as e:
            LOGGER.error(f"Error getting commit diff: {e}")
            return JSONResponse({"error": str(e)}, status_code=404)

    async def api_branches(request):
        """GET /api/branches - List all branches."""
        branches = server.get_branches_list()
        return JSONResponse(branches)

    async def api_branch_info(request):
        """GET /api/branches/{name} - Get info for a specific branch."""
        branch_name = request.path_params["name"]
        info = server.get_branch_info(branch_name)
        return JSONResponse(info)

    async def api_status(request):
        """GET /api/status - Get current status."""
        status = server.get_status()
        return JSONResponse(status)

    routes = [
        Route("/", index),
        Route("/api/commits", api_commits),
        Route("/api/commits/{hash}", api_commit_detail),
        Route("/api/commits/{hash}/diff", api_commit_diff),
        Route("/api/branches", api_branches),
        Route("/api/branches/{name}", api_branch_info),
        Route("/api/status", api_status),
        Mount("/static", StaticFiles(directory=str(static_dir)), name="static"),
    ]

    return Starlette(routes=routes)


def start_ui_server(
    manager: "MemovManager",
    port: int = 8765,
    host: str = "127.0.0.1",
    open_browser: bool = True,
) -> None:
    """Start the UI server."""
    from rich.console import Console

    console = Console()
    app = create_app(manager)

    url = f"http://{host}:{port}"
    console.print(f"\n  [bold cyan]Memov UI[/bold cyan] starting at: [link={url}]{url}[/link]")
    console.print(f"  Project: [dim]{manager.project_path}[/dim]")
    console.print(f"  Press [bold]Ctrl+C[/bold] to stop\n")

    if open_browser:
        webbrowser.open(url)

    uvicorn.run(app, host=host, port=port, log_level="warning")
