import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from memov.utils.string_utils import clean_windows_git_lstree_output

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

        if text:
            kwargs["encoding"] = "utf-8"
        if input is not None:
            kwargs["input"] = input
        else:
            kwargs["stdin"] = subprocess.DEVNULL

        output = subprocess.run(command, **kwargs)
        return True, output
    except subprocess.CalledProcessError as e:
        LOGGER.debug(f"Command failed: {' '.join(command)}\nStdout: {e.stdout}\nStderr: {e.stderr}")
        return False, None


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
    def get_files_by_commit(repo_path: str, commit_id: str) -> tuple[list[str], list[str]]:
        """Get the list of files in a specific commit."""
        command = ["git", f"--git-dir={repo_path}", "ls-tree", "-r", "--name-only", commit_id]
        success, output = subprocess_call(command=command)

        if success and output.stdout:
            file_rel_paths = []
            file_abs_paths = []
            for rel_file in output.stdout.strip().splitlines():
                rel_file = clean_windows_git_lstree_output(rel_file)
                abs_file_path = os.path.join(repo_path, "..", "..", rel_file)
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
            for line in output.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) == 4:
                    blob_hash = parts[2]
                    rel_file = parts[3]
                    rel_file = clean_windows_git_lstree_output(rel_file)
                    # If project_path is provided, resolve relative to it; otherwise use cwd
                    if project_path:
                        abs_path = (Path(project_path) / rel_file).resolve()
                    else:
                        abs_path = Path(rel_file).resolve()
                    file_blobs[abs_path] = blob_hash
                else:
                    LOGGER.warning(f"Unexpected output format: {line}")

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
    def create_tree(repo_path: str, entries: list[str]) -> str:
        """Create a tree object in the Git repository."""
        command = ["git", f"--git-dir={repo_path}", "mktree"]
        success, output = subprocess_call(command=command, input="".join(entries))

        if success and output.stdout:
            return output.stdout.strip()
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

        success, output = subprocess_call(command=command, input=commit_msg)

        if success and output.stdout:
            return output.stdout.strip()
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

        # Build a directory tree structure
        # Format: {"dir1": {"dir2": {"file.txt": blob_hash}}}
        tree_structure = {}

        for rel_file, abs_path in new_file_paths.items():
            blob_hash = GitManager.write_blob(bare_repo, abs_path)
            if not blob_hash:
                LOGGER.error(f"Failed to create blob for {rel_file}")
                return ""

            # Split path into parts
            parts = rel_file.split("/")
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
    def git_show(bare_repo: str, commit_id: str) -> None:
        """Show details of a specific snapshot in the memov bare repo, similar to git show."""
        command = ["git", f"--git-dir={bare_repo}", "show", commit_id]
        success, output = subprocess_call(command=command)

        if success and output:
            sys.stdout.write(output.stdout)
            if output.stderr:
                sys.stderr.write(output.stderr)
        else:
            LOGGER.error(f"Failed to show commit {commit_id} in repository at {bare_repo}")

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
            err_msg = output.stderr if output else "Unknown error"
            LOGGER.error(
                f"Failed to get commit history for {tip} in repository at {bare_repo}: {err_msg}"
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
            LOGGER.error(
                f"Failed to export commit {commit_id} to tar archive in repository at {bare_repo}"
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
        success, output = subprocess_call(command=command, input=new_message)
        if not success:
            error_msg = output.stderr if output else "Unknown error"
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
