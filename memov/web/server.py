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

from memov.constants.prompts import (
    AI_SEARCH_SYSTEM_PROMPT,
    AI_SEARCH_USER_PROMPT_TEMPLATE,
    CLUSTER_SYSTEM_PROMPT,
    CLUSTER_USER_PROMPT_TEMPLATE,
    SKILL_SYSTEM_PROMPT,
    SKILL_USER_PROMPT_TEMPLATE,
)
from memov.core.manager import MemovManager, MemStatus
from memov.storage.skills_db import SkillsDB

LOGGER = logging.getLogger(__name__)

# Global project path (set when server starts)
_project_path: Optional[str] = None


# AI Search request model (defined at module level for proper serialization)
class AISearchRequest(BaseModel):
    api_key: str
    query: str
    provider: str = "openai"  # "anthropic" or "openai"


class SkillsRefreshRequest(BaseModel):
    api_key: str
    force: bool = False


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


def _extract_openai_content(data: dict) -> str:
    try:
        # Responses API
        if isinstance(data.get("output"), list):
            parts = []
            for item in data["output"]:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "output_text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                content = item.get("content") or []
                if isinstance(content, list):
                    for part in content:
                        if not isinstance(part, dict):
                            continue
                        if isinstance(part.get("text"), str):
                            parts.append(part["text"])
            return "".join(parts)

        # Chat Completions API
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part["text"])
            return "".join(parts)
    except Exception:
        return ""
    return ""


async def _call_openai(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    force_json: bool = True,
    max_output_tokens: int = 10240,
) -> str:
    """Call OpenAI API (Responses API for GPT-5)."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        payload = {
            "model": "gpt-5-nano",
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_output_tokens": max_output_tokens,
        }
        if force_json:
            payload["text"] = {"format": {"type": "json_object"}, "verbosity": "low"}
        else:
            payload["text"] = {"verbosity": "low"}

        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        content = _extract_openai_content(data)
        if not content:
            try:
                import json as _json

                raw_preview = _json.dumps(data)[:2000]
            except Exception:
                raw_preview = str(data)[:2000]
            LOGGER.warning(
                f"OpenAI empty content (force_json={force_json}). raw_preview={raw_preview!r}"
            )
        return content


def _get_skills_db(manager: MemovManager) -> SkillsDB:
    db_path = Path(manager.mem_root_path) / "skills.db"
    return SkillsDB(db_path)


def _ensure_mem_logger(project_path: str) -> None:
    """Ensure logs are also written to .mem/mem.log for this project."""
    try:
        mem_root = Path(project_path) / ".mem"
        mem_root.mkdir(parents=True, exist_ok=True)
        log_path = mem_root / "mem.log"

        for handler in LOGGER.handlers:
            if isinstance(handler, logging.FileHandler):
                if Path(handler.baseFilename) == log_path:
                    return

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        LOGGER.addHandler(file_handler)
        LOGGER.setLevel(logging.INFO)
    except Exception:
        # Avoid breaking server if log file setup fails
        return


def _build_history_context(history: list[dict]) -> tuple[str, dict, dict]:
    lines = []
    short_to_full: dict[str, dict] = {}
    short_to_entry: dict[str, dict] = {}
    for entry in history:
        short_hash = entry["short_hash"].lower()
        prompt = (entry.get("prompt") or "N/A").replace("\n", " ").strip()
        prompt = prompt[:160]
        files = entry.get("files") or []
        files_preview = ", ".join(files[:5])
        op = entry.get("operation") or "snap"
        branch = entry.get("branch") or "unknown"
        line = f"[{short_hash}] {branch} | {op} | {prompt}"
        if files_preview:
            line += f" | files: {files_preview}"
        lines.append(line)
        short_to_full[short_hash] = {
            "commit_hash": entry["commit_hash"],
            "commit_short": entry["short_hash"],
        }
        short_to_entry[short_hash] = entry
    return "\n".join(lines), short_to_full, short_to_entry


def _answer_indicates_no_info(answer: str) -> bool:
    lowered = answer.strip().lower()
    if not lowered:
        return True
    # English patterns
    english_markers = [
        "no information",
        "no relevant",
        "not found",
        "cannot find",
        "could not find",
        "unable to find",
        "does not mention",
        "no mention",
    ]
    # Chinese patterns
    chinese_markers = [
        "没有",
        "未找到",
        "找不到",
        "无法找到",
        "无相关",
        "未提及",
        "没有信息",
    ]
    return any(marker in lowered for marker in english_markers) or any(
        marker in answer for marker in chinese_markers
    )


def _parse_json_response(payload: str, label: str) -> dict:
    import json

    if not payload or not payload.strip():
        raise HTTPException(status_code=502, detail=f"{label} JSON invalid: empty response")
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        cleaned = payload.strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=502, detail=f"{label} JSON invalid: {e.msg}")
        raise HTTPException(status_code=502, detail=f"{label} JSON invalid: Expecting value")


def _build_history_context_limited(
    history: list[dict], max_chars: int, max_commits: int
) -> tuple[str, dict, dict]:
    if max_commits <= 0:
        return "", {}, {}
    recent_history = history[-max_commits:] if len(history) > max_commits else history
    lines = []
    short_to_full: dict[str, dict] = {}
    short_to_entry: dict[str, dict] = {}
    total_len = 0
    for entry in recent_history:
        short_hash = entry["short_hash"].lower()
        prompt = (entry.get("prompt") or "N/A").replace("\n", " ").strip()
        prompt = prompt[:160]
        files = entry.get("files") or []
        files_preview = ", ".join(files[:5])
        op = entry.get("operation") or "snap"
        branch = entry.get("branch") or "unknown"
        line = f"[{short_hash}] {branch} | {op} | {prompt}"
        if files_preview:
            line += f" | files: {files_preview}"
        line_len = len(line) + 1
        if total_len + line_len > max_chars:
            break
        lines.append(line)
        total_len += line_len
        short_to_full[short_hash] = {
            "commit_hash": entry["commit_hash"],
            "commit_short": entry["short_hash"],
        }
        short_to_entry[short_hash] = entry
    return "\n".join(lines), short_to_full, short_to_entry


def create_app(project_path: str) -> "FastAPI":
    """Create FastAPI application with routes."""
    global _project_path
    _project_path = project_path
    _ensure_mem_logger(project_path)

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
        system_prompt = AI_SEARCH_SYSTEM_PROMPT
        user_prompt = AI_SEARCH_USER_PROMPT_TEMPLATE.format(
            history_context=history_context,
            query=request.query,
        )

        try:
            if request.provider == "anthropic":
                raise HTTPException(status_code=400, detail="Anthropic provider is not supported for AI search.")
            elif request.provider == "openai":
                ai_response = await _call_openai(request.api_key, system_prompt, user_prompt)
            else:
                raise HTTPException(status_code=400, detail=f"Unknown provider: {request.provider}")

            # Parse JSON response
            import re
            parsed = _parse_json_response(ai_response, "AI response")

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

            if _answer_indicates_no_info(answer):
                commit_ids = []

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

    @app.get("/api/skills")
    async def get_skills():
        """Get cached AI skill summaries and feature clusters."""
        manager = MemovManager(project_path=_project_path)
        if manager.check() is not MemStatus.SUCCESS:
            raise HTTPException(status_code=400, detail="Memov not initialized")

        db = _get_skills_db(manager)
        features = db.get_features()
        return {
            "features": [
                {
                    "id": f.feature_id,
                    "name": f.name,
                    "summary": f.summary,
                    "skill_title": f.skill_title,
                    "skill_content": f.skill_content,
                    "skill_label": f.skill_label,
                    "commit_ids": [c["commit_hash"] for c in f.commits],
                    "commit_shorts": [c["commit_short"] for c in f.commits],
                }
                for f in features
            ]
        }

    @app.post("/api/skills/refresh")
    async def refresh_skills(request: SkillsRefreshRequest):
        """Generate feature clusters and skills summaries using OpenAI."""
        manager = MemovManager(project_path=_project_path)
        if manager.check() is not MemStatus.SUCCESS:
            raise HTTPException(status_code=400, detail="Memov not initialized")

        history = manager.get_history(limit=2000, include_diff=False, diff_mode="none")
        LOGGER.info(f"Skills refresh: history commits loaded={len(history)}")
        if not history:
            raise HTTPException(status_code=400, detail="No history available to summarize")
        attempt_limits = [
            (800, 12000),
            (400, 8000),
            (200, 5000),
            (100, 3000),
        ]
        history_context = ""
        short_to_full: dict[str, dict] = {}
        short_to_entry: dict[str, dict] = {}

        cluster_system_prompt = CLUSTER_SYSTEM_PROMPT
        cluster_user_prompt = CLUSTER_USER_PROMPT_TEMPLATE.format(
            history_context=history_context
        )

        cluster_response = ""
        cluster_payload: Optional[dict] = None
        last_error: Optional[HTTPException] = None
        for max_commits, max_chars in attempt_limits:
            history_context, short_to_full, short_to_entry = _build_history_context_limited(
                history, max_chars=max_chars, max_commits=max_commits
            )
            if not history_context:
                LOGGER.warning(
                    f"Skills refresh: empty history context for max_commits={max_commits}, max_chars={max_chars}"
                )
                continue
            LOGGER.info(
                "Skills refresh: clustering attempt "
                f"max_commits={max_commits}, max_chars={max_chars}, "
                f"context_len={len(history_context)}"
            )
            cluster_user_prompt = CLUSTER_USER_PROMPT_TEMPLATE.format(
                history_context=history_context
            )

            try:
                cluster_response = await _call_openai(
                    request.api_key, cluster_system_prompt, cluster_user_prompt, True
                )
                if not cluster_response:
                    LOGGER.warning("Skills refresh: empty cluster response, retrying without JSON format.")
                    cluster_response = await _call_openai(
                        request.api_key, cluster_system_prompt, cluster_user_prompt, False
                    )
                LOGGER.info(
                    "Skills refresh: cluster response received "
                    f"len={len(cluster_response)} preview={cluster_response[:200]!r}"
                )
                cluster_payload = _parse_json_response(cluster_response, "Cluster")
                last_error = None
                break
            except HTTPException as e:
                if e.status_code == 502 and "Cluster JSON invalid" in str(e.detail):
                    LOGGER.warning(
                        "Skills refresh: cluster parse error, will retry. "
                        f"detail={e.detail} raw_len={len(cluster_response)} raw={cluster_response!r}"
                    )
                    last_error = e
                    continue
                raise
            except httpx.HTTPStatusError as e:
                raise HTTPException(
                    status_code=e.response.status_code, detail=f"API error: {e.response.text}"
                )
            except Exception as e:
                LOGGER.error(f"Skills cluster error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        if last_error is not None:
            LOGGER.error(f"Skills refresh: failed after retries. last_error={last_error.detail}")
            raise last_error
        if cluster_payload is None:
            LOGGER.error("Skills refresh: cluster payload is None after retries.")
            raise HTTPException(status_code=502, detail="Cluster JSON invalid: empty response")

        import re

        if not isinstance(cluster_payload, dict) or "features" not in cluster_payload:
            LOGGER.error(
                f"Skills refresh: cluster payload missing 'features'. keys={list(cluster_payload.keys())}"
            )
            raise HTTPException(status_code=502, detail="Cluster JSON must include 'features'.")

        features = cluster_payload.get("features")
        if not isinstance(features, list):
            LOGGER.error("Skills refresh: cluster payload 'features' is not a list.")
            raise HTTPException(status_code=502, detail="'features' must be an array.")

        db = _get_skills_db(manager)
        db.reset()

        for feature in features:
            if not isinstance(feature, dict):
                raise HTTPException(status_code=502, detail="Feature entries must be objects.")
            name = feature.get("name")
            summary = feature.get("summary")
            commit_ids = feature.get("commit_ids")
            if not isinstance(name, str) or not name.strip():
                raise HTTPException(status_code=502, detail="Feature 'name' must be a string.")
            if not isinstance(summary, str) or not summary.strip():
                raise HTTPException(status_code=502, detail="Feature 'summary' must be a string.")
            if not isinstance(commit_ids, list) or not commit_ids:
                raise HTTPException(status_code=502, detail="Feature 'commit_ids' must be a non-empty array.")

            normalized_ids = []
            for item in commit_ids:
                if not isinstance(item, str):
                    raise HTTPException(status_code=502, detail="Commit ids must be strings.")
                commit_short = item.strip().lower()
                if not re.fullmatch(r"[a-f0-9]{7}", commit_short):
                    raise HTTPException(
                        status_code=502,
                        detail=f"Invalid commit id '{item}'. Expected 7-char hex.",
                    )
                if commit_short not in short_to_full:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Commit id '{item}' not found in history.",
                    )
                normalized_ids.append(commit_short)

            feature_id = db.insert_feature(name.strip(), summary.strip())
            commits_payload = [short_to_full[cid] for cid in normalized_ids]
            db.set_feature_commits(feature_id, commits_payload)

        # Generate skill docs per feature
        features_for_prompt = db.get_features()
        for feature in features_for_prompt:
            commit_lines = []
            for commit in feature.commits:
                entry = short_to_entry.get(commit["commit_short"].lower())
                if entry:
                    prompt = (entry.get("prompt") or "N/A").replace("\n", " ").strip()
                    prompt = prompt[:180]
                    branch = entry.get("branch") or "unknown"
                    op = entry.get("operation") or "snap"
                    files = entry.get("files") or []
                    files_preview = ", ".join(files[:5])
                    line = f"[{commit['commit_short']}] {branch} | {op} | {prompt}"
                    if files_preview:
                        line += f" | files: {files_preview}"
                    commit_lines.append(line)
                else:
                    commit_lines.append(f"[{commit['commit_short']}] {commit['commit_hash']}")
            commits_text = "\n".join(commit_lines)

            skill_system_prompt = SKILL_SYSTEM_PROMPT
            skill_user_prompt = SKILL_USER_PROMPT_TEMPLATE.format(
                feature_name=feature.name,
                feature_summary=feature.summary,
                commits_text=commits_text,
            )

            try:
                skill_response = await _call_openai(
                    request.api_key, skill_system_prompt, skill_user_prompt, True
                )
                if not skill_response:
                    LOGGER.warning("Skills refresh: empty skill response, retrying without JSON format.")
                    skill_response = await _call_openai(
                        request.api_key, skill_system_prompt, skill_user_prompt, False
                    )
            except httpx.HTTPStatusError as e:
                raise HTTPException(
                    status_code=e.response.status_code, detail=f"API error: {e.response.text}"
                )
            except Exception as e:
                LOGGER.error(f"Skills summary error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

            skill_payload = _parse_json_response(skill_response, "Skill")

            if not isinstance(skill_payload, dict):
                raise HTTPException(status_code=502, detail="Skill JSON must be an object.")

            title = skill_payload.get("title")
            content = skill_payload.get("content")
            label = skill_payload.get("label")
            if not isinstance(title, str) or not title.strip():
                raise HTTPException(status_code=502, detail="Skill 'title' must be a string.")
            if not isinstance(content, str) or not content.strip():
                raise HTTPException(status_code=502, detail="Skill 'content' must be a string.")
            if not isinstance(label, str) or not label.strip():
                raise HTTPException(status_code=502, detail="Skill 'label' must be a string.")

            db.set_skill_doc(feature.feature_id, title.strip(), content.strip(), label.strip())

        refreshed = db.get_features()
        return {
            "features": [
                {
                    "id": f.feature_id,
                    "name": f.name,
                    "summary": f.summary,
                    "skill_title": f.skill_title,
                    "skill_content": f.skill_content,
                    "skill_label": f.skill_label,
                    "commit_ids": [c["commit_hash"] for c in f.commits],
                    "commit_shorts": [c["commit_short"] for c in f.commits],
                }
                for f in refreshed
            ]
        }

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
