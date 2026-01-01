"""
Memov MCP Server - AI-assisted version control with automatic prompt recording

This MCP server provides intelligent memov integration that automatically:
- Records user prompts with file changes
- Handles new files vs modified files appropriately
- Provides seamless version control for AI-assisted development

Author: Memov Team
License: MIT
"""

import logging
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from memov.core.manager import MemovManager, MemStatus
from memov.storage import CHROMADB_AVAILABLE

# RAG-dependent imports (only available when [rag] extras are installed)
if CHROMADB_AVAILABLE:
    from memov.debugging import DebugValidator
    from memov.debugging.llm_client import LLMClient
    from memov.debugging.rag_debugger import DebugContext, RAGDebugger

LOGGER = logging.getLogger(__name__)


class MemMCPTools:
    # Initialize FastMCP server
    mcp = FastMCP("Memov MCP Server")

    # Global context storage for user prompts and working directory
    _project_path = None
    _user_context = {
        "current_prompt": None,
        "current_response": None,
        "timestamp": None,
        "session_id": None,
        # Indicates if the context has been cleaned, it should be reset after each interaction with the agent
        "context_cleaned": True,
    }

    def __init__(self, project_path: str) -> None:
        MemMCPTools._project_path = project_path

    def run(self, *args, **kwargs) -> None:
        """
        Run the MCP tools server.
        """
        LOGGER.info("Running MemMCPTools server...")
        # Start the FastMCP server
        MemMCPTools.mcp.run(*args, **kwargs)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_req: Request) -> PlainTextResponse:
        return PlainTextResponse("OK")

    # Core MCP tools for intelligent memov integration
    @staticmethod
    @mcp.tool()
    def snap(
        user_prompt: str, original_response: str, agent_plan: list[str], files_changed: str = ""
    ) -> str:
        """Record every user interaction - MUST be called at the end of EVERY response.

        **CRITICAL: Call this tool for EVERY user interaction, no exceptions!**

        This tool ensures complete interaction history by recording:
        - User prompts (questions, requests, commands)
        - Agent responses (answers, explanations, code changes)
        - Files changed (if any)

        **When to call (ALWAYS):**
        - User asked a question → Call with files_changed=""
        - User requested code changes → Call with files_changed="file1.py,file2.js"
        - User just chatting → Call with files_changed=""
        - Operation failed → Still call to record what happened
        - Read-only operations (viewing, searching) → Call with files_changed=""

        **When NOT to call:**
        - After rename operations - `mem rename` already handles the recording
        - After remove operations - `mem remove` already handles the recording

        **Intelligent Workflow:**
        1. **Auto-initialize** - Creates memov repository if it doesn't exist
        2. **For interactions without file changes** - Records prompt and response only
        3. **For interactions with file changes:**
           - Status check - Analyzes current file states (untracked, modified, clean)
           - New files → `mem track` (auto-commits with prompt)
           - Modified files → `mem snap` (records changes with prompt)

        Args:
            user_prompt: The user's exact original prompt/request
            original_response: The exact original full response from the AI agent
                Note:
                    - Make sure to include the entire response, including any code blocks or explanations.

                Example:
                    Chat content:
                        [User Prompt]: Change the print statement in hello.py to "Hello World"
                        [AI Response]: I can see that the file currently shows "Hello Earth" but you mentioned the edits were undone. Let me check the current content of the file to see what needs to be changed. I can see the file currently has "Hello Earth". I'll change it back to "Hello World" as requested.
                        ```
                        Made changes.
                        ```
                        I've successfully changed "Hello Earth" back to "Hello World" in both the comment and the print statement in your hello.py file. The script will now output "Hello World" when run.
                    original_response:
                        I can see that the file currently shows "Hello Earth" but you mentioned the edits were undone. Let me check the current content of the file to see what needs to be changed. I can see the file currently has "Hello Earth". I'll change it back to "Hello World" as requested.
                        ```
                        Made changes.
                        ```
                        I've successfully changed "Hello Earth" back to "Hello World" in both the comment and the print statement in your hello.py file. The script will now output "Hello World" when run.
            agent_plan: High-level summary of the major changes, organized by file
                Notes:
                    - Each step should describe ONE significant modification to a specific file
                    - Format: "[file]: [what changed]"
                    - Aim for 2-5 high-level steps that map to distinct logical changes
                    - Focus on WHAT was changed in each file, not HOW the change was made
                    - Group all related changes to the same file into one step when they serve the same purpose

                Format:
                    [
                        "<filename>: <concise description of what changed>",
                        "<filename>: <concise description of what changed>",
                        ...
                    ]

                Good Examples (file-focused, concise):
                    Example 1 - Multiple files changed:
                        [User Prompt]: Add error handling and logging to the API endpoint
                        agent_plan:
                        [
                            "api/routes.py: Added try-catch error handling and logging integration",
                            "utils/logger.py: Created configure_logging() helper function"
                        ]

                    Example 2 - Multiple files for feature:
                        [User Prompt]: Refactor database connection to use connection pooling
                        agent_plan:
                        [
                            "db/connection.py: Refactored to use connection pool instead of direct connections",
                            "db/pool.py: Implemented ConnectionPool class with acquire/release methods",
                            "config/settings.py: Added connection pool configuration parameters"
                        ]

                    Example 3 - Simple single file change:
                        [User Prompt]: Fix typo in error message
                        agent_plan:
                        [
                            "handlers/auth.py: Fixed typo in error message"
                        ]

                    Example 4 - New files created:
                        [User Prompt]: Create a user authentication module
                        agent_plan:
                        [
                            "auth/login.py: Created login handler with JWT token generation",
                            "auth/middleware.py: Created authentication middleware",
                            "tests/test_auth.py: Added test cases for login and middleware"
                        ]

                Bad Examples (too vague, too granular, or missing file):
                    ❌ "Updated the code" (no file specified)
                    ❌ "api/routes.py: Made changes" (too vague, what changed?)
                    ❌ "Added a line" (no file, no context)
                    ❌ "Fixed the bug" (no file specified)
                    ❌ "api/routes.py: Added import, created variable, wrote if statement, added return, saved file" (too granular - should be one logical change)
                    ❌ "Added error handling in handle_request(), error_handler(), and validate_input() functions" (no file specified)

                Key Principles:
                    - Always start with the file path
                    - Describe the logical change, not implementation details
                    - One file, one logical purpose = one step
                    - Be concise but specific about what changed

            files_changed: Comma-separated relative path list of files that were modified/created/deleted
                          (e.g. "file1.py,module1/file2.py"), or empty string "" if no files changed

        Returns:
            Detailed result of the complete workflow execution
        """
        try:
            LOGGER.info(
                f"snap called with: files_changed='{files_changed}', project_path='{MemMCPTools._project_path}'"
            )
            LOGGER.info(
                f"Using prompt: {user_prompt}, response: {original_response}, plan: {agent_plan}"
            )

            if MemMCPTools._project_path is None:
                raise ValueError(f"Project path is not set.")

            if not os.path.exists(MemMCPTools._project_path):
                raise ValueError(f"Project path '{MemMCPTools._project_path}' does not exist.")

            # Convert agent_plan list to formatted string for storage
            # Each plan step is stored on a separate line for better readability
            agent_plan_str = None
            if agent_plan:
                agent_plan_str = "\n".join([f"{i+1}. {step}" for i, step in enumerate(agent_plan)])

            # Prepare the variables
            memov_manager = MemovManager(project_path=MemMCPTools._project_path)

            # Step 1: Check if Memov is initialized
            if (check_status := memov_manager.check()) is MemStatus.SUCCESS:
                LOGGER.info("Memov is initialized.")
            else:
                LOGGER.warning(f"Memov is not initialized, return {check_status}.")
                if (init_status := memov_manager.init()) is not MemStatus.SUCCESS:
                    LOGGER.error(f"Failed to initialize Memov: {init_status}")
                    return f"[ERROR] Failed to initialize Memov: {init_status}"

            # Step 2: Handle two cases - with or without file changes
            if not files_changed or files_changed.strip() == "":
                # Case 1: No file changes - just record the interaction without snapshotting files
                # We don't call snapshot() here because that would commit all tracked files,
                # including any manual changes the user made
                LOGGER.info("No files changed, skipping snapshot (prompt-only interaction)")

                # TODO: In the future, we could record prompt-only interactions using git notes
                # or a separate metadata system, without creating commits

                result_parts = [
                    "[SUCCESS] Interaction recorded (no file changes, no snapshot created)"
                ]
                result_parts.append(f"Prompt: {user_prompt}")
                result_parts.append(f"Response: {len(original_response)} characters")
                if agent_plan_str:
                    result_parts.append(f"Agent plan: {len(agent_plan_str)} characters")
                result = "\n".join(result_parts)
                LOGGER.info(f"Interaction recorded successfully: {result}")
                return result

            else:
                # Case 2: Has file changes - track/snap files
                LOGGER.info(f"Processing file changes: {files_changed}")

                # Check file status
                ret_status, current_file_status = memov_manager.status()
                if ret_status is not MemStatus.SUCCESS:
                    LOGGER.error(f"Failed to check file status: {ret_status}")
                    return f"[ERROR] Failed to check file status: {ret_status}"

                # Build set of AI-changed files (from files_changed parameter)
                ai_changed_files = set()
                for file_changed in files_changed.split(","):
                    file_changed = file_changed.strip()
                    if file_changed:
                        file_path = Path(MemMCPTools._project_path) / file_changed
                        ai_changed_files.add(file_path.resolve())

                # Detect manual edits: modified files that are NOT in AI-changed list
                manual_edit_files = []
                project_path_resolved = Path(MemMCPTools._project_path).resolve()
                for modified_file in current_file_status["modified"]:
                    # modified_file is already a Path object with absolute path (resolved)
                    if modified_file.resolve() not in ai_changed_files:
                        # Use relative path (relative to project_path) for snapshot
                        try:
                            rel_path = str(modified_file.relative_to(project_path_resolved))
                            manual_edit_files.append(rel_path)
                        except ValueError:
                            # File is outside project path, use absolute path
                            LOGGER.warning(f"File {modified_file} is outside project path")
                            manual_edit_files.append(str(modified_file))

                # Step 1: Capture manual edits first (if any)
                if manual_edit_files:
                    LOGGER.info(f"Detected manual edits: {manual_edit_files}")
                    manual_snap_status = memov_manager.snapshot(
                        file_paths=manual_edit_files,
                        prompt="Manual edits detected before AI operation",
                        response=f"User manually edited: {', '.join([Path(f).name for f in manual_edit_files])}",
                        agent_plan=None,  # No agent plan for manual edits
                        by_user=True,
                    )
                    if manual_snap_status is not MemStatus.SUCCESS:
                        LOGGER.error(f"Failed to snapshot manual edits: {manual_snap_status}")
                        return f"[ERROR] Failed to snapshot manual edits: {manual_snap_status}"
                    LOGGER.info(f"Captured manual edits in separate commit")

                # Step 2: Process AI changes
                # Separate AI-changed files into untracked and modified
                files_to_track = []
                files_to_snap = []
                files_processed = []

                for file_changed in files_changed.split(","):
                    file_changed = file_changed.strip()
                    if not file_changed:
                        continue

                    file_changed_Path = Path(MemMCPTools._project_path) / file_changed

                    # Check if file is untracked
                    is_untracked = False
                    for untracked_file in current_file_status["untracked"]:
                        if file_changed_Path.samefile(untracked_file):
                            is_untracked = True
                            break

                    if is_untracked:
                        files_to_track.append(str(file_changed_Path))
                        files_processed.append(f"{file_changed} (tracked)")
                    else:
                        files_to_snap.append(str(file_changed_Path))
                        files_processed.append(f"{file_changed} (snapped)")

                # Track all untracked files at once
                if files_to_track:
                    LOGGER.info(f"Tracking new files: {files_to_track}")
                    track_status = memov_manager.track(
                        files_to_track,
                        prompt=user_prompt,
                        response=original_response,
                        by_user=False,
                    )
                    if track_status is not MemStatus.SUCCESS:
                        LOGGER.error(f"Failed to track files: {track_status}")
                        return f"[ERROR] Failed to track files: {track_status}"

                # Snap all AI-modified files at once (fine-grained snapshot)
                if files_to_snap:
                    LOGGER.info(f"Snapping AI-modified files: {files_to_snap}")
                    snap_status = memov_manager.snapshot(
                        file_paths=files_to_snap,
                        prompt=user_prompt,
                        response=original_response,
                        agent_plan=agent_plan_str,
                        by_user=False,
                    )
                    if snap_status is not MemStatus.SUCCESS:
                        LOGGER.error(f"Failed to snap files: {snap_status}")
                        return f"[ERROR] Failed to snap files: {snap_status}"

                # Build detailed result message
                result_parts = ["[SUCCESS] Changes recorded successfully"]
                if manual_edit_files:
                    result_parts.append(
                        f"Manual edits captured: {', '.join([Path(f).name for f in manual_edit_files])}"
                    )
                result_parts.append(f"Prompt: {user_prompt}")
                result_parts.append(f"Response: {len(original_response)} characters")
                if agent_plan_str:
                    result_parts.append(f"Agent plan: {len(agent_plan_str)} characters")
                result_parts.append(f"AI changes: {', '.join(files_processed)}")
                result = "\n".join(result_parts)

                # Auto-sync to VectorDB after recording changes (only if RAG mode is available)
                if CHROMADB_AVAILABLE:
                    LOGGER.info("Auto-syncing to VectorDB after snap...")
                    pending_count = memov_manager.get_pending_writes_count()
                    if pending_count > 0:
                        successful, failed = memov_manager.sync_to_vectordb()
                        if failed == 0:
                            result += f"\n[AUTO-SYNC] Successfully synced {successful} operation(s) to VectorDB"
                        else:
                            result += f"\n[AUTO-SYNC] Synced with errors: {successful} successful, {failed} failed"

                LOGGER.info(f"Operation completed successfully: {result}")
                return result

        except Exception as e:
            error_msg = f"[ERROR] Error in snap: {str(e)}"
            LOGGER.error(error_msg, exc_info=True)
            return error_msg

    @staticmethod
    @mcp.tool()
    def mem_history(limit: int = 20, commit_hash: str = "") -> str:
        """View memov history - list of snapshots with prompts, responses, and file changes.

        **Purpose:**
        Browse the history of AI-assisted code changes recorded by memov.
        Each entry shows what was asked, what was done, and which files were changed.

        **When to use:**
        - To understand what changes were made previously
        - To find a specific commit to jump back to
        - To review the sequence of AI interactions
        - Before using `mem jump` to restore a previous state

        Args:
            limit: Maximum number of commits to return (default: 20, max: 50)
            commit_hash: If provided, show detailed info for this specific commit only

        Returns:
            Formatted history with commit info, prompts, responses, and files
        """
        try:
            LOGGER.info(f"mem_history called with limit={limit}, commit_hash={commit_hash}")

            if MemMCPTools._project_path is None:
                raise ValueError("Project path is not set.")

            if not os.path.exists(MemMCPTools._project_path):
                raise ValueError(f"Project path '{MemMCPTools._project_path}' does not exist.")

            memov_manager = MemovManager(project_path=MemMCPTools._project_path)

            if (check_status := memov_manager.check()) is not MemStatus.SUCCESS:
                return f"[ERROR] Memov not initialized: {check_status}. Run 'mem init' first."

            # Limit to reasonable number
            limit = min(max(1, limit), 50)

            # Get history data
            history = memov_manager.get_history(limit=limit)

            if not history:
                return "[INFO] No history found. Start by tracking files with 'mem track'."

            # If specific commit requested, show detailed view
            if commit_hash and commit_hash.strip():
                target = commit_hash.strip().lower()
                for entry in history:
                    if entry["commit_hash"].startswith(target) or entry["short_hash"] == target:
                        return MemMCPTools._format_commit_detail(entry)
                return f"[ERROR] Commit '{commit_hash}' not found in history."

            # Format history list
            return MemMCPTools._format_history_list(history)

        except Exception as e:
            error_msg = f"[ERROR] Error in mem_history: {str(e)}"
            LOGGER.error(error_msg, exc_info=True)
            return error_msg

    @staticmethod
    def _format_history_list(history: list[dict]) -> str:
        """Format history list for display."""
        lines = []
        lines.append("=" * 80)
        lines.append("MEMOV HISTORY")
        lines.append("=" * 80)
        lines.append("")

        for entry in history:
            marker = "* " if entry["is_head"] else "  "
            branch_str = f"[{entry['branch']}]" if entry["branch"] else ""

            lines.append(f"{marker}{entry['short_hash']} {branch_str}")
            lines.append(f"   Operation: {entry['operation']}")

            if entry["prompt"]:
                prompt_preview = (
                    entry["prompt"][:80] + "..." if len(entry["prompt"]) > 80 else entry["prompt"]
                )
                lines.append(f"   Prompt: {prompt_preview}")

            if entry["files"]:
                files_preview = ", ".join(entry["files"][:3])
                if len(entry["files"]) > 3:
                    files_preview += f" (+{len(entry['files']) - 3} more)"
                lines.append(f"   Files: {files_preview}")

            if entry["timestamp"]:
                lines.append(f"   Time: {entry['timestamp']}")

            lines.append("")

        lines.append("=" * 80)
        lines.append(f"Showing {len(history)} commits. Use commit_hash parameter for details.")
        return "\n".join(lines)

    @staticmethod
    def _format_commit_detail(entry: dict) -> str:
        """Format detailed commit info."""
        lines = []
        lines.append("=" * 80)
        lines.append(f"COMMIT DETAIL: {entry['commit_hash']}")
        lines.append("=" * 80)
        lines.append("")

        lines.append(f"Hash: {entry['commit_hash']}")
        lines.append(f"Operation: {entry['operation']}")
        if entry["branch"]:
            lines.append(f"Branch: {entry['branch']}")
        lines.append(f"Is HEAD: {'Yes' if entry['is_head'] else 'No'}")
        if entry["timestamp"]:
            lines.append(f"Timestamp: {entry['timestamp']}")
        if entry["author"]:
            lines.append(f"Author: {entry['author']}")
        lines.append("")

        if entry["prompt"]:
            lines.append("PROMPT:")
            lines.append(entry["prompt"])
            lines.append("")

        if entry["response"]:
            lines.append("RESPONSE:")
            lines.append(entry["response"])
            lines.append("")

        if entry["agent_plan"]:
            lines.append("AGENT PLAN:")
            lines.append(entry["agent_plan"])
            lines.append("")

        if entry["files"]:
            lines.append(f"FILES ({len(entry['files'])}):")
            for f in entry["files"]:
                lines.append(f"  - {f}")
            lines.append("")

        lines.append("=" * 80)
        return "\n".join(lines)

    @staticmethod
    @mcp.tool()
    def mem_ui(port: int = 38888) -> str:
        """Open the MemoV Web UI to visually browse your AI coding history.

        **Purpose:**
        Launch a local web interface for exploring your memov history with:
        - Timeline view of all commits
        - Branch filtering and navigation
        - Visual diff viewer for each file
        - Jump to any snapshot with one click

        **When to use:**
        - To get a visual overview of your AI coding history
        - When you need to explore commits interactively
        - To compare changes across multiple snapshots
        - Before jumping to a previous state

        Args:
            port: Port number for the web server (default: 38888)

        Returns:
            URL to open in browser
        """
        import subprocess
        import sys
        import time

        try:
            LOGGER.info(f"mem_ui called with port={port}")

            if MemMCPTools._project_path is None:
                raise ValueError("Project path is not set.")

            if not os.path.exists(MemMCPTools._project_path):
                raise ValueError(f"Project path '{MemMCPTools._project_path}' does not exist.")

            memov_manager = MemovManager(project_path=MemMCPTools._project_path)

            if (check_status := memov_manager.check()) is not MemStatus.SUCCESS:
                return f"[ERROR] Memov not initialized: {check_status}. Run 'mem init' first."

            # Start the web server in background
            url = f"http://localhost:{port}"

            # Use subprocess to start the web server
            # Use repr() to properly escape the path (handles Windows backslashes)
            escaped_path = repr(MemMCPTools._project_path)
            cmd = [
                sys.executable,
                "-c",
                f"from memov.web.server import start_server; start_server({escaped_path}, port={port})",
            ]

            # Platform-specific subprocess options for background process
            import platform

            if platform.system() == "Windows":
                # Windows: use CREATE_NEW_PROCESS_GROUP and DETACHED_PROCESS
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
            else:
                # Unix: use start_new_session
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )

            # Give it a moment to start
            time.sleep(1)

            lines = []
            lines.append("[SUCCESS] MemoV Web UI started!")
            lines.append("")
            lines.append(f"🌐 Open in browser: {url}")
            lines.append("")
            lines.append("Features:")
            lines.append("  • Timeline view with expandable commit cards")
            lines.append("  • Branch filtering in sidebar")
            lines.append("  • Click any file to view its diff")
            lines.append("  • Jump to any snapshot with one click")
            lines.append("")
            lines.append("The server runs in background. Close the terminal to stop it.")

            return "\n".join(lines)

        except Exception as e:
            error_msg = f"[ERROR] Error in mem_ui: {str(e)}"
            LOGGER.error(error_msg, exc_info=True)
            return error_msg

    @staticmethod
    @mcp.tool()
    def mem_jump(commit_hash: str) -> str:
        """Jump to a specific snapshot, restoring all tracked files and creating a new branch.

        **Purpose:**
        Time-travel to a previous state by restoring all tracked files to exactly
        how they were at a specific commit. This is useful for:
        - Undoing unwanted changes
        - Reviewing or testing a previous version
        - Starting fresh from a known good state

        **What happens:**
        - This will OVERWRITE current file contents with the snapshot version
        - A new branch (e.g., "jump/1") is automatically created at this commit
        - You can immediately start making changes and snapping on this branch
        - Files that existed in the snapshot but were deleted will be restored
        - Files that exist now but didn't exist in the snapshot will be removed

        **Workflow:**
        1. Use `mem_history()` to find the commit hash you want to jump to
        2. Use `mem_jump(commit_hash)` to restore files and create a new branch
        3. Continue working - you're now on a new branch ready for snaps

        Args:
            commit_hash: The commit hash to jump to (full or short form, e.g., "abc123")

        Returns:
            Success or error message with details about the jump
        """
        try:
            LOGGER.info(f"mem_jump called with commit_hash={commit_hash}")

            if not commit_hash or not commit_hash.strip():
                return (
                    "[ERROR] commit_hash is required. Use mem_history() to find available commits."
                )

            if MemMCPTools._project_path is None:
                raise ValueError("Project path is not set.")

            if not os.path.exists(MemMCPTools._project_path):
                raise ValueError(f"Project path '{MemMCPTools._project_path}' does not exist.")

            memov_manager = MemovManager(project_path=MemMCPTools._project_path)

            if (check_status := memov_manager.check()) is not MemStatus.SUCCESS:
                return f"[ERROR] Memov not initialized: {check_status}. Run 'mem init' first."

            # Get commit info before jumping for better feedback
            history = memov_manager.get_history(limit=50)
            target_entry = None
            target_hash = commit_hash.strip().lower()
            for entry in history:
                if (
                    entry["commit_hash"].startswith(target_hash)
                    or entry["short_hash"] == target_hash
                ):
                    target_entry = entry
                    break

            if not target_entry:
                return f"[ERROR] Commit '{commit_hash}' not found. Use mem_history() to see available commits."

            # Perform the jump (returns 3-tuple: status, branch, error_detail)
            jump_status, new_branch, error_detail = memov_manager.jump(commit_hash.strip())

            if jump_status is not MemStatus.SUCCESS:
                return f"[ERROR] Failed to jump to commit '{commit_hash}': {error_detail or jump_status}"

            # Build success message
            lines = []
            lines.append(f"[SUCCESS] Jumped to commit {target_entry['short_hash']}")
            lines.append(f"Created branch: {new_branch}")
            lines.append("")
            lines.append(f"Commit: {target_entry['commit_hash']}")
            lines.append(f"Operation: {target_entry['operation']}")
            if target_entry["prompt"]:
                prompt_preview = (
                    target_entry["prompt"][:100] + "..."
                    if len(target_entry["prompt"]) > 100
                    else target_entry["prompt"]
                )
                lines.append(f"Prompt: {prompt_preview}")
            if target_entry["files"]:
                lines.append(f"Files restored: {len(target_entry['files'])}")
            lines.append("")
            lines.append(f"You are now on branch '{new_branch}' - ready to snap!")

            return "\n".join(lines)

        except Exception as e:
            error_msg = f"[ERROR] Error in mem_jump: {str(e)}"
            LOGGER.error(error_msg, exc_info=True)
            return error_msg


# RAG-dependent MCP tools (only registered when [rag] extras are installed)
if CHROMADB_AVAILABLE:

    @staticmethod
    @MemMCPTools.mcp.tool()
    def mem_sync() -> str:
        """Sync all pending operations to VectorDB for semantic search capabilities.

        **Purpose:**
        This tool synchronizes your recorded interactions (prompts, responses, agent plans)
        to the VectorDB, enabling semantic search through your code history.

        **When to use:**
        - After recording several interactions to make them searchable
        - Before using vibe_search or vibe_debug tools
        - Periodically to keep VectorDB up to date

        **Requirements:**
        - Requires [rag] extras: Install with `pip install memov[rag]`

        Returns:
            Sync result with number of operations synced
        """
        try:
            LOGGER.info("mem_sync called")

            if MemMCPTools._project_path is None:
                raise ValueError("Project path is not set.")

            if not os.path.exists(MemMCPTools._project_path):
                raise ValueError(f"Project path '{MemMCPTools._project_path}' does not exist.")

            memov_manager = MemovManager(project_path=MemMCPTools._project_path)

            if (check_status := memov_manager.check()) is not MemStatus.SUCCESS:
                return f"[ERROR] Memov not initialized: {check_status}. Run 'mem init' first."

            pending_count = memov_manager.get_pending_writes_count()
            if pending_count == 0:
                return "[INFO] No pending operations to sync."

            successful, failed = memov_manager.sync_to_vectordb()

            if failed == 0:
                return f"[SUCCESS] Synced {successful} operation(s) to VectorDB"
            else:
                return f"[PARTIAL] Synced with errors: {successful} successful, {failed} failed"

        except Exception as e:
            error_msg = f"[ERROR] Error in mem_sync: {str(e)}"
            LOGGER.error(error_msg, exc_info=True)
            return error_msg

    @MemMCPTools.mcp.tool()
    def validate_commit(commit_hash: str, detailed: bool = True) -> str:
        """Validate a specific commit by comparing prompt/response with actual code changes.

        **Purpose:**
        This tool helps debug and review AI-assisted development by checking if:
        - The actual code changes align with the original prompt
        - All intended files were modified
        - No unexpected files were changed (context drift detection)
        - The changes are reasonable in scope

        **When to use:**
        - After completing a feature to verify alignment
        - When debugging unexpected behavior
        - To review if previous changes match their stated intent
        - When investigating potential context drift issues

        **What it checks:**
        1. Extracts prompt, response, and agent_plan from commit metadata
        2. Identifies actual files changed in the commit
        3. Compares expected files (from prompt) vs actual files changed
        4. Calculates alignment score (0.0-1.0) based on multiple factors
        5. Identifies issues and provides recommendations

        **Requirements:**
        - Requires [rag] extras: Install with `pip install memov[rag]`

        Args:
            commit_hash: The commit hash to validate (full or short form, e.g., "a1b2c3d")
            detailed: If True, includes full details. If False, returns summary only. (default: True)

        Returns:
            Validation report with alignment analysis, issues, and recommendations
        """
        try:
            LOGGER.info(f"validate_commit called for: {commit_hash}")

            if MemMCPTools._project_path is None:
                raise ValueError("Project path is not set.")

            if not os.path.exists(MemMCPTools._project_path):
                raise ValueError(f"Project path '{MemMCPTools._project_path}' does not exist.")

            # Prepare the manager and validator
            memov_manager = MemovManager(project_path=MemMCPTools._project_path)

            # Check if memov is initialized
            if (check_status := memov_manager.check()) is not MemStatus.SUCCESS:
                return f"[ERROR] Memov not initialized: {check_status}. Run 'mem init' first."

            # Create validator
            validator = DebugValidator(memov_manager)

            # Validate the commit
            result = validator.validate_commit(commit_hash)

            # Format output
            lines = []
            lines.append("=" * 70)
            lines.append(f"VALIDATION REPORT: {result.commit_hash[:8]}")
            lines.append("=" * 70)
            lines.append("")

            # Alignment summary
            status = "✓ ALIGNED" if result.is_aligned else "✗ NOT ALIGNED"
            lines.append(f"Status: {status}")
            lines.append(f"Alignment Score: {result.alignment_score:.2f} / 1.00")
            lines.append("")

            # Prompt/Response info
            if detailed:
                if result.prompt:
                    lines.append("Prompt:")
                    lines.append(f"  {result.prompt[:200]}")
                    if len(result.prompt) > 200:
                        lines.append("  ...")
                    lines.append("")

                if result.agent_plan:
                    lines.append("Agent Plan:")
                    lines.append(f"  {result.agent_plan[:200]}")
                    if len(result.agent_plan) > 200:
                        lines.append("  ...")
                    lines.append("")

            # File changes summary
            lines.append(f"Files Changed: {len(result.actual_changes)}")
            if result.actual_changes:
                for fc in result.actual_changes[:5]:
                    lines.append(f"  [{fc.change_type.upper()}] {fc.file_path}")
                if len(result.actual_changes) > 5:
                    lines.append(f"  ... and {len(result.actual_changes) - 5} more")
            lines.append("")

            # Expected vs Actual
            if result.expected_files:
                lines.append(f"Expected Files (from prompt): {len(result.expected_files)}")
                if detailed:
                    for ef in result.expected_files[:3]:
                        lines.append(f"  • {ef}")
                    if len(result.expected_files) > 3:
                        lines.append(f"  ... and {len(result.expected_files) - 3} more")
                lines.append("")

            # Issues
            if result.unexpected_files:
                lines.append(f"⚠ Unexpected Files: {len(result.unexpected_files)}")
                for uf in result.unexpected_files[:3]:
                    lines.append(f"  • {uf}")
                if len(result.unexpected_files) > 3:
                    lines.append(f"  ... and {len(result.unexpected_files) - 3} more")
                lines.append("")

            if result.missing_files:
                lines.append(f"⚠ Missing Expected Files: {len(result.missing_files)}")
                for mf in result.missing_files[:3]:
                    lines.append(f"  • {mf}")
                if len(result.missing_files) > 3:
                    lines.append(f"  ... and {len(result.missing_files) - 3} more")
                lines.append("")

            # Issues and recommendations
            if result.issues:
                lines.append(f"Issues ({len(result.issues)}):")
                for issue in result.issues:
                    lines.append(f"  ✗ {issue}")
                lines.append("")

            if result.recommendations:
                lines.append(f"Recommendations ({len(result.recommendations)}):")
                for rec in result.recommendations:
                    lines.append(f"  → {rec}")
                lines.append("")

            lines.append("=" * 70)

            return "\n".join(lines)

        except Exception as e:
            error_msg = f"[ERROR] Error in validate_commit: {str(e)}"
            LOGGER.error(error_msg, exc_info=True)
            return error_msg

    @MemMCPTools.mcp.tool()
    def validate_recent(n: int = 5) -> str:
        """Validate the N most recent commits for alignment with their prompts.

        **Purpose:**
        Batch validation of recent commits to identify patterns of misalignment or context drift.
        This is useful for reviewing a series of changes and ensuring overall quality.

        **When to use:**
        - At the end of a coding session to review all changes
        - Before creating a pull request
        - When debugging issues that may have originated from earlier changes
        - To identify if context drift is occurring over time

        **What it provides:**
        - Summary statistics (total validated, aligned count, average score)
        - Individual validation results for each commit
        - Aggregate issues and recommendations

        **Requirements:**
        - Requires [rag] extras: Install with `pip install memov[rag]`

        Args:
            n: Number of recent commits to validate (default: 5, max: 20)

        Returns:
            Comprehensive validation report for recent commits
        """
        try:
            LOGGER.info(f"validate_recent called for n={n}")

            # Limit to reasonable number
            n = min(max(1, n), 20)

            if MemMCPTools._project_path is None:
                raise ValueError("Project path is not set.")

            if not os.path.exists(MemMCPTools._project_path):
                raise ValueError(f"Project path '{MemMCPTools._project_path}' does not exist.")

            # Prepare the manager and validator
            memov_manager = MemovManager(project_path=MemMCPTools._project_path)

            # Check if memov is initialized
            if (check_status := memov_manager.check()) is not MemStatus.SUCCESS:
                return f"[ERROR] Memov not initialized: {check_status}. Run 'mem init' first."

            # Create validator
            validator = DebugValidator(memov_manager)

            # Validate recent commits
            results = validator.validate_recent_commits(n)

            if not results:
                return "[INFO] No commits found to validate."

            # Generate report
            report = validator.generate_report(results)

            return report

        except Exception as e:
            error_msg = f"[ERROR] Error in validate_recent: {str(e)}"
            LOGGER.error(error_msg, exc_info=True)
            return error_msg

    @MemMCPTools.mcp.tool()
    def vibe_debug(
        query: str,
        error_message: str = "",
        stack_trace: str = "",
        user_logs: str = "",
        models: str = "",
        n_results: int = 5,
    ) -> str:
        """Debug code issues using RAG search + multi-model LLM comparison (VIBE debugging).

        **Purpose:**
        This tool combines the power of:
        1. **RAG (Retrieval Augmented Generation)**: Searches your code history to find
           relevant context, similar issues, and related code changes
        2. **Multi-model LLM comparison**: Queries multiple AI models (GPT-4, Claude, Gemini)
           in parallel to get diverse debugging insights and recommendations

        **When to use:**
        - Encountering runtime errors or bugs
        - Need to understand why code is behaving unexpectedly
        - Want multiple AI perspectives on a complex issue
        - Looking for historical context about similar problems
        - Need actionable debugging recommendations

        **What it does:**
        1. Searches VectorDB for relevant code history using your query + error info
        2. Retrieves similar commits, prompts, and code changes
        3. Builds comprehensive context with error traces and logs
        4. Queries multiple LLM models in parallel for analysis
        5. Compares responses and extracts consensus recommendations

        **Requirements:**
        - VectorDB must be populated (run `mem sync` first)
        - LiteLLM installed: `pip install litellm`
        - API keys configured for desired models:
          - OPENAI_API_KEY for GPT models
          - ANTHROPIC_API_KEY for Claude
          - GEMINI_API_KEY or GOOGLE_API_KEY for Gemini
          - COHERE_API_KEY for Command models
          - MISTRAL_API_KEY for Mistral models

        Args:
            query: Main debug question (e.g., "Why is the API returning 500 errors?")
            error_message: Error message text (optional)
            stack_trace: Stack trace or error traceback (optional)
            user_logs: Relevant log output (optional)
            models: Comma-separated list of model names to query (optional)
                   Examples: "gpt-4o-mini,claude-3-5-sonnet-20241022,gemini/gemini-1.5-flash"
                   Default: Uses GPT-4o-mini, Claude Sonnet, Gemini Flash
            n_results: Number of relevant code snippets to retrieve (default: 5)

        Returns:
            Comprehensive debugging report with:
            - RAG-retrieved relevant code context
            - Analysis from each LLM model
            - Consensus recommendations
            - Specific fix suggestions

        Examples:
            1. Simple error debugging:
               query="API endpoint returning 500",
               error_message="Internal Server Error",
               stack_trace="<full traceback>"

            2. Performance issue:
               query="Database queries are slow",
               user_logs="Query took 5.2s to execute"

            3. Custom models:
               query="Authentication failing",
               models="gpt-4o,claude-3-5-sonnet-20241022"
        """
        try:
            LOGGER.info(f"vibe_debug called with query: {query}")

            if MemMCPTools._project_path is None:
                raise ValueError("Project path is not set.")

            if not os.path.exists(MemMCPTools._project_path):
                raise ValueError(f"Project path '{MemMCPTools._project_path}' does not exist.")

            # Prepare the manager
            memov_manager = MemovManager(project_path=MemMCPTools._project_path)

            # Check if memov is initialized
            if (check_status := memov_manager.check()) is not MemStatus.SUCCESS:
                return f"[ERROR] Memov not initialized: {check_status}. Run 'mem init' first."

            # Check if VectorDB has data
            db_info = memov_manager.get_vectordb_info()
            if db_info.get("count", 0) == 0:
                return (
                    "[ERROR] VectorDB is empty. Please run 'mem sync' first to populate "
                    "the database with your code history."
                )

            # Parse models if provided
            model_list = None
            if models and models.strip():
                model_list = [m.strip() for m in models.split(",") if m.strip()]

            # Create LLM client and debugger
            try:
                llm_client = LLMClient(models=model_list) if model_list else LLMClient()
            except ImportError:
                return (
                    "[ERROR] LiteLLM not installed. Install with: pip install litellm\n\n"
                    "Also configure API keys:\n"
                    "  export OPENAI_API_KEY=your_key\n"
                    "  export ANTHROPIC_API_KEY=your_key\n"
                    "  export GEMINI_API_KEY=your_key"
                )

            debugger = RAGDebugger(memov_manager, llm_client)

            # Build debug context using RAG
            LOGGER.info("Building debug context with RAG...")
            context = debugger.build_debug_context(
                query=query,
                error_message=error_message if error_message else None,
                stack_trace=stack_trace if stack_trace else None,
                user_logs=user_logs if user_logs else None,
                n_results=n_results,
            )

            # Query multiple LLMs
            LOGGER.info("Querying multiple LLM models...")
            result = debugger.debug_with_llm(
                query=query,
                context=context,
                models=model_list,
                use_async=True,
            )

            # Format and return result
            report = debugger.format_debug_result(result, include_full_responses=True)

            LOGGER.info("VIBE debugging completed successfully")
            return report

        except Exception as e:
            error_msg = f"[ERROR] Error in vibe_debug: {str(e)}"
            LOGGER.error(error_msg, exc_info=True)
            return error_msg

    @MemMCPTools.mcp.tool()
    def vibe_search(query: str, n_results: int = 5, content_type: str = "") -> str:
        """Search code history using RAG (without LLM analysis).

        **Purpose:**
        Fast semantic search through your code history to find relevant:
        - Prompts: What you asked the AI to do
        - Responses: What the AI said it did
        - Agent plans: High-level summaries of changes made
        - Code changes: Which files were modified

        Use this when you need quick context retrieval without full LLM analysis.

        **When to use:**
        - Finding when a specific feature was added
        - Locating code that handles similar functionality
        - Understanding when/why a file was changed
        - Quick historical context lookup

        **Requirements:**
        - Requires [rag] extras: Install with `pip install memov[rag]`

        Args:
            query: Search query (natural language)
            n_results: Number of results to return (default: 5, max: 20)
            content_type: Filter by content type: "prompt", "response", "agent_plan", or "" for all

        Returns:
            Formatted search results with relevance scores and commit info

        Examples:
            query="authentication implementation"
            query="database connection", content_type="agent_plan"
            query="API error handling", n_results=10
        """
        try:
            LOGGER.info(f"vibe_search called with query: {query}")

            if MemMCPTools._project_path is None:
                raise ValueError("Project path is not set.")

            if not os.path.exists(MemMCPTools._project_path):
                raise ValueError(f"Project path '{MemMCPTools._project_path}' does not exist.")

            # Prepare the manager
            memov_manager = MemovManager(project_path=MemMCPTools._project_path)

            # Check if memov is initialized
            if (check_status := memov_manager.check()) is not MemStatus.SUCCESS:
                return f"[ERROR] Memov not initialized: {check_status}. Run 'mem init' first."

            # Limit results
            n_results = min(max(1, n_results), 20)

            # Search
            debugger = RAGDebugger(memov_manager, llm_client=None)

            if content_type and content_type.strip():
                content_types = [content_type.strip()]
            else:
                content_types = ["prompt", "response", "agent_plan"]

            results = debugger.search_relevant_code(
                query=query,
                n_results=n_results,
                content_types=content_types,
            )

            # Format results
            lines = []
            lines.append("=" * 80)
            lines.append("🔍 RAG SEARCH RESULTS")
            lines.append("=" * 80)
            lines.append("")
            lines.append(f"Query: {query}")
            lines.append(f"Found: {len(results)} results")
            lines.append("")

            for i, result in enumerate(results, 1):
                metadata = result.get("metadata", {})
                text = result.get("text", "")
                distance = result.get("distance", 1.0)
                relevance = 1.0 - distance

                commit_hash = metadata.get("commit_hash", "unknown")
                content_type_val = metadata.get("content_type", "unknown")
                files = metadata.get("files", "")
                operation = metadata.get("operation_type", "unknown")

                lines.append(f"[{i}] Relevance: {relevance:.2f}")
                lines.append(f"    Commit: {commit_hash[:8]}")
                lines.append(f"    Type: {content_type_val}")
                lines.append(f"    Operation: {operation}")

                if files:
                    files_list = [f.strip() for f in files.split(",") if f.strip()]
                    lines.append(f"    Files: {', '.join(files_list[:3])}")
                    if len(files_list) > 3:
                        lines.append(f"           ... and {len(files_list) - 3} more")

                # Show text preview
                preview = text[:200] + "..." if len(text) > 200 else text
                lines.append(f"    Content: {preview}")
                lines.append("")

            lines.append("=" * 80)

            return "\n".join(lines)

        except Exception as e:
            error_msg = f"[ERROR] Error in vibe_search: {str(e)}"
            LOGGER.error(error_msg, exc_info=True)
            return error_msg


def main():
    """Main entry point for the MCP server"""
    import asyncio

    mem_mcp_tools = MemMCPTools("D:/Projects/temp")
    asyncio.run(mem_mcp_tools.mcp.call_tool("mem_snap", {"files_changed": "123.py"}))


if __name__ == "__main__":
    main()
