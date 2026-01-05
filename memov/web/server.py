"""MemoV Web UI Server - FastAPI backend for visualizing commit history."""

import logging
import os
import traceback
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from memov.core.manager import MemovManager, MemStatus

LOGGER = logging.getLogger(__name__)

# Global project path (set when server starts)
_project_path: Optional[str] = None


def create_app(project_path: str) -> "FastAPI":
    """Create FastAPI application with routes."""
    global _project_path
    _project_path = project_path

    app = FastAPI(title="MemoV Web UI", version="1.0.0")

    # Global exception handler for better error messages
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        error_detail = f"{type(exc).__name__}: {str(exc)}"
        tb = traceback.format_exc()
        LOGGER.error(f"Unhandled exception: {error_detail}\n{tb}")
        return JSONResponse(
            status_code=500,
            content={"detail": error_detail, "traceback": tb},
        )

    # API Routes
    @app.get("/api/status")
    def get_status():
        """Get memov initialization status."""
        manager = MemovManager(project_path=_project_path)
        initialized = manager.check() is MemStatus.SUCCESS
        return {
            "initialized": initialized,
            "project_path": _project_path,
        }

    @app.get("/api/branches")
    def get_branches():
        """Get all branches and current branch."""
        manager = MemovManager(project_path=_project_path)
        if manager.check() is not MemStatus.SUCCESS:
            # Return empty data instead of error - let frontend show "not initialized" UI
            return {"current": None, "branches": {}}

        branches = manager._load_branches()
        if branches is None:
            return {"current": None, "branches": {}}
        return branches

    @app.get("/api/graph")
    def get_graph():
        """Get commit graph data for visualization."""
        manager = MemovManager(project_path=_project_path)
        if manager.check() is not MemStatus.SUCCESS:
            # Return empty graph instead of error - let frontend show "not initialized" UI
            return {"nodes": [], "edges": [], "jump_edges": [], "current_branch": None}

        history = manager.get_history(limit=100)
        branches = manager._load_branches()

        # Build graph structure
        nodes = []
        edges = []
        seen_commits = set()

        for entry in history:
            commit_hash = entry["commit_hash"]
            if commit_hash in seen_commits:
                continue
            seen_commits.add(commit_hash)

            nodes.append(
                {
                    "id": commit_hash,
                    "short_hash": entry["short_hash"],
                    "operation": entry["operation"],
                    "branch": entry["branch"],
                    "is_head": entry["is_head"],
                    "prompt": entry["prompt"],
                    "response": entry["response"],
                    "agent_plan": entry["agent_plan"],
                    "files": entry["files"],
                    "timestamp": entry["timestamp"],
                    "author": entry["author"],
                    "diff": entry.get("diff", {}),
                }
            )

        # Build edges (parent relationships) using git rev-list
        from memov.core.git import GitManager

        if branches:
            for branch_name, tip_hash in branches.get("branches", {}).items():
                commit_list = GitManager.get_commit_history(manager.bare_repo_path, tip_hash)
                for i in range(len(commit_list) - 1):
                    edges.append(
                        {
                            "from": commit_list[i],
                            "to": commit_list[i + 1],
                        }
                    )

        # Get jump edges from exploration history (jump.json)
        # Falls back to branches.json jump_from for backward compatibility
        jump_edges = []
        jump_history = manager._load_jump_history()
        if jump_history and jump_history.get("history"):
            # Use jump.json (preferred)
            for jump_record in jump_history["history"]:
                jump_edges.append(
                    {
                        "from_commit": jump_record["from_commit"],
                        "to_commit": jump_record["to_commit"],
                        "branch": jump_record["new_branch"],
                    }
                )
        elif branches and "jump_from" in branches:
            # Fallback to branches.json for backward compatibility
            for branch_name, jump_info in branches["jump_from"].items():
                jump_edges.append(
                    {
                        "from_commit": jump_info["from_commit"],
                        "to_commit": jump_info["to_commit"],
                        "branch": branch_name,
                    }
                )

        return {
            "nodes": nodes,
            "edges": edges,
            "jump_edges": jump_edges,
            "current_branch": branches.get("current") if branches else None,
        }

    @app.get("/api/commit/{commit_hash}")
    def get_commit(commit_hash: str):
        """Get detailed info for a specific commit."""
        manager = MemovManager(project_path=_project_path)
        if manager.check() is not MemStatus.SUCCESS:
            raise HTTPException(status_code=400, detail="Memov not initialized")

        history = manager.get_history(limit=100)
        for entry in history:
            if entry["commit_hash"].startswith(commit_hash) or entry["short_hash"] == commit_hash:
                return entry

        raise HTTPException(status_code=404, detail=f"Commit {commit_hash} not found")

    @app.get("/api/diff/{commit_hash}")
    def get_diff(commit_hash: str):
        """Get diff for a commit."""
        manager = MemovManager(project_path=_project_path)
        if manager.check() is not MemStatus.SUCCESS:
            raise HTTPException(status_code=400, detail="Memov not initialized")

        diff_content = manager.get_diff(commit_hash)
        return {"commit_hash": commit_hash, "diff": diff_content}

    @app.post("/api/jump/{commit_hash}")
    def jump_to_commit(commit_hash: str):
        """Jump to a specific commit."""
        manager = MemovManager(project_path=_project_path)
        if manager.check() is not MemStatus.SUCCESS:
            raise HTTPException(status_code=400, detail="Memov not initialized")

        status, new_branch, error_detail = manager.jump(commit_hash)
        if status is not MemStatus.SUCCESS:
            raise HTTPException(status_code=400, detail=f"Jump failed: {error_detail or status}")

        return {"status": "success", "new_branch": new_branch}

    # Serve static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():

        @app.get("/")
        def serve_index():
            """Serve the main HTML page."""
            index_path = static_dir / "index.html"
            if index_path.exists():
                # Use explicit utf-8 encoding for Windows compatibility
                return HTMLResponse(content=index_path.read_text(encoding="utf-8"), status_code=200)
            raise HTTPException(status_code=404, detail="index.html not found")

        # Mount static files for assets (logo, etc.)
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app


def start_server(project_path: str, port: int = 38888, host: str = "127.0.0.1"):
    """Start the MemoV web server."""
    # Validate project path
    if not os.path.exists(project_path):
        print(f"Error: Project path '{project_path}' does not exist.")
        return

    app = create_app(project_path)

    # Check initialization status (warning only, don't block)
    manager = MemovManager(project_path=project_path)
    if manager.check() is not MemStatus.SUCCESS:
        print(f"Warning: Memov not initialized in '{project_path}'.")
        print("Run 'mem init' to initialize, or the UI will show setup instructions.")

    print(f"Starting MemoV Web UI...")
    print(f"Project: {project_path}")
    print(f"URL: http://{host}:{port}")
    print("Press Ctrl+C to stop.")

    uvicorn.run(app, host=host, port=port, log_level="warning")
