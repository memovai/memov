import io
import json
import logging
import os
import tarfile
import traceback
from collections import defaultdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import pathspec

from memov.core.git import GitManager
from memov.storage import CHROMADB_AVAILABLE
from memov.storage.vectordb import VectorDB
from memov.utils.print_utils import Color
from memov.utils.string_utils import short_msg

LOGGER = logging.getLogger(__name__)


class MemStatus(Enum):
    """Mem operation status."""

    SUCCESS = "success"
    PROJECT_NOT_FOUND = "project_not_found"
    BARE_REPO_NOT_FOUND = "bare_repo_not_found"
    FAILED_TO_COMMIT = "failed_to_commit"
    UNKNOWN_ERROR = "unknown_error"


class MemovManager:
    def __init__(
        self,
        project_path: str,
        default_name: Optional[str] = None,
        default_email: Optional[str] = None,
    ) -> None:
        """Initialize the MemovManager."""
        self.project_path = project_path
        self.default_name = default_name
        self.default_email = default_email

        # Memov config paths
        self.mem_root_path = os.path.join(self.project_path, ".mem")
        self.bare_repo_path = os.path.join(self.mem_root_path, "memov.git")
        self.branches_config_path = os.path.join(self.mem_root_path, "branches.json")
        self.memignore_path = os.path.join(self.project_path, ".memignore")
        self.vectordb_path = os.path.join(self.mem_root_path, "vectordb")
        self.pending_writes_path = os.path.join(self.mem_root_path, "pending_writes.json")

        # Initialize VectorDB (lazy initialization - only when needed)
        self._vectordb: Optional[VectorDB] = None

        # Memory cache for pending VectorDB writes
        # Format: list of dicts with keys: operation_type, commit_hash, prompt, response, agent_plan, by_user, files
        # Load from disk if exists (to persist across CLI command invocations)
        self._pending_writes: list[dict] = self._load_pending_writes()

    def is_rag_available(self) -> bool:
        """Check if RAG mode (ChromaDB) is available."""
        return CHROMADB_AVAILABLE

    @property
    def vectordb(self) -> VectorDB:
        """Get or initialize the VectorDB instance.

        Raises:
            ImportError: If RAG mode dependencies are not installed.
        """
        if not self.is_rag_available():
            raise ImportError(
                "RAG mode is not available. ChromaDB dependencies are not installed.\n"
                "Install with: pip install memov[rag] or uv pip install memov[rag]"
            )

        if self._vectordb is None:
            # Use lightweight default embedding (no heavy dependencies)
            # To use other backends, set MEMOV_EMBEDDING_BACKEND environment variable:
            # - "default": ChromaDB built-in (~50MB) - RECOMMENDED
            # - "fastembed": ONNX Runtime (~30MB)
            # - "openai": OpenAI API (<5MB, requires API key)
            # - "sentence-transformers": Original (~1.5GB)
            embedding_backend = os.getenv("MEMOV_EMBEDDING_BACKEND", "default")

            self._vectordb = VectorDB(
                persist_directory=Path(self.vectordb_path),
                collection_name="memov_memories",
                chunk_size=768,
                embedding_backend=embedding_backend,
            )
        return self._vectordb

    def check(self, only_basic_check: bool = False) -> MemStatus:
        """Check some basic conditions for the memov repo."""
        # Check project path
        if not os.path.exists(self.project_path):
            LOGGER.error(f"Project path {self.project_path} does not exist.")
            return MemStatus.PROJECT_NOT_FOUND

        # If only basic check is required, return early
        if only_basic_check:
            LOGGER.debug("Only basic check is required, skipping further checks.")
            return MemStatus.SUCCESS

        # Check the bare repo
        if not os.path.exists(self.bare_repo_path):
            LOGGER.error(
                f"Memov bare repo {self.bare_repo_path} does not exist.\nPlease run `mem -h` to see the help message."
            )
            return MemStatus.BARE_REPO_NOT_FOUND

        return MemStatus.SUCCESS

    def version(self) -> str:
        """Show version information."""
        # Read version from pyproject.toml or package metadata
        import importlib.metadata

        try:
            version = importlib.metadata.version("memov")
            LOGGER.info(f"memov version {version}")
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"
            LOGGER.info("memov version unknown (development)")

        return version

    def init(self) -> MemStatus:
        """Initialize a memov repo if it doesn't exist."""
        try:
            # Initialize .mem directory
            os.makedirs(self.mem_root_path, exist_ok=True)
            if not os.path.exists(self.bare_repo_path):
                GitManager.create_bare_repo(self.bare_repo_path)

            # Ensure .memignore exists and is tracked
            if not os.path.exists(self.memignore_path):
                with open(self.memignore_path, "w") as f:
                    f.write("# Add files/directories to ignore from memov tracking\n")
                    f.write("# Ignore all hidden files (starting with .)\n")
                    f.write(".*\n")
                self.track(
                    [self.memignore_path],
                    prompt="Initialize .memignore",
                    response="Created default .memignore file",
                )

            return MemStatus.SUCCESS
        except Exception as e:
            LOGGER.error(f"Error initializing memov project: {e}")
            return MemStatus.UNKNOWN_ERROR

    def track(
        self,
        file_paths: list[str],
        prompt: Optional[str] = None,
        response: Optional[str] = None,
        by_user: bool = False,
    ) -> MemStatus:
        """Track files in the memov repo, generating a commit to record the operation."""
        try:
            # Return early if no file paths are provided
            if not file_paths:
                LOGGER.error("No files to track.")
                return MemStatus.SUCCESS

            # Get the head commit of the memov repo
            head_commit = GitManager.get_commit_id_by_ref(
                self.bare_repo_path, "refs/memov/HEAD", verbose=False
            )
            if not head_commit:  # If HEAD commit does not exist, try to get the main branch commit
                head_commit = GitManager.get_commit_id_by_ref(
                    self.bare_repo_path, "main", verbose=False
                )
            if not head_commit:  # If still no commit, set to None
                head_commit = None

            # Get all currently tracked files in the memov repo
            tracked_file_rel_paths, tracked_file_abs_paths = [], []

            if head_commit:
                tracked_file_rel_paths, tracked_file_abs_paths = GitManager.get_files_by_commit(
                    self.bare_repo_path, head_commit
                )

            # Only track new files that are not already tracked
            new_files = self._filter_new_files(file_paths, tracked_file_rel_paths)

            if len(new_files) == 0:
                LOGGER.warning(
                    "No new files to track. All provided files are already tracked or ignored."
                )
                return MemStatus.SUCCESS

            # Build tree with: new files from workspace, existing files from HEAD (to preserve their state)
            # This ensures we don't accidentally commit manual changes to existing files
            if head_commit:
                # Get blob hashes for all existing files in HEAD
                head_file_blobs = GitManager.get_files_and_blobs_by_commit(
                    self.bare_repo_path, head_commit, self.project_path
                )

                # Build tree structure
                tree_structure = {}

                # Add existing files with their HEAD blob hashes (preserve their state)
                for rel_path in tracked_file_rel_paths:
                    abs_resolved = (Path(self.project_path) / rel_path).resolve()
                    blob_hash = head_file_blobs.get(abs_resolved)
                    if blob_hash:
                        parts = rel_path.split("/")
                        current = tree_structure
                        for part in parts[:-1]:
                            if part not in current:
                                current[part] = {}
                            current = current[part]
                        current[parts[-1]] = blob_hash

                # Add new files with their current content (new blobs)
                for rel_path, abs_path in new_files:
                    blob_hash = GitManager.write_blob(self.bare_repo_path, abs_path)
                    if not blob_hash:
                        LOGGER.error(f"Failed to create blob for {rel_path}")
                        return MemStatus.UNKNOWN_ERROR

                    parts = rel_path.split("/")
                    current = tree_structure
                    for part in parts[:-1]:
                        if part not in current:
                            current[part] = {}
                        current = current[part]
                    current[parts[-1]] = blob_hash

                # Create commit from tree structure
                commit_msg = "Track files\n\n"
                commit_msg += f"Files: {', '.join([rel_file for rel_file, _ in new_files])}\n"
                commit_msg += (
                    f"Prompt: {prompt}\nResponse: {response}\nSource: {'User' if by_user else 'AI'}"
                )

                commit_hash = GitManager.create_commit_from_tree_structure(
                    self.bare_repo_path, tree_structure, commit_msg
                )

                if not commit_hash:
                    LOGGER.error("Failed to create track commit")
                    return MemStatus.FAILED_TO_COMMIT

                # Update branch
                self._validate_and_fix_branches()
                GitManager.ensure_git_user_config(
                    self.bare_repo_path, self.default_name, self.default_email
                )
                self._update_branch(commit_hash)
            else:
                # First commit - no existing files
                all_files = {}
                for rel_file, abs_path in new_files:
                    all_files[rel_file] = abs_path

                commit_msg = "Track files\n\n"
                commit_msg += f"Files: {', '.join([rel_file for rel_file, _ in new_files])}\n"
                commit_msg += (
                    f"Prompt: {prompt}\nResponse: {response}\nSource: {'User' if by_user else 'AI'}"
                )

                commit_hash = self._commit(commit_msg, all_files)
                if not commit_hash:
                    LOGGER.error("Failed to commit tracked files.")
                    return MemStatus.FAILED_TO_COMMIT

            LOGGER.info(
                f"Tracked file(s) in memov repo and committed: {[abs_path for _, abs_path in new_files]}"
            )

            # Add to pending writes (will be synced later via mem sync)
            self._add_to_pending_writes(
                operation_type="track",
                commit_hash=commit_hash,
                prompt=prompt,
                response=response,
                agent_plan=None,  # track operations typically don't have agent plans
                by_user=by_user,
                files=[rel_file for rel_file, _ in new_files],
            )

            return MemStatus.SUCCESS
        except Exception as e:
            tb = traceback.extract_tb(e.__traceback__)
            filename, lineno, func, code = tb[-1]  # last frame
            LOGGER.error(f"Error tracking files in memov repo: {e}, {filename}:{lineno} - {code}")
            return MemStatus.UNKNOWN_ERROR

    def snapshot(
        self,
        file_paths: Optional[list[str]] = None,
        prompt: Optional[str] = None,
        response: Optional[str] = None,
        agent_plan: Optional[str] = None,
        by_user: bool = False,
    ) -> MemStatus:
        """Create a snapshot of the current project state in the memov repo, generating a commit to record the operation.

        Args:
            file_paths: Optional list of specific file paths to snapshot. If None, snapshots all tracked files.
                       Paths can be absolute or relative to project_path.
            prompt: Optional prompt text to record with the snapshot
            response: Optional response text to record with the snapshot
            by_user: Whether the snapshot was initiated by the user (True) or AI (False)

        Returns:
            MemStatus indicating success or failure
        """
        try:
            # Check if we're on a branch (not detached)
            branches = self._load_branches()
            if branches and branches.get("current") is None:
                LOGGER.error(
                    "Not on any branch. Use 'mem switch <branch>' to create or switch to a branch first."
                )
                return MemStatus.UNKNOWN_ERROR

            # Get all tracked files in the memov repo and their previous blob hashes
            tracked_file_rel_paths, tracked_file_abs_paths = [], []
            head_commit = GitManager.get_commit_id_by_ref(
                self.bare_repo_path, "refs/memov/HEAD", verbose=False
            )
            if head_commit:
                tracked_file_rel_paths, tracked_file_abs_paths = GitManager.get_files_by_commit(
                    self.bare_repo_path, head_commit
                )

            # Return early if no tracked files are found
            if len(tracked_file_rel_paths) == 0:
                LOGGER.warning("No tracked files to snapshot. Please track files first.")
                return MemStatus.SUCCESS

            # If specific files are provided, only update those files in the snapshot
            if file_paths is not None:
                # Convert file_paths to relative paths
                specified_rel_paths = set()
                project_path_resolved = Path(self.project_path).resolve()

                for fp in file_paths:
                    # If fp is already relative, make it relative to project_path
                    # If fp is absolute, convert to relative to project_path
                    fp_path = Path(fp)
                    if fp_path.is_absolute():
                        abs_fp = fp_path.resolve()
                    else:
                        # Relative path - assume it's relative to project_path
                        abs_fp = (Path(self.project_path) / fp).resolve()

                    try:
                        # Use Path.relative_to instead of os.path.relpath to handle symlinks correctly
                        rel_fp = str(abs_fp.relative_to(project_path_resolved))
                        specified_rel_paths.add(rel_fp)
                    except ValueError:
                        LOGGER.warning(f"File {fp} is not in project path, skipping")
                        continue

                # Verify that specified files are tracked
                untracked_specified = specified_rel_paths - set(tracked_file_rel_paths)
                if untracked_specified:
                    LOGGER.warning(
                        f"{Color.RED}Some specified files are not tracked and will be skipped: {untracked_specified}{Color.RESET}"
                    )

                # Filter to only tracked specified files
                tracked_specified = specified_rel_paths & set(tracked_file_rel_paths)
                if not tracked_specified:
                    LOGGER.warning("None of the specified files are tracked. Nothing to snapshot.")
                    return MemStatus.SUCCESS

                # Get blob hashes for all files in HEAD
                head_file_blobs = GitManager.get_files_and_blobs_by_commit(
                    self.bare_repo_path, head_commit, self.project_path
                )

                # Build tree with: specified files from workspace (new blobs), others from HEAD (old blobs)
                # We need to create blobs and build the tree structure manually
                tree_structure = {}

                for rel_path in tracked_file_rel_paths:
                    if rel_path in tracked_specified:
                        # Create new blob from current workspace content
                        current_abs_path = Path(self.project_path) / rel_path
                        if current_abs_path.exists():
                            blob_hash = GitManager.write_blob(
                                self.bare_repo_path, str(current_abs_path)
                            )
                        else:
                            LOGGER.warning(
                                f"Specified file {rel_path} does not exist, using HEAD version"
                            )
                            abs_resolved = (Path(self.project_path) / rel_path).resolve()
                            blob_hash = head_file_blobs.get(abs_resolved)
                    else:
                        # Use blob from HEAD for non-specified files
                        abs_resolved = (Path(self.project_path) / rel_path).resolve()
                        blob_hash = head_file_blobs.get(abs_resolved)

                    if not blob_hash:
                        LOGGER.error(f"Failed to get blob for {rel_path}")
                        return MemStatus.UNKNOWN_ERROR

                    # Build tree structure
                    parts = rel_path.split("/")
                    current = tree_structure
                    for part in parts[:-1]:
                        if part not in current:
                            current[part] = {}
                        current = current[part]
                    current[parts[-1]] = blob_hash

                # Create tree and commit using the structure
                commit_hash = GitManager.create_commit_from_tree_structure(
                    self.bare_repo_path,
                    tree_structure,
                    f"Create snapshot\n\nFiles: {', '.join(sorted(tracked_specified))}\nPrompt: {prompt}\nResponse: {response}\nAgent Plan: {agent_plan}\nSource: {'User' if by_user else 'AI'}",
                )

                if not commit_hash:
                    LOGGER.error("Failed to create snapshot commit")
                    return MemStatus.FAILED_TO_COMMIT

                # Update branch and return
                self._validate_and_fix_branches()
                GitManager.ensure_git_user_config(
                    self.bare_repo_path, self.default_name, self.default_email
                )
                self._update_branch(commit_hash)
                LOGGER.info("Snapshot created in memov repo.")

                # Add to pending writes (will be synced later via mem sync)
                self._add_to_pending_writes(
                    operation_type="snap",
                    commit_hash=commit_hash,
                    prompt=prompt,
                    response=response,
                    agent_plan=agent_plan,
                    by_user=by_user,
                    files=list(tracked_specified),
                )

                return MemStatus.SUCCESS
            else:
                # Original behavior: snapshot all tracked files
                # Filter out new files that are not tracked or should be ignored
                new_files = self._filter_new_files([self.project_path], tracked_file_rel_paths)

                # If there are untracked files, warn the user
                if len(new_files) != 0:
                    LOGGER.warning(
                        f"{Color.RED}Untracked files present: {new_files}. They will not be included in the snapshot.{Color.RESET}"
                    )

                # Build commit file paths with all tracked files
                commit_file_paths = {}
                for rel_path, abs_path in zip(tracked_file_rel_paths, tracked_file_abs_paths):
                    commit_file_paths[rel_path] = abs_path

                commit_msg = "Create snapshot\n\n"
                commit_msg += f"Prompt: {prompt}\nResponse: {response}\nAgent Plan: {agent_plan}\nSource: {'User' if by_user else 'AI'}"

            commit_hash = self._commit(commit_msg, commit_file_paths)
            LOGGER.info("Snapshot created in memov repo.")

            # Add to pending writes (will be synced later via mem sync)
            if commit_hash:
                self._add_to_pending_writes(
                    operation_type="snap",
                    commit_hash=commit_hash,
                    prompt=prompt,
                    response=response,
                    agent_plan=agent_plan,
                    by_user=by_user,
                    files=tracked_file_rel_paths,
                )

            return MemStatus.SUCCESS
        except Exception as e:
            LOGGER.error(f"Error creating snapshot in memov repo: {e}")
            return MemStatus.UNKNOWN_ERROR

    def rename(
        self,
        old_file_path: str,
        new_file_path: str,
        prompt: Optional[str] = None,
        response: Optional[str] = None,
        by_user: bool = False,
    ) -> None:
        """Rename a tracked file in the memov repo, and generate a commit to record the operation. Supports branches."""
        try:
            old_abs_path = os.path.abspath(old_file_path)
            new_abs_path = os.path.abspath(new_file_path)
            old_rel_path = os.path.relpath(old_abs_path, self.project_path)
            old_file_existed = os.path.exists(old_abs_path)
            new_file_existed = os.path.exists(new_abs_path)

            # Return early if both paths are existing
            if old_file_existed and new_file_existed:
                LOGGER.error(f"New file path {new_abs_path} already exists.")
                return

            # Return early if both paths are not existing
            if not old_file_existed and not new_file_existed:
                LOGGER.error(
                    f"Neither old file path {old_file_path} nor new file path {new_file_path} exists."
                )
                return

            # Return early if the file is tracked on the current branch
            head_commit = GitManager.get_commit_id_by_ref(
                self.bare_repo_path, "refs/memov/HEAD", verbose=False
            )
            tracked_files = []
            if head_commit:
                tracked_files, _ = GitManager.get_files_by_commit(self.bare_repo_path, head_commit)

            if old_rel_path not in tracked_files:
                LOGGER.warning(
                    f"{Color.RED}File {old_rel_path} is not tracked, cannot rename.{Color.RESET}"
                )
                return

            # If the old file exists, rename it to the new file path
            if old_file_existed:
                os.rename(old_abs_path, new_abs_path)
                commit_msg = "Rename file\n\n"
            else:
                commit_msg = "Rename file (already renamed by user)\n\n"
            commit_msg += f"Files: {old_rel_path} -> {new_file_path}\n"
            commit_msg += (
                f"Prompt: {prompt}\nResponse: {response}\nSource: {'User' if by_user else 'AI'}"
            )

            # Commit the rename in the memov repo
            file_list = self._filter_new_files([self.project_path], tracked_file_rel_paths=None)
            file_list = {rel_path: abs_path for rel_path, abs_path in file_list}
            commit_hash = self._commit(commit_msg, file_list)

            # Add to pending writes (will be synced later via mem sync)
            if commit_hash:
                new_rel_path = os.path.relpath(new_abs_path, self.project_path)
                self._add_to_pending_writes(
                    operation_type="rename",
                    commit_hash=commit_hash,
                    prompt=prompt,
                    response=response,
                    agent_plan=None,
                    by_user=by_user,
                    files=[old_rel_path, new_rel_path],
                )

            LOGGER.info(
                f"Renamed file in memov repo from {old_file_path} to {new_file_path} and committed."
            )
        except Exception as e:
            LOGGER.error(f"Error renaming file in memov repo: {e}")

    def remove(
        self,
        file_path: str,
        prompt: Optional[str] = None,
        response: Optional[str] = None,
        by_user: bool = False,
    ) -> None:
        """Remove a tracked file from the memov repo, and generate a commit to record the operation."""
        try:
            target_abs_path = os.path.abspath(file_path)
            target_rel_path = os.path.relpath(target_abs_path, self.project_path)

            # Check if the file is tracked on the current branch
            head_commit = GitManager.get_commit_id_by_ref(
                self.bare_repo_path, "refs/memov/HEAD", verbose=False
            )
            tracked_files = []
            if head_commit:
                tracked_files, _ = GitManager.get_files_by_commit(self.bare_repo_path, head_commit)

            if target_rel_path not in tracked_files:
                logging.warning(
                    f"{Color.RED}File {file_path} is not tracked, nothing to remove.{Color.RESET}"
                )
                return

            # If the file exists, remove it from the working directory
            if os.path.exists(target_abs_path):
                if (
                    input(f"Are you sure you want to remove {target_abs_path}? (y/N): ")
                    .strip()
                    .lower()
                    != "y"
                ):
                    LOGGER.info("File removal cancelled by user.")
                    return
                os.remove(target_abs_path)
                commit_msg = "Remove file\n\n"
            else:
                commit_msg = "Remove file (already missing)\n\n"

            commit_msg += f"Files: {target_rel_path}\n"
            commit_msg += (
                f"Prompt: {prompt}\nResponse: {response}\nSource: {'User' if by_user else 'AI'}"
            )

            # Commit the removal in the memov repo
            # Get current tracked files and exclude the removed file
            tracked_file_rel_paths, tracked_file_abs_paths = [], []
            if head_commit:
                tracked_file_rel_paths, tracked_file_abs_paths = GitManager.get_files_by_commit(
                    self.bare_repo_path, head_commit
                )

            # Build file list excluding the removed file
            file_list = {}
            for rel_path, abs_path in zip(tracked_file_rel_paths, tracked_file_abs_paths):
                if rel_path != target_rel_path and os.path.exists(abs_path):
                    file_list[rel_path] = abs_path

            commit_hash = self._commit(commit_msg, file_list)

            # Add to pending writes (will be synced later via mem sync)
            if commit_hash:
                self._add_to_pending_writes(
                    operation_type="remove",
                    commit_hash=commit_hash,
                    prompt=prompt,
                    response=response,
                    agent_plan=None,
                    by_user=by_user,
                    files=[target_rel_path],
                )

            LOGGER.info(
                f"Removed file from working directory: {target_abs_path} and committed in memov repo."
            )
        except Exception as e:
            LOGGER.error(f"Error removing file from memov repo: {e}")

    def history(self) -> None:
        """Show the history of all branches in the memov bare repo, with table header and wider prompt/resp columns."""
        try:
            # Load branches from the memov repo
            branches = self._load_branches()
            if branches is None:
                LOGGER.error(
                    "No branches found in the memov repo. Please initialize or track files first."
                )
                return

            # Get the head commit of the memov repo and the branches' commit hashes
            head_commit = GitManager.get_commit_id_by_ref(
                self.bare_repo_path, "refs/memov/HEAD", verbose=False
            )
            commit_to_branch = defaultdict(list)
            for name, commit_hash in branches["branches"].items():
                commit_to_branch[commit_hash].append(name)

            # Print the header with new format including Operation column
            logging.info(
                f"{'Operation'.ljust(10)} {'Branch'.ljust(20)} {'Commit'.ljust(8)} {'Prompt'.ljust(15)} {'Resp'.ljust(15)} {'Plan'.ljust(15)}"
            )
            logging.info("-" * 85)

            # Get commit history for each branch and print the details
            seen = set()
            for commit_hash in branches["branches"].values():
                commit_history = GitManager.get_commit_history(self.bare_repo_path, commit_hash)

                for hash_id in commit_history:
                    if hash_id in seen:
                        continue
                    seen.add(hash_id)

                    # Get the commit message and extract operation type
                    message = GitManager.get_commit_message(self.bare_repo_path, hash_id)
                    operation_type = self._extract_operation_type(message)

                    # Get prompt, response, agent_plan from commit message first
                    prompt = response = agent_plan = ""
                    for line in message.splitlines():
                        if line.startswith("Prompt:"):
                            prompt = line[len("Prompt:") :].strip()
                        elif line.startswith("Response:"):
                            response = line[len("Response:") :].strip()
                        elif line.startswith("Agent Plan:"):
                            agent_plan = line[len("Agent Plan:") :].strip()

                    # Check if there's a git note for this commit (priority over commit message)
                    note_content = GitManager.get_commit_note(self.bare_repo_path, hash_id)
                    if note_content:
                        # Parse the note content for updated prompt/response/agent_plan
                        for line in note_content.splitlines():
                            if line.startswith("Prompt:"):
                                prompt = line[len("Prompt:") :].strip()
                            elif line.startswith("Response:"):
                                response = line[len("Response:") :].strip()
                            elif line.startswith("Agent Plan:"):
                                agent_plan = line[len("Agent Plan:") :].strip()

                    # Get the branch marker and format the output
                    marker = "*" if hash_id == head_commit else " "
                    branch_names = ",".join(commit_to_branch.get(hash_id, []))
                    branch_str = f"[{branch_names}]" if branch_names else ""
                    hash7 = hash_id[:7]

                    # Format prompt, response, agent_plan, handle None values
                    prompt_display = short_msg(prompt) if prompt and prompt != "None" else "None"
                    response_display = (
                        short_msg(response) if response and response != "None" else "None"
                    )
                    plan_display = (
                        short_msg(agent_plan) if agent_plan and agent_plan != "None" else "None"
                    )

                    logging.info(
                        f"{operation_type.ljust(10)} {marker} {branch_str.ljust(18)} {hash7.ljust(8)} {prompt_display.ljust(15)} {response_display.ljust(15)} {plan_display.ljust(15)}"
                    )
        except Exception as e:
            LOGGER.error(f"Error showing history in memov repo: {e}")

    def get_history(self, limit: int = 20, include_diff: bool = True) -> list[dict]:
        """Get the history of all branches in the memov bare repo as structured data.

        Args:
            limit: Maximum number of commits to return (default: 20)
            include_diff: Whether to include diff/hunk information for each commit (default: True)

        Returns:
            List of commit dictionaries with keys:
                - commit_hash: Full commit hash
                - short_hash: 7-char short hash
                - operation: Operation type (track, snap, rename, etc.)
                - branch: Branch name(s) if commit is a branch tip
                - is_head: Whether this commit is the current HEAD
                - prompt: User prompt
                - response: AI response
                - agent_plan: Agent plan (if available)
                - files: List of files in the commit
                - timestamp: Commit timestamp (ISO format)
                - author: Commit author
                - diff: Dict mapping file paths to their diff/hunk content (if include_diff=True)
        """
        result = []
        try:
            # Load branches from the memov repo
            branches = self._load_branches()
            if branches is None:
                LOGGER.warning("No branches found in the memov repo.")
                return []

            # Get the head commit
            head_commit = GitManager.get_commit_id_by_ref(
                self.bare_repo_path, "refs/memov/HEAD", verbose=False
            )
            commit_to_branch = defaultdict(list)
            for name, commit_hash in branches["branches"].items():
                commit_to_branch[commit_hash].append(name)

            # Get commit history for each branch
            seen = set()
            all_commits = []
            for commit_hash in branches["branches"].values():
                commit_history = GitManager.get_commit_history(self.bare_repo_path, commit_hash)
                for hash_id in commit_history:
                    if hash_id not in seen:
                        seen.add(hash_id)
                        all_commits.append(hash_id)

            # Process commits (most recent first, limited)
            all_commits = all_commits[-limit:] if len(all_commits) > limit else all_commits

            for hash_id in all_commits:
                # Get the commit message
                message = GitManager.get_commit_message(self.bare_repo_path, hash_id)
                operation_type = self._extract_operation_type(message)

                # Parse prompt, response, agent_plan from commit message
                prompt = response = agent_plan = ""
                for line in message.splitlines():
                    if line.startswith("Prompt:"):
                        prompt = line[len("Prompt:") :].strip()
                    elif line.startswith("Response:"):
                        response = line[len("Response:") :].strip()
                    elif line.startswith("Agent Plan:"):
                        agent_plan = line[len("Agent Plan:") :].strip()

                # Check if there's a git note for this commit (priority over commit message)
                note_content = GitManager.get_commit_note(self.bare_repo_path, hash_id)
                if note_content:
                    for line in note_content.splitlines():
                        if line.startswith("Prompt:"):
                            prompt = line[len("Prompt:") :].strip()
                        elif line.startswith("Response:"):
                            response = line[len("Response:") :].strip()
                        elif line.startswith("Agent Plan:"):
                            agent_plan = line[len("Agent Plan:") :].strip()

                # Get files in this commit
                file_rel_paths, _ = GitManager.get_files_by_commit(self.bare_repo_path, hash_id)

                # Get commit details (timestamp, author) using git log
                commit_info = self._get_commit_info(hash_id)

                # Get diff/hunk information if requested
                diff_data = {}
                if include_diff:
                    diff_data = self._get_commit_diff_by_file(hash_id)

                # Build result entry
                branch_names = commit_to_branch.get(hash_id, [])
                entry = {
                    "commit_hash": hash_id,
                    "short_hash": hash_id[:7],
                    "operation": operation_type,
                    "branch": ",".join(branch_names) if branch_names else None,
                    "is_head": hash_id == head_commit,
                    "prompt": prompt if prompt and prompt != "None" else None,
                    "response": response if response and response != "None" else None,
                    "agent_plan": agent_plan if agent_plan and agent_plan != "None" else None,
                    "files": file_rel_paths,
                    "timestamp": commit_info.get("timestamp"),
                    "author": commit_info.get("author"),
                }
                if include_diff:
                    entry["diff"] = diff_data
                result.append(entry)

        except Exception as e:
            LOGGER.error(f"Error getting history from memov repo: {e}")

        return result

    def _get_commit_info(self, commit_hash: str) -> dict:
        """Get commit info (timestamp, author) for a specific commit."""
        from memov.core.git import subprocess_call

        command = [
            "git",
            f"--git-dir={self.bare_repo_path}",
            "log",
            "-1",
            "--format=%aI|%an",
            commit_hash,
        ]
        success, output = subprocess_call(command=command)

        if success and output.stdout:
            parts = output.stdout.strip().split("|")
            if len(parts) == 2:
                return {"timestamp": parts[0], "author": parts[1]}

        return {"timestamp": None, "author": None}

    def _get_commit_diff_by_file(self, commit_hash: str) -> dict[str, dict]:
        """Get structured diff content for a specific commit, grouped by file.

        Args:
            commit_hash: The commit hash to get diff for.

        Returns:
            Dictionary mapping file paths to structured diff data.
            Example: {
                "1.txt": {
                    "status": "modified",  # "added", "modified", "deleted"
                    "hunks": [
                        {
                            "header": "@@ -0,0 +1 @@",
                            "old_start": 0,
                            "old_count": 0,
                            "new_start": 1,
                            "new_count": 1,
                            "lines": [
                                {"type": "add", "content": "hello!!!!"}
                            ]
                        }
                    ]
                }
            }
        """
        import re

        from memov.core.git import subprocess_call

        try:
            # Resolve the full commit hash
            full_hash = GitManager.get_commit_id_by_ref(
                self.bare_repo_path, commit_hash, verbose=False
            )
            if not full_hash:
                LOGGER.error(f"Commit '{commit_hash}' not found.")
                return {}

            # Get the parent commit (if exists)
            command = [
                "git",
                f"--git-dir={self.bare_repo_path}",
                "rev-parse",
                f"{full_hash}^",
            ]
            success, output = subprocess_call(command=command)

            diffs_by_file: dict[str, dict] = {}

            if success and output.stdout.strip():
                # Has parent - get diff between parent and this commit
                parent_hash = output.stdout.strip()
                diff_command = [
                    "git",
                    f"--git-dir={self.bare_repo_path}",
                    "diff",
                    parent_hash,
                    full_hash,
                ]
                success, diff_output = subprocess_call(command=diff_command)
                if success and diff_output.stdout:
                    # Parse the diff output and group by file
                    diffs_by_file = self._parse_diff_by_file(diff_output.stdout)
            else:
                # No parent (first commit) - show all files as added
                file_rel_paths, _ = GitManager.get_files_by_commit(self.bare_repo_path, full_hash)
                for rel_path in file_rel_paths:
                    # Get file content from the commit
                    show_command = [
                        "git",
                        f"--git-dir={self.bare_repo_path}",
                        "show",
                        f"{full_hash}:{rel_path}",
                    ]
                    success, content_output = subprocess_call(command=show_command)
                    if success:
                        lines = content_output.stdout.splitlines()
                        line_count = len(lines)
                        diffs_by_file[rel_path] = {
                            "status": "added",
                            "hunks": [
                                {
                                    "header": f"@@ -0,0 +1,{line_count} @@",
                                    "old_start": 0,
                                    "old_count": 0,
                                    "new_start": 1,
                                    "new_count": line_count,
                                    "lines": [{"type": "add", "content": line} for line in lines],
                                }
                            ],
                        }

            return diffs_by_file

        except Exception as e:
            LOGGER.error(f"Error getting diff for commit {commit_hash}: {e}")
            return {}

    def _parse_diff_by_file(self, diff_output: str) -> dict[str, dict]:
        """Parse unified diff output and return structured data grouped by file.

        Args:
            diff_output: Raw git diff output string.

        Returns:
            Dictionary mapping file paths to structured diff data with hunks.
        """
        import re

        diffs_by_file: dict[str, dict] = {}
        current_file = None
        current_status = "modified"
        current_hunks: list[dict] = []
        current_hunk: Optional[dict] = None

        # Regex to parse hunk header: @@ -old_start,old_count +new_start,new_count @@
        hunk_pattern = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

        for line in diff_output.splitlines():
            # Detect start of a new file diff
            if line.startswith("diff --git"):
                # Save previous file's data if exists
                if current_file:
                    if current_hunk:
                        current_hunks.append(current_hunk)
                    diffs_by_file[current_file] = {
                        "status": current_status,
                        "hunks": current_hunks,
                    }

                # Extract file path from "diff --git a/path b/path"
                parts = line.split(" ")
                if len(parts) >= 4:
                    b_path = parts[-1]
                    if b_path.startswith("b/"):
                        current_file = b_path[2:]
                    else:
                        current_file = b_path
                else:
                    current_file = None

                current_status = "modified"
                current_hunks = []
                current_hunk = None

            elif line.startswith("new file mode"):
                current_status = "added"
            elif line.startswith("deleted file mode"):
                current_status = "deleted"
            elif line.startswith("@@"):
                # Save previous hunk if exists
                if current_hunk:
                    current_hunks.append(current_hunk)

                # Parse hunk header
                match = hunk_pattern.match(line)
                if match:
                    old_start = int(match.group(1))
                    old_count = int(match.group(2)) if match.group(2) else 1
                    new_start = int(match.group(3))
                    new_count = int(match.group(4)) if match.group(4) else 1
                    current_hunk = {
                        "header": line,
                        "old_start": old_start,
                        "old_count": old_count,
                        "new_start": new_start,
                        "new_count": new_count,
                        "lines": [],
                    }
                else:
                    current_hunk = {
                        "header": line,
                        "old_start": 0,
                        "old_count": 0,
                        "new_start": 0,
                        "new_count": 0,
                        "lines": [],
                    }
            elif current_hunk is not None:
                # Parse diff lines
                if line.startswith("+"):
                    current_hunk["lines"].append({"type": "add", "content": line[1:]})
                elif line.startswith("-"):
                    current_hunk["lines"].append({"type": "delete", "content": line[1:]})
                elif line.startswith(" "):
                    current_hunk["lines"].append({"type": "context", "content": line[1:]})
                elif line.startswith("\\"):
                    # "\ No newline at end of file"
                    current_hunk["lines"].append({"type": "info", "content": line})

        # Don't forget the last file
        if current_file:
            if current_hunk:
                current_hunks.append(current_hunk)
            diffs_by_file[current_file] = {
                "status": current_status,
                "hunks": current_hunks,
            }

        return diffs_by_file

    def jump(self, commit_hash: str) -> tuple[MemStatus, str]:
        """Jump to a specific snapshot and auto-create a new branch.

        Args:
            commit_hash: The commit hash to jump to (full or short form)

        Returns:
            Tuple of (MemStatus, branch_name) - branch_name is the auto-created branch
        """
        try:
            # Validate commit hash exists
            full_hash = GitManager.get_commit_id_by_ref(
                self.bare_repo_path, commit_hash, verbose=False
            )
            if not full_hash:
                LOGGER.error(f"Commit '{commit_hash}' not found.")
                return MemStatus.UNKNOWN_ERROR, ""

            # Get all files that have ever been tracked
            all_tracked_files = set()
            branches = self._load_branches()
            if branches is None or "branches" not in branches:
                LOGGER.error("No branches configuration found.")
                return MemStatus.UNKNOWN_ERROR, ""

            for branch_tip in branches["branches"].values():
                rev_list = GitManager.get_commit_history(self.bare_repo_path, branch_tip)
                for commit in rev_list:
                    _, file_abs_paths = GitManager.get_files_by_commit(self.bare_repo_path, commit)
                    # Normalize paths for cross-platform compatibility
                    all_tracked_files.update(
                        os.path.normpath(os.path.abspath(p)) for p in file_abs_paths
                    )

            # Verify archive can be created BEFORE deleting files
            archive = GitManager.git_archive(self.bare_repo_path, full_hash)
            if archive is None:
                LOGGER.error(f"Failed to create archive for commit {commit_hash}.")
                return MemStatus.UNKNOWN_ERROR, ""

            # Now safe to remove files that are not in the snapshot
            # Use absolute paths for comparison (normalize for cross-platform compatibility)
            _, snapshot_abs_files = GitManager.get_files_by_commit(self.bare_repo_path, full_hash)
            snapshot_abs_set = set(os.path.normpath(os.path.abspath(p)) for p in snapshot_abs_files)
            for file_path in all_tracked_files:
                normalized_path = os.path.normpath(os.path.abspath(file_path))
                if normalized_path not in snapshot_abs_set and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError as e:
                        LOGGER.warning(f"Failed to delete {file_path}: {e}")

            # Extract the snapshot content to the workspace
            try:
                with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
                    tar.extractall(self.project_path)
            except (tarfile.TarError, OSError, PermissionError) as e:
                LOGGER.error(f"Failed to extract archive to {self.project_path}: {e}")
                return MemStatus.UNKNOWN_ERROR, ""

            # Auto-create a new branch at this commit
            # Record where we jumped from (the previous HEAD)
            previous_branch = branches.get("current", "main")
            previous_head = branches["branches"].get(previous_branch)

            new_branch = self._generate_jump_branch_name(branches)
            branches["branches"][new_branch] = full_hash
            branches["current"] = new_branch

            # Record jump metadata: from which commit we jumped
            if "jump_from" not in branches:
                branches["jump_from"] = {}
            if previous_head and previous_head != full_hash:
                branches["jump_from"][new_branch] = {
                    "from_commit": previous_head,
                    "to_commit": full_hash,
                    "from_branch": previous_branch,
                }

            self._save_branches(branches)
            GitManager.update_ref(self.bare_repo_path, "refs/memov/HEAD", full_hash)

            # Record jump in exploration history (jump.json)
            if previous_head and previous_head != full_hash:
                self._record_jump(
                    from_commit=previous_head,
                    to_commit=full_hash,
                    from_branch=previous_branch,
                    new_branch=new_branch,
                )

            LOGGER.info(f"Jumped to commit {full_hash[:7]} and created branch '{new_branch}'.")
            return MemStatus.SUCCESS, new_branch
        except Exception as e:
            LOGGER.error(f"Error jumping to commit in memov repo: {e}", exc_info=True)
            return MemStatus.UNKNOWN_ERROR, ""

    def _generate_jump_branch_name(self, branches: dict) -> str:
        """Generate a unique branch name for jump operation."""
        if not isinstance(branches, dict) or "branches" not in branches:
            return "jump/1"

        i = 1
        while f"jump/{i}" in branches["branches"]:
            i += 1
        return f"jump/{i}"

    def show(self, commit_id: str) -> None:
        """Show details of a specific snapshot in the memov bare repo, similar to git show."""
        try:
            GitManager.git_show(self.bare_repo_path, commit_id)

            tracked_file_rel_paths, _ = GitManager.get_files_by_commit(
                self.bare_repo_path, commit_id
            )
            LOGGER.info(f"\nTracked files in snapshot {commit_id}:")
            for rel_path in tracked_file_rel_paths:
                LOGGER.info(f"  {rel_path}")

        except Exception as e:
            LOGGER.error(f"Error showing snapshot {commit_id} in bare repo: {e}")

    def get_diff(self, commit_hash: str) -> dict[str, str]:
        """Get diff content for a specific commit.

        Args:
            commit_hash: The commit hash to get diff for.

        Returns:
            Dictionary mapping file paths to their diff content.
        """
        try:
            from memov.core.git import subprocess_call

            # Resolve the full commit hash
            full_hash = GitManager.get_commit_id_by_ref(
                self.bare_repo_path, commit_hash, verbose=False
            )
            if not full_hash:
                LOGGER.error(f"Commit '{commit_hash}' not found.")
                return {}

            # Get the parent commit (if exists)
            command = [
                "git",
                f"--git-dir={self.bare_repo_path}",
                "rev-parse",
                f"{full_hash}^",
            ]
            success, output = subprocess_call(command=command)

            diffs = {}

            if success and output.stdout.strip():
                # Has parent - get diff between parent and this commit
                parent_hash = output.stdout.strip()
                diff_command = [
                    "git",
                    f"--git-dir={self.bare_repo_path}",
                    "diff",
                    parent_hash,
                    full_hash,
                ]
                success, diff_output = subprocess_call(command=diff_command)
                if success:
                    diffs["_all"] = diff_output.stdout
            else:
                # No parent (first commit) - show all files as added
                file_rel_paths, _ = GitManager.get_files_by_commit(self.bare_repo_path, full_hash)
                for rel_path in file_rel_paths:
                    # Get file content from the commit
                    show_command = [
                        "git",
                        f"--git-dir={self.bare_repo_path}",
                        "show",
                        f"{full_hash}:{rel_path}",
                    ]
                    success, content_output = subprocess_call(command=show_command)
                    if success:
                        # Format as diff-like output
                        lines = content_output.stdout.splitlines()
                        diff_lines = [f"+{line}" for line in lines]
                        diffs[rel_path] = "\n".join(diff_lines)

            return diffs

        except Exception as e:
            LOGGER.error(f"Error getting diff for commit {commit_hash}: {e}")
            return {}

    def status(self) -> tuple[MemStatus, dict[str, list[Path]]]:
        """Show status of working directory compared to HEAD snapshot, and display current HEAD commit and branch."""
        try:
            # Get the current HEAD commit and branch
            head_commit = GitManager.get_commit_id_by_ref(
                self.bare_repo_path, "refs/memov/HEAD", verbose=False
            )
            if head_commit is None:
                head_commit = GitManager.get_commit_id_by_ref(
                    self.bare_repo_path, "main", verbose=False
                )

            branches = self._load_branches()
            current_branch = branches.get("current") if branches else None

            LOGGER.info(f"Current HEAD commit: {head_commit}")
            LOGGER.info(f"Current branch: {current_branch}")

            # Get the tracked files and worktree files
            tracked_files_and_blobs = GitManager.get_files_and_blobs_by_commit(
                self.bare_repo_path, head_commit, self.project_path
            )
            # Exclude files based on .memignore, but tracked files will still be shown if they exist
            workspace_files = self._filter_new_files(
                [self.project_path], tracked_file_rel_paths=None, exclude_memignore=True
            )
            worktree_files_and_blobs = {}
            for rel_path, abs_path in workspace_files:
                blob_hash = GitManager.write_blob(self.bare_repo_path, abs_path)
                worktree_files_and_blobs[Path(abs_path).resolve()] = blob_hash

            # Compare tracked files with workspace files
            all_files: set[Path] = set(
                list(tracked_files_and_blobs.keys()) + list(worktree_files_and_blobs.keys())
            )

            untracked_files = []
            deleted_files = []
            modified_files = []
            for f in sorted(all_files):
                if f not in tracked_files_and_blobs:
                    untracked_files.append(f)
                    LOGGER.info(f"{Color.RED}Untracked: {f}{Color.RESET}")
                elif f not in worktree_files_and_blobs:
                    deleted_files.append(f)
                    LOGGER.info(f"{Color.RED}Deleted:   {f}{Color.RESET}")
                elif tracked_files_and_blobs[f] != worktree_files_and_blobs[f]:
                    modified_files.append(f)
                    LOGGER.info(f"{Color.RED}Modified:  {f}{Color.RESET}")
                else:
                    LOGGER.info(f"{Color.GREEN}Clean:     {f}{Color.RESET}")

            return MemStatus.SUCCESS, {
                "untracked": untracked_files,
                "deleted": deleted_files,
                "modified": modified_files,
            }

        except Exception as e:
            tb = traceback.extract_tb(e.__traceback__)
            filename, lineno, func, code = tb[-1]  # last frame
            LOGGER.error(f"Error showing status: {code}, {e}")
            return MemStatus.UNKNOWN_ERROR, {}

    def amend_commit_message(
        self,
        commit_hash: str,
        prompt: Optional[str] = None,
        response: Optional[str] = None,
        by_user: bool = False,
    ) -> None:
        """
        Attach prompt/response to the commit as a git note (does not rewrite history).
        """
        try:
            # Compose the note content
            note_lines = []
            if prompt is not None:
                note_lines.append(f"Prompt: {prompt}")
            if response is not None:
                note_lines.append(f"Response: {response}")
            note_lines.append(f"Source: {'User' if by_user else 'AI'}")
            if not (prompt or response):
                LOGGER.error("No prompt or response provided to amend.")
                return
            note_msg = "\n".join(note_lines)
            # Attach the note using GitManager
            success, error_msg = GitManager.amend_commit_message(
                self.bare_repo_path, commit_hash, note_msg
            )
            if success:
                LOGGER.info(f"Added note to commit {commit_hash}.")
            else:
                LOGGER.error(f"Failed to add note to commit {commit_hash}: {error_msg}")
        except Exception as e:
            LOGGER.error(f"Error adding note to commit: {e}")

    def _commit(self, commit_msg: str, file_paths: dict[str, str]) -> str:
        """Commit changes to the memov repo with the given commit message and file paths."""
        try:
            # Validate and fix branches before committing
            self._validate_and_fix_branches()

            # Check the git user config(name and email)
            GitManager.ensure_git_user_config(
                self.bare_repo_path, self.default_name, self.default_email
            )

            # Write blob to bare repo and get commit hash
            commit_hash = GitManager.write_blob_to_bare_repo(
                self.bare_repo_path, file_paths, commit_msg
            )

            # Update the branch metadata with the new commit
            self._update_branch(commit_hash)
            LOGGER.debug(f"Committed changes in memov repo: {commit_msg}")
            return commit_hash
        except Exception as e:
            LOGGER.error(f"Error committing changes in memov repo: {e}")
            return ""

    def _filter_new_files(
        self,
        file_paths: list[str],
        tracked_file_rel_paths: Optional[list[str]] = None,
        exclude_memignore: bool = True,
    ) -> list[tuple[str, str]]:
        """Filter out files that are already tracked or should be ignored.

        Args:
            file_paths (list[str]): The list of file paths to check.
            tracked_file_rel_paths (list[str] | None): The list of tracked file paths. If None, all files are considered new.
            exclude_memignore (bool): Whether to exclude files that match .memignore rules.
        """
        memignore_pspec = self._load_memignore()

        def filter(file_rel_path: str) -> bool:
            """Check if the file should be ignored"""

            # Filter out files that are already tracked if tracked_file_rel_paths is provided
            if tracked_file_rel_paths is not None and file_rel_path in tracked_file_rel_paths:
                return True

            # Never filter out .memignore itself based on .memignore rules
            # (but it can still be filtered if already tracked above)
            if file_rel_path == ".memignore":
                return False

            # Filter out files that match .memignore rules
            if exclude_memignore and memignore_pspec.match_file(file_rel_path):
                return True

            return False

        new_files = []
        for file_path in file_paths:
            abs_path = os.path.abspath(file_path)

            # Check if the file path is valid
            if not os.path.exists(abs_path):
                LOGGER.error(f"File {abs_path} does not exist.")
                continue

            # If the file is a directory, walk through it
            if os.path.isdir(abs_path):
                for root, dirs, files in os.walk(abs_path):
                    rel_root = os.path.relpath(root, self.project_path)

                    # Don't filter the current directory itself
                    if (
                        rel_root != "."
                        and exclude_memignore
                        and memignore_pspec.match_file(rel_root)
                    ):
                        continue

                    if ".mem" in dirs:
                        dirs.remove(".mem")
                    if ".git" in dirs:
                        dirs.remove(".git")

                    for file in files:
                        rel_file = os.path.relpath(os.path.join(root, file), self.project_path)
                        if filter(rel_file):
                            continue

                        new_files.append((rel_file, os.path.join(root, file)))

            # If the file is a regular file, check if it should be tracked
            elif os.path.isfile(abs_path):
                rel_file = os.path.relpath(abs_path, self.project_path)
                if filter(rel_file):
                    continue

                new_files.append((rel_file, abs_path))

            # If the path is neither a file nor a directory, log an error
            else:
                LOGGER.error(f"Path {abs_path} is neither a file nor a directory.")
                return []

        return new_files

    def _load_branches(self) -> Optional[dict]:
        """Load branches configuration from the branches config file."""
        if not os.path.exists(self.branches_config_path):
            return None

        with open(self.branches_config_path, "r") as f:
            return json.load(f)

    def _save_branches(self, data) -> None:
        """Save branches configuration to the branches config file."""
        with open(self.branches_config_path, "w") as f:
            json.dump(data, f, indent=2)

    def _load_jump_history(self) -> dict:
        """Load exploration history from jump.json."""
        jump_file = Path(self.mem_root_path) / "jump.json"
        if not jump_file.exists():
            return {"history": []}
        try:
            with open(jump_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"history": []}

    def _save_jump_history(self, data: dict) -> None:
        """Save exploration history to jump.json."""
        jump_file = Path(self.mem_root_path) / "jump.json"
        with open(jump_file, "w") as f:
            json.dump(data, f, indent=2)

    def _record_jump(
        self, from_commit: str, to_commit: str, from_branch: str, new_branch: str
    ) -> None:
        """Record a jump action in exploration history."""
        data = self._load_jump_history()
        next_id = max([h["id"] for h in data["history"]], default=0) + 1
        data["history"].append(
            {
                "id": next_id,
                "timestamp": datetime.now().isoformat(),
                "action": "jump",
                "from_commit": from_commit,
                "to_commit": to_commit,
                "from_branch": from_branch,
                "new_branch": new_branch,
            }
        )
        self._save_jump_history(data)

    def _next_develop_branch(self, branches: dict[str, str]) -> str:
        """Find the next available develop branch name based on existing branches."""
        i = 0
        while f"develop/{i}" in branches:
            i += 1
        return f"develop/{i}"

    def list_branches(self) -> MemStatus:
        """List all branches, marking current with *."""
        branches = self._load_branches()
        if not branches:
            LOGGER.warning("No branches found. Run 'mem init' first.")
            return MemStatus.BARE_REPO_NOT_FOUND

        current = branches.get("current")
        for name, commit in branches["branches"].items():
            prefix = "* " if name == current else "  "
            LOGGER.info(f"{prefix}{name} -> {commit[:7]}")
        return MemStatus.SUCCESS

    def create_branch(self, name: str) -> MemStatus:
        """Create a new branch at current HEAD."""
        branches = self._load_branches()
        if not branches:
            LOGGER.warning("No branches config found. Run 'mem init' first.")
            return MemStatus.BARE_REPO_NOT_FOUND

        if name in branches["branches"]:
            LOGGER.warning(f"Branch '{name}' already exists.")
            return MemStatus.UNKNOWN_ERROR

        head_commit = GitManager.get_commit_id_by_ref(
            self.bare_repo_path, "refs/memov/HEAD", verbose=False
        )
        if not head_commit:
            LOGGER.error("No HEAD commit found.")
            return MemStatus.UNKNOWN_ERROR

        branches["branches"][name] = head_commit
        self._save_branches(branches)
        LOGGER.info(f"Created branch '{name}' at {head_commit[:7]}")
        return MemStatus.SUCCESS

    def delete_branch(self, name: str) -> MemStatus:
        """Delete a branch."""
        branches = self._load_branches()
        if not branches:
            LOGGER.warning("No branches config found. Run 'mem init' first.")
            return MemStatus.BARE_REPO_NOT_FOUND

        if name not in branches["branches"]:
            LOGGER.warning(f"Branch '{name}' does not exist.")
            return MemStatus.UNKNOWN_ERROR

        if name == branches.get("current"):
            LOGGER.error(f"Cannot delete current branch '{name}'.")
            return MemStatus.UNKNOWN_ERROR

        if name == "main":
            LOGGER.error("Cannot delete 'main' branch.")
            return MemStatus.UNKNOWN_ERROR

        del branches["branches"][name]
        self._save_branches(branches)
        LOGGER.info(f"Deleted branch '{name}'")
        return MemStatus.SUCCESS

    def switch_branch(self, name: str) -> MemStatus:
        """Switch to a branch (lightweight, no file changes). Creates branch if it doesn't exist."""
        branches = self._load_branches()
        if not branches:
            LOGGER.warning("No branches config found. Run 'mem init' first.")
            return MemStatus.BARE_REPO_NOT_FOUND

        # If branch doesn't exist, create it at current HEAD
        created_new = False
        if name not in branches["branches"]:
            head_commit = GitManager.get_commit_id_by_ref(
                self.bare_repo_path, "refs/memov/HEAD", verbose=False
            )
            if not head_commit:
                LOGGER.error("No HEAD commit found.")
                return MemStatus.UNKNOWN_ERROR
            branches["branches"][name] = head_commit
            created_new = True

        target_commit = branches["branches"][name]
        branches["current"] = name
        self._save_branches(branches)
        GitManager.update_ref(self.bare_repo_path, "refs/memov/HEAD", target_commit)

        # Log after save succeeds to avoid inconsistency
        if created_new:
            LOGGER.info(f"Created and switched to branch '{name}' at {target_commit[:7]}")
        else:
            LOGGER.info(f"Switched to branch '{name}'")
        return MemStatus.SUCCESS

    def _load_memignore(self) -> pathspec.PathSpec:
        """Load .memignore rules and return a pathspec.PathSpec object"""
        patterns = []
        if os.path.exists(self.memignore_path):
            with open(self.memignore_path, "r") as f:
                patterns = [
                    line.strip() for line in f if line.strip() and not line.strip().startswith("#")
                ]
        # Exclude .mem and .git directories by default
        patterns.append(".mem/")
        patterns.append(".git/")
        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)

    def _validate_and_fix_branches(self) -> None:
        """Validate and fix abnormal states in branches.json"""
        branches = self._load_branches()
        if not branches:
            return

        head_commit = GitManager.get_commit_id_by_ref(
            self.bare_repo_path, "refs/memov/HEAD", verbose=False
        )

        fixed = False

        # Fix empty branch commit hashes
        for name, commit_hash in branches["branches"].items():
            if not commit_hash:  # Empty string or None
                if name == "main" and head_commit:
                    branches["branches"][name] = head_commit
                    LOGGER.info(f"Fixed empty {name} branch with current HEAD {head_commit}")
                    fixed = True

        # Ensure current points to a valid branch
        current = branches.get("current")
        if current and current not in branches["branches"]:
            branches["current"] = "main"  # Default back to main
            LOGGER.warning(f"Fixed invalid current branch, reset to main")
            fixed = True

        if fixed:
            self._save_branches(branches)

    def _update_branch(self, new_commit: str, reset_current_branch: bool = False) -> None:
        """Automatically create or update a branch in the memov repo based on the new commit."""
        branches = self._load_branches()

        # First commit to create the default branch if it doesn't exist
        if branches is None:
            branches = {"current": "main", "branches": {"main": new_commit}}
            self._save_branches(branches)
            GitManager.update_ref(self.bare_repo_path, "refs/memov/HEAD", new_commit)
            return

        # If reset_current_branch is True, save current branch and reset
        if reset_current_branch:
            current_branch = branches.get("current")
            if current_branch and current_branch in branches["branches"]:
                head_commit = GitManager.get_commit_id_by_ref(
                    self.bare_repo_path, "refs/memov/HEAD", verbose=False
                )
                if head_commit:
                    branches["branches"][current_branch] = head_commit
            branches["current"] = None
        else:
            head_commit = GitManager.get_commit_id_by_ref(
                self.bare_repo_path, "refs/memov/HEAD", verbose=False
            )

            # Prioritize using current branch
            current_branch = branches.get("current")
            if current_branch and current_branch in branches["branches"]:
                # If current branch exists, update it directly
                branches["branches"][current_branch] = new_commit
                LOGGER.debug(f"Updated current branch {current_branch} to {new_commit}")
            else:
                # No current branch - this should not happen if snapshot() checks for detached state
                # Just log a warning and don't create automatic branches
                LOGGER.warning(
                    f"No current branch set. Commit {new_commit} created but not associated with any branch."
                )

        # Update the branches config file and the HEAD reference
        self._save_branches(branches)
        GitManager.update_ref(self.bare_repo_path, "refs/memov/HEAD", new_commit)

    def _extract_operation_type(self, commit_message: str) -> str:
        """Extract operation type from commit message first line."""
        if not commit_message:
            return "unknown"

        first_line = commit_message.splitlines()[0].lower()

        if "track" in first_line:
            return "track"
        elif "snapshot" in first_line or "snap" in first_line:
            return "snap"
        elif "rename" in first_line:
            return "rename"
        elif "remove" in first_line:
            return "remove"
        else:
            return "unknown"

    def _load_pending_writes(self) -> list[dict]:
        """Load pending writes from disk if exists."""
        if not os.path.exists(self.pending_writes_path):
            return []

        try:
            with open(self.pending_writes_path, "r", encoding="utf-8") as f:
                pending_writes = json.load(f)
                LOGGER.debug(f"Loaded {len(pending_writes)} pending writes from disk")
                return pending_writes
        except Exception as e:
            LOGGER.warning(f"Failed to load pending writes: {e}")
            return []

    def _save_pending_writes(self) -> None:
        """Save pending writes to disk for persistence across CLI invocations."""
        try:
            # Create .mem directory if it doesn't exist
            os.makedirs(self.mem_root_path, exist_ok=True)

            with open(self.pending_writes_path, "w", encoding="utf-8") as f:
                json.dump(self._pending_writes, f, indent=2, ensure_ascii=False)
                LOGGER.debug(f"Saved {len(self._pending_writes)} pending writes to disk")
        except Exception as e:
            LOGGER.warning(f"Failed to save pending writes: {e}")

    def _add_to_pending_writes(
        self,
        operation_type: str,
        commit_hash: str,
        prompt: Optional[str],
        response: Optional[str],
        agent_plan: Optional[str],
        by_user: bool,
        files: list[str],
    ) -> None:
        """
        Add operation data to pending writes cache (in-memory).

        This method does NOT write to VectorDB immediately. Instead, it adds the data
        to a memory cache. Use sync_to_vectordb() to batch write all pending operations.

        Args:
            operation_type: Type of operation (track, snap, rename, remove)
            commit_hash: Git commit hash
            prompt: User prompt
            response: AI response
            agent_plan: Agent plan (high-level summary of changes)
            by_user: Whether operation was initiated by user
            files: List of affected file paths
        """
        try:
            # Get parent commit
            parent_hash = None
            head_commit = GitManager.get_commit_id_by_ref(
                self.bare_repo_path, "refs/memov/HEAD", verbose=False
            )
            if head_commit and head_commit != commit_hash:
                parent_hash = head_commit

            # Add to pending writes
            self._pending_writes.append(
                {
                    "operation_type": operation_type,
                    "commit_hash": commit_hash,
                    "prompt": prompt,
                    "response": response,
                    "agent_plan": agent_plan,
                    "by_user": by_user,
                    "files": files,
                    "parent_hash": parent_hash,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            LOGGER.debug(
                f"Added commit {commit_hash} to pending writes cache "
                f"(total pending: {len(self._pending_writes)})"
            )

            # Save to disk for persistence across CLI invocations
            self._save_pending_writes()

        except Exception as e:
            LOGGER.warning(f"Failed to add to pending writes: {e}")

    def sync_to_vectordb(self) -> tuple[int, int]:
        """
        Batch write all pending operations to VectorDB.

        This method processes all cached operations in _pending_writes and writes them
        to the VectorDB using the splitted embedding approach (prompt, response, agent_plan
        are stored as separate documents).

        Returns:
            Tuple of (successful_writes, failed_writes)
        """
        if not self._pending_writes:
            LOGGER.info("No pending writes to sync")
            return (0, 0)

        LOGGER.info(f"Syncing {len(self._pending_writes)} pending writes to VectorDB...")

        successful = 0
        failed = 0

        for write_data in self._pending_writes:
            try:
                # Prepare base metadata
                metadata = {
                    "operation_type": write_data["operation_type"],
                    "source": "user" if write_data["by_user"] else "ai",
                    "files": ", ".join(write_data["files"]),
                    "commit_hash": write_data["commit_hash"],
                    "parent_hash": write_data.get("parent_hash", ""),
                    "timestamp": write_data["timestamp"],
                }

                # Use splitted insertion for independent retrieval
                self.vectordb.insert_splitted(
                    commit_hash=write_data["commit_hash"],
                    prompt=write_data.get("prompt"),
                    response=write_data.get("response"),
                    agent_plan=write_data.get("agent_plan"),
                    metadata=metadata,
                )

                LOGGER.debug(f"Synced commit {write_data['commit_hash']} to VectorDB")
                successful += 1

            except Exception as e:
                LOGGER.warning(f"Failed to sync commit {write_data['commit_hash']}: {e}")
                failed += 1

        # Clear pending writes after sync
        self._pending_writes.clear()

        # Remove the persistent file since all writes are now synced
        if os.path.exists(self.pending_writes_path):
            try:
                os.remove(self.pending_writes_path)
                LOGGER.debug("Removed pending_writes.json after sync")
            except Exception as e:
                LOGGER.warning(f"Failed to remove pending_writes.json: {e}")

        LOGGER.info(f"Sync completed: {successful} successful, {failed} failed")
        return (successful, failed)

    def get_pending_writes_count(self) -> int:
        """Get the number of pending writes in the cache."""
        return len(self._pending_writes)

    def clear_pending_writes(self) -> None:
        """Clear all pending writes without syncing (data will be lost)."""
        count = len(self._pending_writes)
        self._pending_writes.clear()

        # Remove the persistent file
        if os.path.exists(self.pending_writes_path):
            try:
                os.remove(self.pending_writes_path)
                LOGGER.debug("Removed pending_writes.json after clear")
            except Exception as e:
                LOGGER.warning(f"Failed to remove pending_writes.json: {e}")

        LOGGER.warning(f"Cleared {count} pending writes without syncing")

    def find_similar_prompts(
        self, query_prompt: str, n_results: int = 5, operation_type: Optional[str] = None
    ) -> list[dict]:
        """
        Find prompts similar to the given query.

        Args:
            query_prompt: The prompt text to search for
            n_results: Number of results to return (default: 5)
            operation_type: Optional filter by operation type (track, snap, etc.)

        Returns:
            List of similar prompts with their commit information
        """
        try:
            return self.vectordb.find_similar_prompts(
                query_prompt=query_prompt,
                n_results=n_results,
                operation_type=operation_type,
            )
        except Exception as e:
            LOGGER.error(f"Error finding similar prompts: {e}")
            return []

    def find_commits_by_prompt(self, query_prompt: str, n_results: int = 5) -> list[str]:
        """
        Find commit IDs with prompts similar to the query.

        Args:
            query_prompt: The prompt text to search for
            n_results: Number of results to return

        Returns:
            List of commit hashes
        """
        try:
            results = self.find_similar_prompts(query_prompt, n_results)
            return [r["metadata"].get("commit_hash") for r in results if "metadata" in r]
        except Exception as e:
            LOGGER.error(f"Error finding commits by prompt: {e}")
            return []

    def find_commits_by_files(self, file_paths: list[str]) -> list[dict]:
        """
        Find commits that involve specific files.

        Args:
            file_paths: List of file paths to search for

        Returns:
            List of commits involving these files
        """
        try:
            return self.vectordb.find_commits_by_files(file_paths)
        except Exception as e:
            LOGGER.error(f"Error finding commits by files: {e}")
            return []

    def get_vectordb_info(self) -> dict:
        """
        Get information about the VectorDB collection.

        Returns:
            Dictionary with collection statistics
        """
        try:
            return self.vectordb.get_collection_info()
        except Exception as e:
            LOGGER.error(f"Error getting VectorDB info: {e}")
            return {}

    def report(self, format: str = "json") -> Optional[dict]:
        """
        Generate a report of the latest commit with all necessary information
        for external MCP snap operations.

        This method retrieves:
        - commit_hash: Latest commit hash
        - commit_message: Commit message (from Prompt field)
        - diff: Git diff output
        - branch: Current branch name
        - parent_commit: Parent commit hash (empty if no parent)

        Args:
            format: Output format, currently only "json" is supported

        Returns:
            Dictionary with commit information, or None if no commits exist
        """
        try:
            # Get the latest commit (HEAD)
            head_commit = GitManager.get_commit_id_by_ref(
                self.bare_repo_path, "refs/memov/HEAD", verbose=False
            )
            if not head_commit:
                LOGGER.warning("No commits found in memov repository")
                return None

            # Get branch information
            branches = self._load_branches()
            current_branch = branches.get("current", "") if branches else ""

            # Get commit message and extract prompt
            commit_message = GitManager.get_commit_message(self.bare_repo_path, head_commit)
            prompt = ""
            response = ""
            source = ""

            # Parse commit message
            for line in commit_message.splitlines():
                if line.startswith("Prompt:"):
                    prompt = line[len("Prompt:") :].strip()
                elif line.startswith("Response:"):
                    response = line[len("Response:") :].strip()
                elif line.startswith("Source:"):
                    source = line[len("Source:") :].strip()

            # Check for git notes (overrides commit message)
            note_content = GitManager.get_commit_note(self.bare_repo_path, head_commit)
            if note_content:
                for line in note_content.splitlines():
                    if line.startswith("Prompt:"):
                        prompt = line[len("Prompt:") :].strip()
                    elif line.startswith("Response:"):
                        response = line[len("Response:") :].strip()
                    elif line.startswith("Source:"):
                        source = line[len("Source:") :].strip()

            # Get parent commit (previous commit in history)
            # commit_history is sorted from oldest to newest due to --reverse flag
            # So head_commit is the last element, and its parent is the second-to-last
            parent_commit = ""
            commit_history = GitManager.get_commit_history(self.bare_repo_path, head_commit)
            if len(commit_history) > 1:
                parent_commit = commit_history[-2]  # Second-to-last commit is the parent

            # Get diff output using git show
            diff_output = GitManager.git_show(self.bare_repo_path, head_commit, return_output=True)

            # Get tracked files in this commit
            tracked_files, _ = GitManager.get_files_by_commit(self.bare_repo_path, head_commit)

            # Build report
            report_data = {
                "commit_hash": head_commit,
                "commit_message": prompt if prompt else commit_message.splitlines()[0],
                "diff": diff_output,
                "branch": current_branch,
                "parent_commit": parent_commit,
                "metadata": {
                    "prompt": prompt,
                    "response": response,
                    "source": source,
                    "files": tracked_files,
                    "full_commit_message": commit_message,
                },
            }

            return report_data

        except Exception as e:
            LOGGER.error(f"Error generating report: {e}")
            traceback.print_exc()
            return None
