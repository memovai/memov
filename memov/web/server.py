"""MemoV Web UI Server - FastAPI backend for visualizing commit history."""

import logging
import os
import traceback
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from memov.core.manager import MemovManager, MemStatus

LOGGER = logging.getLogger(__name__)

# Global project path (set when server starts)
_project_path: Optional[str] = None


# AI Search request model (defined at module level for proper serialization)
class AISearchRequest(BaseModel):
    api_key: str
    query: str
    provider: str = "openai"  # "anthropic" or "openai"


async def _call_anthropic(api_key: str, system_prompt: str, user_prompt: str) -> str:
    """Call Anthropic Claude API."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"]


async def _call_openai(api_key: str, system_prompt: str, user_prompt: str) -> str:
    """Call OpenAI API."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-5-nano",
                "max_tokens": 1024,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


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

        history = manager.get_history(limit=10000, diff_mode="status")
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

        status, new_branch = manager.jump(commit_hash)
        if status is not MemStatus.SUCCESS:
            raise HTTPException(status_code=400, detail=f"Jump failed: {status}")

        return {"status": "success", "new_branch": new_branch}

    @app.post("/api/search/ai")
    async def ai_search(request: AISearchRequest):
        """Search history using AI model."""
        manager = MemovManager(project_path=_project_path)
        if manager.check() is not MemStatus.SUCCESS:
            raise HTTPException(status_code=400, detail="Memov not initialized")

        # Get history data
        history = manager.get_history(limit=50)  # Limit to recent 50 commits

        # Build compact history summary for AI (only prompt/commit message)
        history_text = []
        for entry in history:
            prompt = entry["prompt"] or "N/A"
            summary = f"[{entry['short_hash']}] {entry['branch']} | {prompt[:200]}"
            history_text.append(summary)

        history_context = "\n".join(history_text)

        # Build AI prompt
        system_prompt = """You are an AI assistant helping users search their code history.
You will be given a list of commits with their prompts/messages.
Answer the user's question based ONLY on this history. Be concise.

LANGUAGE:
- Detect the language of the user's question.
- Respond in the SAME language as the user's question.
- If the question explicitly requests a language, prioritize that language.

OUTPUT FORMAT (STRICT JSON ONLY):
- Return ONLY a JSON object (no markdown, no code fences, no extra text).
- The JSON object MUST contain exactly these keys:
  - "answer": a concise string answer in the user's language
  - "commit_ids": an array of 7-character commit hashes (strings) that are relevant
- Use only commit hashes that appear in the provided history.

Example:
{"answer":"You fixed the login bug in commit abc1234","commit_ids":["abc1234"]}"""

        user_prompt = f"""Commit history (format: [hash] branch | prompt):

{history_context}

Question: {request.query}

Return ONLY the JSON object with "answer" and "commit_ids" as specified."""

        try:
            if request.provider == "anthropic":
                raise HTTPException(status_code=400, detail="Anthropic provider is not supported for AI search.")
            elif request.provider == "openai":
                ai_response = await _call_openai(request.api_key, system_prompt, user_prompt)
            else:
                raise HTTPException(status_code=400, detail=f"Unknown provider: {request.provider}")

            # Parse JSON response
            import json
            import re
            try:
                parsed = json.loads(ai_response)
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=502, detail=f"AI response was not valid JSON: {e.msg}")

            if not isinstance(parsed, dict):
                raise HTTPException(status_code=502, detail="AI response JSON must be an object.")

            if "answer" not in parsed or "commit_ids" not in parsed:
                raise HTTPException(status_code=502, detail="AI response JSON must contain 'answer' and 'commit_ids'.")

            answer = parsed.get("answer")
            commit_ids_raw = parsed.get("commit_ids")

            if not isinstance(answer, str):
                raise HTTPException(status_code=502, detail="AI response 'answer' must be a string.")

            if not isinstance(commit_ids_raw, list):
                raise HTTPException(status_code=502, detail="AI response 'commit_ids' must be an array.")

            commit_ids = []
            for item in commit_ids_raw:
                if not isinstance(item, str):
                    raise HTTPException(status_code=502, detail="AI response 'commit_ids' items must be strings.")
                normalized = item.strip().lower()
                if not re.fullmatch(r"[a-f0-9]{7}", normalized):
                    raise HTTPException(
                        status_code=502,
                        detail=f"Invalid commit id '{item}'. Expected 7-char hex hash.",
                    )
                commit_ids.append(normalized)

            # Convert short hashes to full commit hashes
            full_commit_ids = []
            for short_hash in commit_ids:
                for entry in history:
                    if entry["short_hash"].lower().startswith(short_hash.lower()):
                        full_commit_ids.append(entry["commit_hash"])
                        break

            return {
                "response": answer,
                "commit_ids": full_commit_ids
            }
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code, detail=f"API error: {e.response.text}"
            )
        except Exception as e:
            LOGGER.error(f"AI search error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

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
