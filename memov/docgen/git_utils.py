"""
Git utilities for analyzing commits and branches.

Provides functions to:
- Get changed files from commits
- Get commit messages and metadata
- Analyze commit ranges
- Get branch information
"""

import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CommitInfo:
    """Information about a Git commit."""
    hash: str
    author: str
    date: datetime
    message: str
    changed_files: List[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0


class GitUtils:
    """Utilities for Git repository operations."""

    def __init__(self, repo_path: str = "."):
        """
        Initialize Git utilities.

        Args:
            repo_path: Path to the Git repository
        """
        self.repo_path = Path(repo_path).resolve()
        self._validate_git_repo()

    def _validate_git_repo(self) -> None:
        """Check if the path is a valid Git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            logger.info(f"Git repository found at {self.repo_path}")
        except subprocess.CalledProcessError:
            raise ValueError(f"Not a Git repository: {self.repo_path}")

    def get_commit_info(self, commit_hash: str) -> Optional[CommitInfo]:
        """
        Get detailed information about a commit.

        Args:
            commit_hash: Commit hash or reference (e.g., HEAD, branch name)

        Returns:
            CommitInfo object or None if commit not found
        """
        try:
            # Get commit metadata
            result = subprocess.run(
                [
                    "git", "log", "-1",
                    "--format=%H%n%an%n%aI%n%B",
                    commit_hash
                ],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )

            lines = result.stdout.strip().split('\n')
            if len(lines) < 4:
                logger.error(f"Invalid commit format for {commit_hash}")
                return None

            full_hash = lines[0]
            author = lines[1]
            date_str = lines[2]
            message = '\n'.join(lines[3:])

            # Parse date
            date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))

            # Get changed files
            changed_files = self.get_changed_files(commit_hash)

            # Get stats
            stats = self.get_commit_stats(commit_hash)

            return CommitInfo(
                hash=full_hash,
                author=author,
                date=date,
                message=message,
                changed_files=changed_files,
                additions=stats.get('additions', 0),
                deletions=stats.get('deletions', 0)
            )

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get commit info for {commit_hash}: {e}")
            return None

    def get_changed_files(
        self,
        commit_hash: str,
        file_extensions: Optional[List[str]] = None
    ) -> List[str]:
        """
        Get list of files changed in a commit.

        Args:
            commit_hash: Commit hash or reference
            file_extensions: Optional list of file extensions to filter (e.g., ['.py', '.js'])

        Returns:
            List of absolute file paths
        """
        try:
            # Get changed files relative to parent
            result = subprocess.run(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )

            files = []
            for file_path in result.stdout.strip().split('\n'):
                if not file_path:
                    continue

                # Convert to absolute path
                abs_path = (self.repo_path / file_path).resolve()

                # Filter by extension if specified
                if file_extensions:
                    if not any(str(abs_path).endswith(ext) for ext in file_extensions):
                        continue

                # Only include existing files
                if abs_path.exists():
                    files.append(str(abs_path))

            return files

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get changed files for {commit_hash}: {e}")
            return []

    def get_commit_stats(self, commit_hash: str) -> Dict[str, int]:
        """
        Get statistics for a commit (additions, deletions).

        Args:
            commit_hash: Commit hash or reference

        Returns:
            Dictionary with 'additions' and 'deletions' keys
        """
        try:
            result = subprocess.run(
                ["git", "show", "--shortstat", "--format=", commit_hash],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )

            output = result.stdout.strip()
            stats = {'additions': 0, 'deletions': 0}

            # Parse output like: "2 files changed, 10 insertions(+), 5 deletions(-)"
            if 'insertion' in output:
                additions = output.split('insertion')[0].split()[-1]
                stats['additions'] = int(additions)
            if 'deletion' in output:
                deletions = output.split('deletion')[0].split()[-1]
                stats['deletions'] = int(deletions)

            return stats

        except (subprocess.CalledProcessError, ValueError) as e:
            logger.error(f"Failed to get commit stats for {commit_hash}: {e}")
            return {'additions': 0, 'deletions': 0}

    def get_commits_in_range(
        self,
        start_ref: str,
        end_ref: str = "HEAD"
    ) -> List[CommitInfo]:
        """
        Get all commits in a range.

        Args:
            start_ref: Starting commit reference
            end_ref: Ending commit reference (default: HEAD)

        Returns:
            List of CommitInfo objects
        """
        try:
            # Get commit hashes in range
            result = subprocess.run(
                ["git", "rev-list", f"{start_ref}..{end_ref}"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )

            commits = []
            for commit_hash in result.stdout.strip().split('\n'):
                if commit_hash:
                    commit_info = self.get_commit_info(commit_hash)
                    if commit_info:
                        commits.append(commit_info)

            return commits

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get commits in range {start_ref}..{end_ref}: {e}")
            return []

    def get_branch_commits(
        self,
        branch_name: str,
        base_branch: str = "main"
    ) -> List[CommitInfo]:
        """
        Get commits unique to a branch (not in base branch).

        Args:
            branch_name: Branch to analyze
            base_branch: Base branch to compare against

        Returns:
            List of CommitInfo objects
        """
        return self.get_commits_in_range(base_branch, branch_name)

    def get_current_branch(self) -> str:
        """
        Get the name of the current branch.

        Returns:
            Branch name or empty string if detached HEAD
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            branch = result.stdout.strip()
            return branch if branch != "HEAD" else ""

        except subprocess.CalledProcessError:
            return ""

    def get_file_content_at_commit(
        self,
        file_path: str,
        commit_hash: str
    ) -> Optional[str]:
        """
        Get file content at a specific commit.

        Args:
            file_path: Relative path to file from repo root
            commit_hash: Commit hash or reference

        Returns:
            File content as string or None if not found
        """
        try:
            result = subprocess.run(
                ["git", "show", f"{commit_hash}:{file_path}"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout

        except subprocess.CalledProcessError:
            logger.warning(f"Could not get {file_path} at {commit_hash}")
            return None

    def get_commit_diff(
        self,
        commit_hash: str,
        file_path: Optional[str] = None
    ) -> str:
        """
        Get diff for a commit.

        Args:
            commit_hash: Commit hash or reference
            file_path: Optional specific file to get diff for

        Returns:
            Diff as string
        """
        try:
            cmd = ["git", "show", commit_hash]
            if file_path:
                cmd.append("--")
                cmd.append(file_path)

            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get diff for {commit_hash}: {e}")
            return ""

    def get_all_branches(self) -> List[str]:
        """
        Get list of all branches in the repository.

        Returns:
            List of branch names
        """
        try:
            result = subprocess.run(
                ["git", "branch", "--format=%(refname:short)"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            branches = [b.strip() for b in result.stdout.strip().split('\n') if b.strip()]
            return branches

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get branches: {e}")
            return []

    def get_files_in_branch(
        self,
        branch_name: str,
        file_extensions: Optional[List[str]] = None
    ) -> List[str]:
        """
        Get all files in a branch.

        Args:
            branch_name: Branch name
            file_extensions: Optional list of file extensions to filter

        Returns:
            List of absolute file paths
        """
        try:
            result = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", branch_name],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )

            files = []
            for file_path in result.stdout.strip().split('\n'):
                if not file_path:
                    continue

                # Convert to absolute path
                abs_path = (self.repo_path / file_path).resolve()

                # Filter by extension if specified
                if file_extensions:
                    if not any(str(abs_path).endswith(ext) for ext in file_extensions):
                        continue

                files.append(str(abs_path))

            return files

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get files in branch {branch_name}: {e}")
            return []
