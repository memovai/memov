import logging
import os
import sys
from typing import TYPE_CHECKING, List, Optional

import typer
from typing_extensions import Annotated

# Lazy imports for faster startup - only import heavy modules when needed
# These imports are deferred until get_manager() is called
if TYPE_CHECKING:
    from memov.core.manager import MemovManager, MemStatus
    from rich.console import Console

# Lazy console initialization
_console: Optional["Console"] = None


def get_console() -> "Console":
    """Get or create the Rich console (lazy initialization)."""
    global _console
    if _console is None:
        from rich.console import Console

        _console = Console()
    return _console



# Common type aliases
LocOption = Annotated[
    str,
    typer.Option("--loc", help="Specify the project directory path (default: current directory)"),
]
PromptOption = Annotated[
    Optional[str],
    typer.Option(
        "-p", "--prompt", help="Descriptive prompt explaining the purpose of this operation"
    ),
]
ResponseOption = Annotated[
    Optional[str],
    typer.Option(
        "-r", "--response", help="AI or user response to the prompt (optional documentation)"
    ),
]
ByUserOption = Annotated[
    bool,
    typer.Option(
        "-u", "--by_user", help="Mark this operation as performed by a human user (vs AI)"
    ),
]


# Create Typer app
app = typer.Typer(
    name="memov",
    help="memov - AI-assisted version control on top of Git. Track, snapshot, and manage your project evolution.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    add_completion=False,  # Disable shell completion for now
)


def get_manager(loc: str, skip_mem_check: bool = False) -> "MemovManager":
    """Get MemovManager instance, and config the logging.

    This function uses lazy imports to speed up CLI startup time.
    Heavy modules (MemovManager, logging utils) are only imported when needed.
    """
    # Lazy import: only load these when actually creating a manager
    from memov.core.manager import MemovManager, MemStatus
    from memov.utils.logging_utils import setup_logging

    # Configure logging
    setup_logging(loc)

    # Validate and return MemovManager instance
    loc = os.path.abspath(loc)
    manager = MemovManager(project_path=loc)

    status = manager.check(only_basic_check=skip_mem_check)
    if status is not MemStatus.SUCCESS:
        sys.exit(1)

    return manager


@app.command()
def init(loc: LocOption = ".") -> None:
    """Initialize memov repository in the specified location."""
    manager = get_manager(loc, skip_mem_check=True)
    manager.init()


@app.command()
def track(
    loc: LocOption = ".",
    file_paths: Annotated[
        Optional[List[str]], typer.Argument(help="List of file paths to track")
    ] = None,
    prompt: PromptOption = None,
    response: ResponseOption = None,
    by_user: ByUserOption = False,
) -> None:
    """Track files in the project directory for version control."""
    manager = get_manager(loc)
    manager.track(file_paths, prompt, response, by_user)


@app.command()
def snap(
    files: Annotated[
        Optional[List[str]],
        typer.Option(
            "--files",
            help="Specific files to snapshot (comma-separated or multiple --files flags). If not specified, snapshots all tracked files.",
        ),
    ] = None,
    loc: LocOption = ".",
    prompt: PromptOption = None,
    response: ResponseOption = None,
    by_user: ByUserOption = False,
) -> None:
    """Create a snapshot of the current project state."""
    manager = get_manager(loc)
    manager.snapshot(file_paths=files, prompt=prompt, response=response, by_user=by_user)


@app.command()
def rename(
    old_path: Annotated[str, typer.Argument(help="Current path of the file to rename")],
    new_path: Annotated[str, typer.Argument(help="New path for the file")],
    loc: LocOption = ".",
    prompt: PromptOption = None,
    response: ResponseOption = None,
    by_user: ByUserOption = False,
) -> None:
    """Rename a tracked file and record the operation."""
    manager = get_manager(loc)
    manager.rename(old_path, new_path, prompt, response, by_user)


@app.command()
def remove(
    file_path: Annotated[str, typer.Argument(help="Path of the file to remove from tracking")],
    loc: LocOption = ".",
    prompt: PromptOption = None,
    response: ResponseOption = None,
    by_user: ByUserOption = False,
) -> None:
    """Remove a tracked file from the project and record the operation."""
    manager = get_manager(loc)
    manager.remove(file_path, prompt, response, by_user)


@app.command()
def history(loc: LocOption = ".") -> None:
    """Show history of snapshots and operations."""
    manager = get_manager(loc)
    manager.history()


@app.command()
def show(
    snapshot_id: Annotated[str, typer.Argument(help="ID/hash of the snapshot to display")],
    loc: LocOption = ".",
) -> None:
    """Show detailed information about a specific snapshot."""
    manager = get_manager(loc)
    manager.show(snapshot_id)


@app.command()
def jump(
    snapshot_id: Annotated[str, typer.Argument(help="ID/hash of the snapshot to jump to")],
    loc: LocOption = ".",
) -> None:
    """Jump to a specific snapshot, restoring the project state."""
    manager = get_manager(loc)
    manager.jump(snapshot_id)


@app.command()
def branch(
    name: Annotated[Optional[str], typer.Argument(help="Branch name to create")] = None,
    delete: Annotated[Optional[str], typer.Option("-d", "--delete", help="Delete branch")] = None,
    loc: LocOption = ".",
) -> None:
    """List, create, or delete branches."""
    manager = get_manager(loc)
    if delete:
        manager.delete_branch(delete)
    elif name:
        manager.create_branch(name)
    else:
        manager.list_branches()


@app.command()
def switch(
    branch_name: Annotated[str, typer.Argument(help="Branch to switch to (creates if not exists)")],
    loc: LocOption = ".",
) -> None:
    """Switch to a branch (does not change files). Creates branch if it doesn't exist."""
    manager = get_manager(loc)
    manager.switch_branch(branch_name)


@app.command()
def status(loc: LocOption = ".") -> None:
    """Show status of working directory compared to the latest snapshot."""
    manager = get_manager(loc)
    manager.status()


@app.command()
def amend(
    commit_hash: Annotated[str, typer.Argument(help="Commit hash to add notes to")],
    loc: LocOption = ".",
    prompt: PromptOption = None,
    response: ResponseOption = None,
    by_user: ByUserOption = False,
) -> None:
    """Add or update prompt/response notes for a specific commit."""
    manager = get_manager(loc)
    manager.amend_commit_message(commit_hash, prompt, response, by_user)


@app.command()
def version() -> None:
    """Show version information."""
    manager = get_manager(loc=".", skip_mem_check=True)
    manager.version()


@app.command()
def report(
    loc: LocOption = ".",
    format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format (json, text)",
        ),
    ] = "json",
) -> None:
    """Generate a report of the latest commit with all necessary information for external MCP operations.

    This command outputs commit information in a format suitable for external MCP snap operations,
    including commit hash, diff, branch name, and parent commit.

    Example:
        # Get JSON report for external MCP
        mem report

        # Save report to file
        mem report > commit_info.json

        # Use with bash variables
        REPORT=$(mem report)
        COMMIT_HASH=$(echo $REPORT | jq -r '.commit_hash')
    """
    import json

    manager = get_manager(loc)

    # Generate report
    report_data = manager.report(format=format)

    if report_data is None:
        get_console().print("[yellow]No commits found in memov repository[/yellow]")
        sys.exit(1)

    # Output based on format
    if format == "json":
        # Output as JSON to stdout (without rich formatting)
        print(json.dumps(report_data, indent=2, ensure_ascii=False))
    elif format == "text":
        # Output as human-readable text
        console = get_console()
        console.print(f"[bold cyan]Commit Report[/bold cyan]")
        console.print(f"[bold]Commit Hash:[/bold] {report_data['commit_hash']}")
        console.print(f"[bold]Branch:[/bold] {report_data['branch'] or 'N/A'}")
        console.print(f"[bold]Parent Commit:[/bold] {report_data['parent_commit'] or 'N/A'}")
        console.print(f"[bold]Commit Message:[/bold] {report_data['commit_message']}")
        console.print(f"\n[bold]Metadata:[/bold]")
        console.print(f"  Prompt: {report_data['metadata']['prompt'] or 'N/A'}")
        console.print(f"  Response: {report_data['metadata']['response'] or 'N/A'}")
        console.print(f"  Source: {report_data['metadata']['source'] or 'N/A'}")
        console.print(f"  Files: {', '.join(report_data['metadata']['files']) or 'N/A'}")
        console.print(f"\n[bold]Diff:[/bold]")
        console.print(report_data["diff"])
    else:
        get_console().print(f"[red]Unsupported format: {format}[/red]")
        sys.exit(1)


@app.command()
def sync(loc: LocOption = ".") -> None:
    """Sync pending operations to VectorDB for semantic search.

    This command batch writes all cached operations (from snap, track, etc.)
    to the VectorDB. Pending operations are stored in memory during the session
    and must be explicitly synced using this command.

    Example:
        mem snap file1.py
        mem snap file2.py
        mem sync  # Write all pending operations to VectorDB
    """
    manager = get_manager(loc)

    console = get_console()

    # Check if RAG mode is available
    if not manager.is_rag_available():
        console.print(
            "[red]✗ RAG mode is not available[/red]\n\n"
            "[yellow]This command requires ChromaDB dependencies.[/yellow]\n"
            "Install with:\n"
            "  [cyan]pip install memov[rag][/cyan]\n"
            "or\n"
            "  [cyan]uv pip install memov[rag][/cyan]\n\n"
            "[dim]Note: Use the basic mode binary if you don't need semantic search.[/dim]"
        )
        sys.exit(1)

    # Check pending writes count
    pending_count = manager.get_pending_writes_count()

    if pending_count == 0:
        console.print("[yellow]No pending writes to sync[/yellow]")
        return

    console.print(f"[blue]Syncing {pending_count} pending operation(s) to VectorDB...[/blue]")

    # Perform sync
    successful, failed = manager.sync_to_vectordb()

    # Report results
    if failed == 0:
        console.print(f"[green]✓ Successfully synced {successful} operation(s)[/green]")
    else:
        console.print(
            f"[yellow]Sync completed with errors:[/yellow]\n"
            f"  [green]✓ Successful: {successful}[/green]\n"
            f"  [red]✗ Failed: {failed}[/red]"
        )


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query (prompt text or file path)")],
    loc: LocOption = ".",
    by_files: Annotated[
        bool,
        typer.Option(
            "--by-files",
            "-f",
            help="Search by file paths instead of prompt text",
        ),
    ] = False,
    operation_type: Annotated[
        Optional[str],
        typer.Option(
            "--type",
            "-t",
            help="Filter by operation type: track, snap, rename, remove",
        ),
    ] = None,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-n",
            help="Maximum number of results to return",
        ),
    ] = 10,
    show_distance: Annotated[
        bool,
        typer.Option(
            "--show-distance/--no-distance",
            "-d/-D",
            help="Show similarity distance scores (default: enabled for semantic search)",
        ),
    ] = True,
) -> None:
    """Search for commits using semantic search on prompts or file paths.

    Examples:
        # Search by prompt
        mem search "authentication bug fix"

        # Search by file paths
        mem search "src/auth.py" --by-files

        # Filter by operation type
        mem search "refactor" --type snap

        # Limit results and show distances
        mem search "database" --limit 5 --show-distance
    """
    manager = get_manager(loc)
    console = get_console()

    # Check if RAG mode is available
    if not manager.is_rag_available():
        console.print(
            "[red]✗ RAG mode is not available[/red]\n\n"
            "[yellow]This command requires ChromaDB dependencies.[/yellow]\n"
            "Install with:\n"
            "  [cyan]pip install memov[rag][/cyan]\n"
            "or\n"
            "  [cyan]uv pip install memov[rag][/cyan]\n\n"
            "[dim]Note: Use the basic mode binary if you don't need semantic search.[/dim]"
        )
        sys.exit(1)

    try:
        if by_files:
            # Search by file paths
            file_paths = [p.strip() for p in query.split(",")]
            results = manager.find_commits_by_files(file_paths)

            if not results:
                console.print(
                    f"[yellow]No commits found for files: {', '.join(file_paths)}[/yellow]"
                )
                return

            # Limit results
            results = results[:limit]
        else:
            # Search by prompt (semantic search)
            results = manager.find_similar_prompts(
                query_prompt=query, n_results=limit, operation_type=operation_type
            )

            if not results:
                console.print(f"[yellow]No similar prompts found for: {query}[/yellow]")
                return

        # Create rich table (lazy import)
        from rich.table import Table

        table = Table(title=f"Search Results for: {query}", show_header=True, header_style="bold")

        # Add columns
        table.add_column("Commit", style="cyan", no_wrap=True, width=8)
        table.add_column("Type", style="magenta", width=8)
        table.add_column("Source", style="blue", width=6)
        if show_distance and not by_files:
            table.add_column("Distance", style="yellow", width=8)
        table.add_column("Files", style="green", width=30)
        table.add_column("Text Preview", style="white", width=50)

        # Add rows
        for result in results:
            metadata = result.get("metadata", {})
            commit_hash = metadata.get("commit_hash", "unknown")[:8]
            op_type = metadata.get("operation_type", "unknown")
            source = metadata.get("source", "unknown")
            files = metadata.get("files", [])

            # Format files (stored as comma-separated string)
            if isinstance(files, str):
                # Files are stored as comma-separated string
                file_list = [f.strip() for f in files.split(",") if f.strip()]
                if len(file_list) > 2:
                    files_str = ", ".join(file_list[:2]) + f" (+{len(file_list) - 2} more)"
                else:
                    files_str = ", ".join(file_list) if file_list else "No files"
            elif isinstance(files, list):
                # Fallback for backwards compatibility
                files_str = ", ".join(files[:2])
                if len(files) > 2:
                    files_str += f" (+{len(files) - 2} more)"
            else:
                files_str = str(files)

            # Get text preview
            text = result.get("text", "")
            if len(text) > 50:
                text_preview = text[:47] + "..."
            else:
                text_preview = text

            # Build row
            row = [commit_hash, op_type, source]

            if show_distance and not by_files:
                distance = result.get("distance", 0.0)
                similarity = (1 - distance) * 100
                row.append(f"{similarity:.1f}%")

            row.extend([files_str, text_preview])
            table.add_row(*row)

        # Print table
        console.print()
        console.print(table)
        console.print()

        # Print statistics
        info = manager.get_vectordb_info()
        console.print(
            f"[dim]Searched {info.get('count', 0)} chunks in collection '{info.get('name', 'unknown')}'[/dim]"
        )

    except Exception as e:
        console.print(f"[red]Error during search: {e}[/red]")
        logging.error(f"Search error: {e}", exc_info=True)
        sys.exit(1)


@app.command()
def ui(
    loc: LocOption = ".",
    port: Annotated[int, typer.Option("--port", help="HTTP port for the UI server")] = 8765,
    no_browser: Annotated[
        bool, typer.Option("--no-browser", help="Don't automatically open browser")
    ] = False,
) -> None:
    """Start a local web UI to visualize .mem directory git information.

    This command starts a web server that provides a visual interface for exploring
    the memov history, including commits, diffs, prompts, responses, and more.

    Examples:
        # Start UI with default settings (opens browser)
        mem ui

        # Start on a specific port
        mem ui --port 9000

        # Don't open browser automatically
        mem ui --no-browser

        # Specify project directory
        mem ui --loc /path/to/project
    """
    from memov.ui.server import start_ui_server

    manager = get_manager(loc)
    start_ui_server(manager=manager, port=port, open_browser=not no_browser)


def main() -> None:
    """Main entry point for the memov command line interface."""
    try:
        app()
    except KeyboardInterrupt:
        logging.info("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        logging.debug("Full traceback:", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
