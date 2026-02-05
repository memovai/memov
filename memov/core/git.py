import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from memov.utils.string_utils import clean_windows_git_lstree_output, split_path_parts

LOGGER = logging.getLogger(__name__)


def subprocess_call(
    command: list[str], input: str = None, text: bool = True
) -> tuple[bool, Optional[subprocess.CompletedProcess]]:
    """Run a subprocess command and handle errors."""
    try:
        # When using input parameter, don't set stdin (it will be auto-set to PIPE)
        # Only set stdin=DEVNULL when no input is provided
        kwargs = {
            "check": True,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": text,
        }

        # Only set encoding when text mode is True
        if text:
            kwargs["encoding"] = "utf-8"
            # Be resilient to non-UTF-8 diffs/binary output across platforms
            kwargs["errors"] = "replace"

        if input is not None:
            kwargs["input"] = input
        else:
            kwargs["stdin"] = subprocess.DEVNULL

        output = subprocess.run(command, **kwargs)
        return True, output
    except subprocess.CalledProcessError as e:
        LOGGER.debug(f"Command failed: {' '.join(command)}\nStdout: {e.stdout}\nStderr: {e.stderr}")
        # Return the exception object so callers can access stderr for better error messages
        return False, e


class GitManager:

    @staticmethod
    def create_bare_repo(repo_path: str) -> None:
        """Create a bare Git repository at the specified path."""
        if not os.path.exists(repo_path):
            LOGGER.info(f"Creating bare Git repository at {repo_path}")
            command = ["git", "init", "--bare", repo_path, "--initial-branch=main"]
            success, _ = subprocess_call(command=command)

            if success:
                LOGGER.info(f"Bare Git repository created at {repo_path}")
            else:
                LOGGER.error(f"Failed to create bare Git repository at {repo_path}")

        else:
            LOGGER.info(f"Bare Git repository already exists at {repo_path}")

    @staticmethod
    def get_commit_id_by_ref(repo_path: str, ref: str, verbose: bool = True) -> str:
        """Get the commit ID by reference from the repository."""
        command = ["git", f"--git-dir={repo_path}", "rev-parse", ref]
        success, output = subprocess_call(command=command)

        if success and output:
            return output.stdout.strip()
        else:
            if verbose:
                LOGGER.error(
                    f"Failed to get commit ID for reference {ref} in repository at {repo_path}"
                )
            else:
                LOGGER.debug(
                    f"Failed to get commit ID for reference {ref} in repository at {repo_path}"
                )
            return ""

    @staticmethod
    def get_tree_hash(repo_path: str, commit_id: str) -> str:
        """Get the tree hash for a specific commit."""
        command = ["git", f"--git-dir={repo_path}", "rev-parse", f"{commit_id}^{{tree}}"]
        success, output = subprocess_call(command=command)

        if success and output:
            return output.stdout.strip()
        else:
            LOGGER.error(
                f"Failed to get tree hash for commit {commit_id} in repository at {repo_path}"
            )
            return ""

    @staticmethod
    def get_files_by_commit(repo_path: str, commit_id: str) -> tuple[list[str], list[str]]:
        """Get the list of files in a specific commit."""
        command = ["git", f"--git-dir={repo_path}", "ls-tree", "-r", "--name-only", commit_id]
        success, output = subprocess_call(command=command)

        if success and output.stdout:
            file_rel_paths = []
            file_abs_paths = []
            # repo_path is .mem/memov.git, project root is two levels up
            project_root = Path(repo_path).parent.parent

            raw_stdout = output.stdout
            LOGGER.debug(f"get_files_by_commit raw stdout (repr): {repr(raw_stdout[:500])}")

            # Clean the entire output first to remove any stray control characters
            cleaned_stdout = raw_stdout.replace("\r", "").strip()
            LOGGER.debug(f"get_files_by_commit cleaned stdout (repr): {repr(cleaned_stdout[:500])}")

            for rel_file in cleaned_stdout.splitlines():
                rel_file = clean_windows_git_lstree_output(rel_file)
                # Skip empty lines
                if not rel_file:
                    continue
                # Build absolute path using os.path.join for proper Windows handling
                abs_file_path = str((project_root / rel_file).resolve())

                if len(file_rel_paths) < 3:
                    LOGGER.debug(
                        f"get_files_by_commit: rel_file={repr(rel_file)}, abs_file_path={repr(abs_file_path)}"
                    )

                file_rel_paths.append(rel_file)
                file_abs_paths.append(abs_file_path)

            return file_rel_paths, file_abs_paths

        else:
            LOGGER.error(f"Failed to get files for commit {commit_id} in repository at {repo_path}")
            return [], []

    # TODO: merge this with get_files_by_commit
    @staticmethod
    def get_files_and_blobs_by_commit(
        repo_path: str, commit_id: str, project_path: str = None
    ) -> dict[str, str]:
        """Get the list of files and their blob hashes in a specific commit.

        Args:
            repo_path (str): Path to the Git repository.
            commit_id (str): Commit ID to inspect.
            project_path (str): Path to the project directory (optional, for resolving relative paths correctly).
        """
        command = ["git", f"--git-dir={repo_path}", "ls-tree", "-r", commit_id]
        success, output = subprocess_call(command=command)

        if success and output.stdout:
            file_blobs = {}
            # Clean the entire output first to remove any stray control characters
            cleaned_stdout = output.stdout.replace("\r", "").strip()
            for line in cleaned_stdout.splitlines():
                # git ls-tree format: "<mode> <type> <hash>\t<filename>"
                # Split by tab first to handle filenames with spaces
                if "\t" in line:
                    meta, rel_file = line.split("\t", 1)
                    meta_parts = meta.split()
                    if len(meta_parts) == 3:
                        blob_hash = meta_parts[2]
                        rel_file = clean_windows_git_lstree_output(rel_file)
                        # Skip empty lines
                        if not rel_file:
                            continue
                        # If project_path is provided, resolve relative to it; otherwise use cwd
                        if project_path:
                            abs_path = (Path(project_path) / rel_file).resolve()
                        else:
                            abs_path = Path(rel_file).resolve()
                        file_blobs[abs_path] = blob_hash
                    else:
                        LOGGER.warning(f"Unexpected output format: {line}")
                else:
                    LOGGER.warning(f"Unexpected output format (no tab): {line}")

            return file_blobs
        else:
            LOGGER.error(
                f"Failed to get files and blobs for commit {commit_id} in repository at {repo_path}"
            )
            return {}

    @staticmethod
    def write_blob(repo_path: str, file_path: str) -> str:
        """Write a file as a blob in the Git repository."""
        command = ["git", f"--git-dir={repo_path}", "hash-object", "-w", file_path]
        success, output = subprocess_call(command=command)

        if success and output.stdout:
            return output.stdout.strip()
        else:
            LOGGER.error(f"Failed to write blob for file {file_path} in repository at {repo_path}")
            return ""

    @staticmethod
    def write_blobs(repo_path: str, file_paths: list[str]) -> dict[str, str]:
        """Write multiple files as blobs in the Git repository in a single batch operation.

        This is much more efficient than calling write_blob() for each file individually,
        as it uses a single git process with --stdin-paths.

        Args:
            repo_path: Path to the Git repository.
            file_paths: List of absolute file paths to write as blobs.

        Returns:
            Dictionary mapping file paths to their blob hashes.
            Files that failed to hash will not be included in the result.
        """
        if not file_paths:
            return {}

        LOGGER.debug(f"write_blobs called with {len(file_paths)} paths")
        for i, fp in enumerate(file_paths[:3]):
            LOGGER.debug(f"write_blobs file_paths[{i}] = {repr(fp)}")

        # Use --stdin-paths to batch process all files in one git call
        command = ["git", f"--git-dir={repo_path}", "hash-object", "-w", "--stdin-paths"]
        input_paths = "\n".join(file_paths)

        LOGGER.debug(f"write_blobs input_paths (repr, first 500): {repr(input_paths[:500])}")

        # Use binary mode to prevent Windows from converting \n to \r\n
        input_data = input_paths.encode("utf-8")
        success, output = subprocess_call(command=command, input=input_data, text=False)

        if success and output.stdout:
            hashes = output.stdout.decode("utf-8").strip().splitlines()
            if len(hashes) == len(file_paths):
                return dict(zip(file_paths, hashes))
            else:
                LOGGER.warning(
                    f"Hash count mismatch: expected {len(file_paths)}, got {len(hashes)}"
                )
                # Fall back to individual processing
                result = {}
                for file_path in file_paths:
                    blob_hash = GitManager.write_blob(repo_path, file_path)
                    if blob_hash:
                        result[file_path] = blob_hash
                return result
        else:
            LOGGER.error(f"Failed to batch write blobs in repository at {repo_path}")
            # Fall back to individual processing
            result = {}
            for file_path in file_paths:
                blob_hash = GitManager.write_blob(repo_path, file_path)
                if blob_hash:
                    result[file_path] = blob_hash
            return result

    @staticmethod
    def create_tree(repo_path: str, entries: list[str]) -> str:
        """Create a tree object in the Git repository."""
        command = ["git", f"--git-dir={repo_path}", "mktree"]
        # Use binary mode to prevent Windows from converting \n to \r\n
        input_data = "".join(entries).encode("utf-8")
        success, output = subprocess_call(command=command, input=input_data, text=False)

        if success and output.stdout:
            return output.stdout.decode("utf-8").strip()
        else:
            LOGGER.error(f"Failed to create tree in repository at {repo_path}")
            return ""

    @staticmethod
    def commit_tree(repo_path: str, tree_hash: str, commit_msg: str, parent_hash: str = "") -> str:
        """Commit a tree object in the Git repository."""
        # Use -F - to read commit message from stdin to support multiline messages
        command = ["git", f"--git-dir={repo_path}", "commit-tree", tree_hash, "-F", "-"]
        if parent_hash:
            command.extend(["-p", parent_hash])

        # Use binary mode to prevent Windows from converting \n to \r\n
        input_data = commit_msg.encode("utf-8")
        success, output = subprocess_call(command=command, input=input_data, text=False)

        if success and output.stdout:
            return output.stdout.decode("utf-8").strip()
        else:
            LOGGER.error(f"Failed to commit tree in repository at {repo_path}")
            return ""

    @staticmethod
    def write_blob_to_bare_repo(
        bare_repo: str, new_file_paths: dict[str, str], commit_msg: str
    ) -> str:
        """Write files as blobs in the bare Git repository and create a proper tree structure.

        This handles nested directories by creating a hierarchical tree structure.
        """
        if len(new_file_paths) == 0:
            return ""

        LOGGER.debug(f"write_blob_to_bare_repo called with {len(new_file_paths)} files")
        for i, (rel, abs_p) in enumerate(list(new_file_paths.items())[:3]):
            LOGGER.debug(
                f"write_blob_to_bare_repo new_file_paths[{i}]: rel={repr(rel)}, abs={repr(abs_p)}"
            )

        # Batch write all blobs in a single git call for better performance
        abs_paths = list(new_file_paths.values())
        path_to_blob = GitManager.write_blobs(bare_repo, abs_paths)

        # Build a directory tree structure
        # Format: {"dir1": {"dir2": {"file.txt": blob_hash}}}
        tree_structure = {}

        for rel_file, abs_path in new_file_paths.items():
            blob_hash = path_to_blob.get(abs_path)
            if not blob_hash:
                LOGGER.error(f"Failed to create blob for {rel_file}")
                return ""

            # Split path into parts (cross-platform compatible)
            parts = split_path_parts(rel_file)
            current = tree_structure

            # Navigate/create nested structure
            for part in parts[:-1]:  # All parts except the filename
                if part not in current:
                    current[part] = {}
                current = current[part]

            # Add the file blob
            current[parts[-1]] = blob_hash

        # Recursively create trees from the structure
        def create_tree_recursive(structure: dict) -> str:
            """Recursively create git tree objects from nested directory structure."""
            entries = []

            for name, value in sorted(structure.items()):
                if isinstance(value, dict):
                    # It's a directory - recursively create subtree
                    subtree_hash = create_tree_recursive(value)
                    if not subtree_hash:
                        return ""
                    entries.append(f"040000 tree {subtree_hash}\t{name}\n")
                else:
                    # It's a file blob
                    entries.append(f"100644 blob {value}\t{name}\n")

            # Create tree from entries
            return GitManager.create_tree(bare_repo, entries)

        tree_hash = create_tree_recursive(tree_structure)
        if not tree_hash:
            LOGGER.error("Failed to create tree structure")
            return ""

        # Get the parent commit hash
        parent_hash = GitManager.get_commit_id_by_ref(bare_repo, "refs/memov/HEAD", verbose=False)

        # Commit the tree
        commit_hash = GitManager.commit_tree(bare_repo, tree_hash, commit_msg, parent_hash)
        return commit_hash

    @staticmethod
    def create_commit_from_tree_structure(
        bare_repo: str, tree_structure: dict, commit_msg: str
    ) -> str:
        """Create a commit from a pre-built tree structure with blob hashes.

        Args:
            bare_repo: Path to the bare git repository
            tree_structure: Nested dict structure where leaves are blob hashes
            commit_msg: Commit message

        Returns:
            Commit hash, or empty string on failure
        """

        # Recursively create trees from the structure
        def create_tree_recursive(structure: dict) -> str:
            """Recursively create git tree objects from nested directory structure."""
            entries = []

            for name, value in sorted(structure.items()):
                if isinstance(value, dict):
                    # It's a directory - recursively create subtree
                    subtree_hash = create_tree_recursive(value)
                    if not subtree_hash:
                        return ""
                    entries.append(f"040000 tree {subtree_hash}\t{name}\n")
                else:
                    # It's a file blob
                    entries.append(f"100644 blob {value}\t{name}\n")

            # Create tree from entries
            return GitManager.create_tree(bare_repo, entries)

        tree_hash = create_tree_recursive(tree_structure)
        if not tree_hash:
            LOGGER.error("Failed to create tree structure")
            return ""

        # Get the parent commit hash
        parent_hash = GitManager.get_commit_id_by_ref(bare_repo, "refs/memov/HEAD", verbose=False)

        # Commit the tree
        commit_hash = GitManager.commit_tree(bare_repo, tree_hash, commit_msg, parent_hash)
        return commit_hash

    @staticmethod
    def git_show(bare_repo: str, commit_id: str, return_output: bool = False) -> Optional[str]:
        """Show details of a specific snapshot in the memov bare repo, similar to git show.

        Args:
            bare_repo: Path to the bare git repository
            commit_id: Commit hash to show
            return_output: If True, return the output as a string instead of printing

        Returns:
            If return_output is True, returns the git show output as a string, otherwise None
        """
        command = ["git", f"--git-dir={bare_repo}", "show", commit_id]
        success, output = subprocess_call(command=command)

        if return_output:
            return output.stdout if success else ""
        else:
            sys.stdout.write(output.stdout)
            if output.stderr:
                sys.stderr.write(output.stderr)
            return None

    @staticmethod
    def get_commit_history(bare_repo: str, tip: str) -> list[str]:
        """Return a list of commit hashes from the given tip in chronological order.

        Args:
            bare_repo (str): Path to the bare git repository.
            tip (str): Branch name, tag, or commit SHA.

        Returns:
            List[str]: Commit hashes from oldest to newest.
        """
        command = ["git", f"--git-dir={bare_repo}", "rev-list", "--reverse", tip]
        success, output = subprocess_call(command=command)

        if success:
            return output.stdout.strip().splitlines()
        else:
            LOGGER.error(
                f"Failed to get commit history for {tip} in repository at {bare_repo}: {output.stderr}"
            )
            return []

    @staticmethod
    def get_commit_message(bare_repo: str, commit_id: str) -> str:
        """Get the commit message for a specific commit ID."""
        command = ["git", f"--git-dir={bare_repo}", "log", "-1", "--pretty=format:%B", commit_id]
        success, output = subprocess_call(command=command)

        if success and output.stdout:
            return output.stdout.strip()
        else:
            LOGGER.error(
                f"Failed to get commit message for {commit_id} in repository at {bare_repo}"
            )
            return ""

    @staticmethod
    def git_archive(bare_repo: str, commit_id: str) -> Optional[bytes]:
        """Export the content of a specific commit to a tar archive."""
        command = ["git", f"--git-dir={bare_repo}", "archive", "--format=tar", commit_id]
        success, output = subprocess_call(command=command, text=False)

        if success:
            return output.stdout
        else:
            # Get detailed error message from git
            stderr_msg = ""
            if output is not None and hasattr(output, "stderr"):
                stderr = output.stderr
                # Handle both bytes and string stderr
                if isinstance(stderr, bytes):
                    stderr_msg = stderr.decode("utf-8", errors="replace")
                else:
                    stderr_msg = str(stderr)
            LOGGER.error(
                f"Failed to export commit {commit_id} to tar archive in repository at {bare_repo}. "
                f"Git error: {stderr_msg}"
            )
            return None

    @staticmethod
    def update_ref(bare_repo: str, ref_name: str, commit_id: str) -> None:
        """Update a reference in the bare Git repository."""
        command = ["git", f"--git-dir={bare_repo}", "update-ref", ref_name, commit_id]
        success, output = subprocess_call(command=command)

        if not success:
            LOGGER.error(
                f"Failed to update ref {ref_name} to {commit_id} in repository at {bare_repo}"
            )

    @staticmethod
    def amend_commit_message(
        repo_path: str, commit_hash: str, new_message: str
    ) -> tuple[bool, str]:
        """
        Attach prompt/response to the commit using git notes (works on bare repos).
        Returns (success, error_message)
        """
        # Use git notes with -F - to read message from stdin (supports multiline)
        command = ["git", f"--git-dir={repo_path}", "notes", "add", "-f", "-F", "-", commit_hash]
        # Use binary mode to prevent Windows from converting \n to \r\n
        input_data = new_message.encode("utf-8")
        success, output = subprocess_call(command=command, input=input_data, text=False)
        if not success:
            error_msg = ""
            if output is not None and hasattr(output, "stderr"):
                stderr = output.stderr
                if isinstance(stderr, bytes):
                    error_msg = stderr.decode("utf-8", errors="replace")
                else:
                    error_msg = str(stderr) if stderr else "Unknown error"
            LOGGER.error(f"Failed to add git note for {commit_hash}: {error_msg}")
            return False, error_msg
        return True, ""

    @staticmethod
    def get_commit_note(repo_path: str, commit_hash: str) -> str:
        """
        Get the git note for a specific commit.
        Returns the note content as a string, or empty string if no note exists.
        """
        command = ["git", f"--git-dir={repo_path}", "notes", "show", commit_hash]
        success, output = subprocess_call(command=command)

        if success and output.stdout:
            return output.stdout.strip()
        else:
            # No note exists for this commit, which is normal
            return ""

    @staticmethod
    def ensure_git_user_config(
        repo_path: str, default_name: Optional[str] = None, default_email: Optional[str] = None
    ) -> None:
        """
        Ensure that the git user.name and user.email are set in the repository.

        Args:
            repo_path (str): Path to the Git repository.
            default_name (str | None): Default name to set if user.name is not set.
            default_email (str | None): Default email to set if user.email is not set. If None, use "memov" and "memov@example.com".
        """
        default_name = default_name or "memov"
        default_email = default_email or "memov@example.com"

        def set_git_config(key: str, value: str) -> bool:
            """Set a git config key to a specific value, if not already set."""
            check_command = ["git", f"--git-dir={repo_path}", "config", "--get", key]
            success, output = subprocess_call(command=check_command)

            if not success or not output.stdout.strip():
                LOGGER.warning(f"Git {key} not set. Setting default value.")
                command = ["git", f"--git-dir={repo_path}", "config", key, value]
                success, _ = subprocess_call(command=command)
                return success

            return True

        if set_git_config("user.name", default_name):
            LOGGER.info(f"Set git user.name to '{default_name}' in repository at {repo_path}")
        else:
            LOGGER.error(
                f"Failed to set git user.name to '{default_name}' in repository at {repo_path}"
            )

        if set_git_config("user.email", default_email):
            LOGGER.info(f"Set git user.email to '{default_email}' in repository at {repo_path}")
        else:
            LOGGER.error(
                f"Failed to set git user.email to '{default_email}' in repository at {repo_path}"
            )

    @staticmethod
    def get_commits_info_batch(repo_path: str, commit_hashes: list[str]) -> dict[str, dict]:
        """Get commit info (message, timestamp, author) for multiple commits in one call.

        This is much faster than calling get_commit_message/get_commit_info for each commit.

        Args:
            repo_path: Path to the Git repository.
            commit_hashes: List of commit hashes to get info for.

        Returns:
            Dictionary mapping commit hash to info dict with keys:
                - message: Full commit message
                - timestamp: ISO format timestamp
                - author: Author name
        """
        if not commit_hashes:
            return {}

        # Use a unique delimiter that won't appear in commit messages
        record_sep = "<<<RECORD_SEP>>>"
        field_sep = "<<<FIELD_SEP>>>"

        # Format: hash, author date (ISO), author name, full message
        format_str = f"%H{field_sep}%aI{field_sep}%an{field_sep}%B{record_sep}"

        command = [
            "git",
            f"--git-dir={repo_path}",
            "log",
            f"--format={format_str}",
            "--no-walk",
            "--stdin",
        ]

        # Pass commit hashes via stdin
        input_data = "\n".join(commit_hashes)
        success, output = subprocess_call(command=command, input=input_data)

        result = {}
        if success and output.stdout:
            records = output.stdout.split(record_sep)
            for record in records:
                record = record.strip()
                if not record:
                    continue
                parts = record.split(field_sep)
                if len(parts) >= 4:
                    commit_hash = parts[0]
                    result[commit_hash] = {
                        "message": parts[3].strip(),
                        "timestamp": parts[1],
                        "author": parts[2],
                    }

        return result

    @staticmethod
    def get_all_notes_batch(repo_path: str) -> dict[str, str]:
        """Get all git notes in one call.

        Args:
            repo_path: Path to the Git repository.

        Returns:
            Dictionary mapping commit hash to note content.
        """
        # List all notes with their content
        command = [
            "git",
            f"--git-dir={repo_path}",
            "notes",
            "list",
        ]
        success, output = subprocess_call(command=command)

        if not success or not output.stdout:
            return {}

        # notes list returns: blob_hash commit_hash
        note_refs = {}
        for line in output.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                blob_hash, commit_hash = parts[0], parts[1]
                note_refs[commit_hash] = blob_hash

        if not note_refs:
            return {}

        # Batch fetch all note contents using cat-file --batch
        result = {}
        blob_to_commit = {v: k for k, v in note_refs.items()}

        # Use cat-file --batch to get all blobs at once
        command = [
            "git",
            f"--git-dir={repo_path}",
            "cat-file",
            "--batch",
        ]
        input_data = "\n".join(note_refs.values())
        success, output = subprocess_call(command=command, input=input_data)

        if success and output.stdout:
            # Parse batch output: each blob has header line followed by content
            lines = output.stdout.split("\n")
            i = 0
            while i < len(lines):
                header = lines[i]
                if " blob " in header:
                    parts = header.split()
                    blob_hash = parts[0]
                    size = int(parts[2])
                    # Collect content lines until we have enough bytes
                    content_lines = []
                    content_len = 0
                    i += 1
                    while i < len(lines) and content_len < size:
                        line = lines[i]
                        content_lines.append(line)
                        content_len += len(line) + 1  # +1 for newline
                        i += 1
                    content = "\n".join(content_lines).strip()
                    if blob_hash in blob_to_commit:
                        result[blob_to_commit[blob_hash]] = content
                else:
                    i += 1

        return result

    @staticmethod
    def get_diff_status_batch(
        repo_path: str, commit_hashes: list[str]
    ) -> dict[str, dict[str, dict]]:
        """Get file status (added/modified/deleted) for multiple commits.

        This uses git log with --name-status to get status for all commits at once.

        Args:
            repo_path: Path to the Git repository.
            commit_hashes: List of commit hashes.

        Returns:
            Dictionary mapping commit hash to file status dict.
            Example: {"abc123": {"file.py": {"status": "modified", "hunks": []}}}
        """
        if not commit_hashes:
            return {}

        record_sep = "<<<RECORD_SEP>>>"

        # Get commit hash and name-status in one call
        command = [
            "git",
            f"--git-dir={repo_path}",
            "log",
            f"--format={record_sep}%H",
            "--name-status",
            "--no-walk",
            "--stdin",
        ]

        input_data = "\n".join(commit_hashes)
        success, output = subprocess_call(command=command, input=input_data)

        result = {}
        if success and output.stdout:
            # Split by record separator, then parse each record
            parts = output.stdout.split(record_sep)
            for section in parts:
                section = section.strip()
                if not section:
                    continue

                lines = section.split("\n")
                if not lines:
                    continue

                commit_hash = lines[0].strip()
                if not commit_hash:
                    continue

                # Parse file status from remaining lines
                files_status = {}
                for line in lines[1:]:
                    line = line.strip()
                    if not line:
                        continue
                    file_parts = line.split("\t", 1)
                    if len(file_parts) >= 2:
                        status_char, file_path = file_parts[0], file_parts[1]
                        if status_char.startswith("A"):
                            files_status[file_path] = {"status": "added", "hunks": []}
                        elif status_char.startswith("D"):
                            files_status[file_path] = {"status": "deleted", "hunks": []}
                        else:
                            files_status[file_path] = {"status": "modified", "hunks": []}

                result[commit_hash] = files_status

        return result

    @staticmethod
    def get_files_by_commits_batch(
        repo_path: str, commit_hashes: list[str]
    ) -> dict[str, list[str]]:
        """Get the list of files for multiple commits.

        Args:
            repo_path: Path to the Git repository.
            commit_hashes: List of commit hashes.

        Returns:
            Dictionary mapping commit hash to list of file paths.
        """
        if not commit_hashes:
            return {}

        result = {}
        for commit_hash in commit_hashes:
            command = [
                "git",
                f"--git-dir={repo_path}",
                "ls-tree",
                "-r",
                "--name-only",
                commit_hash,
            ]
            success, output = subprocess_call(command=command)
            if success and output.stdout:
                cleaned_stdout = output.stdout.replace("\r", "").strip()
                files = [
                    clean_windows_git_lstree_output(f) for f in cleaned_stdout.splitlines() if f
                ]
            else:
                files = []
            result[commit_hash] = files

        return result
