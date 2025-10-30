#!/usr/bin/env python3
"""
CLI tool for generating code documentation.

Supports:
- Commit-level documentation
- Branch-level documentation
- Repository-level documentation
- Mermaid diagram generation
- Web preview server
"""

import logging
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from typing_extensions import Annotated

from memov.docgen.code_analyzer import CodeAnalyzer
from memov.docgen.diagram_generator import DiagramGenerator, DiagramType
from memov.docgen.doc_generator import DocType, DocumentGenerator
from memov.docgen.git_utils import GitUtils
from memov.docgen.preview_server import start_preview_server
from memov.utils.logging_utils import setup_logging

console = Console()
app = typer.Typer(
    name="mem-docgen",
    help="Generate comprehensive documentation from code and Git history",
    no_args_is_help=True,
)

logger = logging.getLogger(__name__)


def init_components(
    project_path: str = ".",
    model: str = "qwen2:0.5b"
) -> tuple:
    """
    Initialize all required components.

    Returns:
        Tuple of (analyzer, generator, diagram_gen, git_utils)
    """
    try:
        # Initialize Git utilities
        git_utils = GitUtils(project_path)

        # Initialize code analyzer
        analyzer = CodeAnalyzer(project_path)

        # Initialize LLM client (optional)
        llm_client = None
        try:
            from memov.debugging.llm_client import LLMClient
            llm_client = LLMClient(models=[model])
        except ImportError:
            console.print("[yellow]Warning: LLM client not available. Using fallback mode.[/yellow]")

        # Initialize generators
        generator = DocumentGenerator(analyzer, llm_client, model)
        diagram_gen = DiagramGenerator(llm_client)

        return analyzer, generator, diagram_gen, git_utils

    except Exception as e:
        console.print(f"[red]Error initializing components: {e}[/red]")
        logger.error(f"Initialization error: {e}", exc_info=True)
        sys.exit(1)


@app.command()
def generate_commit(
    commit_hash: Annotated[str, typer.Argument(help="Commit hash or reference (e.g., HEAD, abc123)")],
    output_dir: Annotated[str, typer.Option("--output", "-o", help="Output directory")] = ".mem/docs/commits",
    doc_type: Annotated[str, typer.Option("--type", "-t", help="Document type")] = "feature",
    model: Annotated[str, typer.Option("--model", "-m", help="LLM model to use")] = "qwen2:0.5b",
    with_diagram: Annotated[bool, typer.Option("--diagram", "-d", help="Generate mermaid diagrams")] = True,
    file_extensions: Annotated[Optional[str], typer.Option("--ext", help="Filter files by extensions (comma-separated)")] = ".py",
    project_path: Annotated[str, typer.Option("--path", "-p", help="Project path")] = ".",
):
    """
    Generate documentation for a specific commit.

    Examples:
        mem-docgen generate-commit HEAD
        mem-docgen generate-commit abc123 --type feature
        mem-docgen generate-commit HEAD~1 --diagram
    """
    console.print(f"\n[cyan]📝 Generating documentation for commit {commit_hash}[/cyan]\n")

    # Initialize components
    analyzer, generator, diagram_gen, git_utils = init_components(project_path, model)

    # Parse file extensions
    extensions = [ext.strip() for ext in file_extensions.split(",")] if file_extensions else None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        # Get commit info
        task = progress.add_task("Fetching commit information...", total=None)
        commit_info = git_utils.get_commit_info(commit_hash)

        if not commit_info:
            console.print(f"[red]✗ Commit not found: {commit_hash}[/red]")
            sys.exit(1)

        # Get changed files
        progress.update(task, description="Analyzing changed files...")
        changed_files = git_utils.get_changed_files(commit_hash, extensions)

        if not changed_files:
            console.print(f"[yellow]⚠ No files to analyze (filter: {extensions})[/yellow]")
            sys.exit(0)

        console.print(f"  Commit: [green]{commit_info.hash[:8]}[/green]")
        console.print(f"  Author: {commit_info.author}")
        console.print(f"  Files changed: {len(changed_files)}")
        console.print(f"  +{commit_info.additions} -{commit_info.deletions}")
        console.print()

        # Generate documentation
        progress.update(task, description="Generating documentation...")
        try:
            doc_type_enum = DocType[doc_type.upper()]
        except KeyError:
            console.print(f"[red]Invalid doc type: {doc_type}[/red]")
            console.print(f"Available types: {', '.join([dt.value for dt in DocType])}")
            sys.exit(1)

        doc = generator.generate_for_commit(
            commit_hash=commit_info.hash,
            changed_files=changed_files,
            commit_message=commit_info.message,
            doc_type=doc_type_enum
        )

        # Create output directory
        output_path = Path(output_dir) / commit_info.hash[:8]
        output_path.mkdir(parents=True, exist_ok=True)

        # Save main documentation
        doc_file = output_path / f"{doc_type}.md"
        with open(doc_file, 'w', encoding='utf-8') as f:
            f.write(doc.content)

        progress.update(task, description="Documentation generated!")
        console.print(f"[green]✓[/green] Documentation saved to: {doc_file}")

        # Generate diagrams if requested
        if with_diagram:
            progress.update(task, description="Generating diagrams...")
            modules = analyzer.analyze_files(changed_files)

            if modules:
                # Generate architecture diagram
                arch_diagram = diagram_gen.generate_architecture_diagram(
                    modules,
                    title=f"Commit {commit_info.hash[:8]} Architecture"
                )

                diagram_file = output_path / "architecture.md"
                with open(diagram_file, 'w', encoding='utf-8') as f:
                    f.write(f"# Architecture Diagram\n\n")
                    f.write(f"**Commit**: {commit_info.hash[:8]}\n\n")
                    f.write(arch_diagram)

                console.print(f"[green]✓[/green] Diagram saved to: {diagram_file}")

                # Generate class diagram if classes exist
                all_classes = []
                for module in modules:
                    all_classes.extend(module.classes)

                if all_classes:
                    class_diagram = diagram_gen.generate_class_diagram(all_classes)
                    class_file = output_path / "classes.md"
                    with open(class_file, 'w', encoding='utf-8') as f:
                        f.write(f"# Class Diagram\n\n")
                        f.write(class_diagram)

                    console.print(f"[green]✓[/green] Class diagram saved to: {class_file}")

    console.print(f"\n[bold green]✨ Done![/bold green] View at: {output_path}\n")


@app.command()
def generate_branch(
    branch_name: Annotated[Optional[str], typer.Argument(help="Branch name (default: current branch)")] = None,
    output_dir: Annotated[str, typer.Option("--output", "-o", help="Output directory")] = ".mem/docs/branches",
    doc_types: Annotated[str, typer.Option("--types", "-t", help="Document types (comma-separated)")] = "readme,api_reference,architecture",
    model: Annotated[str, typer.Option("--model", "-m", help="LLM model to use")] = "gpt-4o-mini",
    with_diagram: Annotated[bool, typer.Option("--diagram", "-d", help="Generate mermaid diagrams")] = True,
    base_branch: Annotated[Optional[str], typer.Option("--base", "-b", help="Base branch for comparison")] = None,
    project_path: Annotated[str, typer.Option("--path", "-p", help="Project path")] = ".",
):
    """
    Generate documentation for a branch.

    Examples:
        mem-docgen generate-branch
        mem-docgen generate-branch feat/new-feature
        mem-docgen generate-branch --types "readme,api_reference"
        mem-docgen generate-branch --base main
    """
    # Initialize components
    analyzer, generator, diagram_gen, git_utils = init_components(project_path, model)

    # Get branch name
    if not branch_name:
        branch_name = git_utils.get_current_branch()
        if not branch_name:
            console.print("[red]✗ Not on a branch. Please specify branch name.[/red]")
            sys.exit(1)

    console.print(f"\n[cyan]📚 Generating documentation for branch '{branch_name}'[/cyan]\n")

    # Parse document types
    try:
        doc_type_list = [DocType[dt.strip().upper()] for dt in doc_types.split(",")]
    except KeyError as e:
        console.print(f"[red]Invalid doc type: {e}[/red]")
        console.print(f"Available types: {', '.join([dt.value for dt in DocType])}")
        sys.exit(1)

    # Create output directory
    output_path = Path(output_dir) / branch_name.replace('/', '-')
    output_path.mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        # Get commit range if base branch specified
        commit_range = None
        if base_branch:
            task = progress.add_task("Analyzing commits...", total=None)
            commits = git_utils.get_branch_commits(branch_name, base_branch)
            console.print(f"  Commits: {len(commits)}")
            console.print(f"  Base branch: {base_branch}")
            console.print()
            commit_range = (base_branch, branch_name)

        # Generate each document type
        for doc_type in doc_type_list:
            task = progress.add_task(f"Generating {doc_type.value}...", total=None)

            doc = generator.generate_for_branch(
                branch_name=branch_name,
                directory=project_path,
                doc_type=doc_type,
                commit_range=commit_range
            )

            # Save document
            filename = f"{doc_type.value}.md"
            doc_file = output_path / filename
            with open(doc_file, 'w', encoding='utf-8') as f:
                f.write(doc.content)

            console.print(f"[green]✓[/green] {doc_type.value.title()} → {doc_file}")

        # Generate diagrams if requested
        if with_diagram:
            progress.add_task("Generating diagrams...", total=None)

            # Analyze project
            modules = analyzer.analyze_directory(project_path)

            # Architecture diagram
            arch_diagram = diagram_gen.generate_architecture_diagram(
                modules,
                title=f"Branch '{branch_name}' Architecture"
            )
            arch_file = output_path / "architecture_diagram.md"
            with open(arch_file, 'w', encoding='utf-8') as f:
                f.write(f"# Architecture Diagram\n\n")
                f.write(arch_diagram)
            console.print(f"[green]✓[/green] Architecture diagram → {arch_file}")

            # Dependency graph
            dependencies = analyzer.get_dependencies(modules)
            if dependencies:
                dep_diagram = diagram_gen.generate_dependency_graph(dependencies)
                dep_file = output_path / "dependencies_diagram.md"
                with open(dep_file, 'w', encoding='utf-8') as f:
                    f.write(f"# Dependency Graph\n\n")
                    f.write(dep_diagram)
                console.print(f"[green]✓[/green] Dependency graph → {dep_file}")

            # Class diagram
            all_classes = []
            for module in modules:
                all_classes.extend(module.classes)

            if all_classes:
                class_diagram = diagram_gen.generate_class_diagram(all_classes[:20])  # Limit to 20
                class_file = output_path / "classes_diagram.md"
                with open(class_file, 'w', encoding='utf-8') as f:
                    f.write(f"# Class Diagram\n\n")
                    f.write(class_diagram)
                console.print(f"[green]✓[/green] Class diagram → {class_file}")

    console.print(f"\n[bold green]✨ Done![/bold green] View at: {output_path}\n")


@app.command()
def generate_diagrams(
    output_dir: Annotated[str, typer.Option("--output", "-o", help="Output directory")] = ".mem/docs/diagrams",
    types: Annotated[str, typer.Option("--types", "-t", help="Diagram types (comma-separated)")] = "architecture,class,dependency",
    project_path: Annotated[str, typer.Option("--path", "-p", help="Project path")] = ".",
):
    """
    Generate Mermaid diagrams for the project.

    Examples:
        mem-docgen generate-diagrams
        mem-docgen generate-diagrams --types "architecture,class"
        mem-docgen generate-diagrams --output ./docs/diagrams
    """
    console.print("\n[cyan]📊 Generating diagrams...[/cyan]\n")

    # Initialize components
    analyzer, _, diagram_gen, _ = init_components(project_path)

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        # Analyze project
        task = progress.add_task("Analyzing code...", total=None)
        modules = analyzer.analyze_directory(project_path)

        if not modules:
            console.print("[yellow]⚠ No modules found to analyze[/yellow]")
            sys.exit(0)

        console.print(f"  Analyzed {len(modules)} modules")
        console.print()

        # Parse diagram types
        diagram_types = [t.strip() for t in types.split(",")]

        # Generate architecture diagram
        if "architecture" in diagram_types:
            progress.update(task, description="Generating architecture diagram...")
            arch_diagram = diagram_gen.generate_architecture_diagram(modules)
            arch_file = output_path / "architecture.md"
            with open(arch_file, 'w', encoding='utf-8') as f:
                f.write("# Architecture Diagram\n\n")
                f.write(arch_diagram)
            console.print(f"[green]✓[/green] Architecture → {arch_file}")

        # Generate class diagram
        if "class" in diagram_types:
            progress.update(task, description="Generating class diagram...")
            all_classes = []
            for module in modules:
                all_classes.extend(module.classes)

            if all_classes:
                class_diagram = diagram_gen.generate_class_diagram(all_classes[:30])
                class_file = output_path / "classes.md"
                with open(class_file, 'w', encoding='utf-8') as f:
                    f.write("# Class Diagram\n\n")
                    f.write(class_diagram)
                console.print(f"[green]✓[/green] Classes → {class_file}")
            else:
                console.print("[yellow]⚠ No classes found[/yellow]")

        # Generate dependency graph
        if "dependency" in diagram_types:
            progress.update(task, description="Generating dependency graph...")
            dependencies = analyzer.get_dependencies(modules)
            if dependencies:
                dep_diagram = diagram_gen.generate_dependency_graph(dependencies)
                dep_file = output_path / "dependencies.md"
                with open(dep_file, 'w', encoding='utf-8') as f:
                    f.write("# Dependency Graph\n\n")
                    f.write(dep_diagram)
                console.print(f"[green]✓[/green] Dependencies → {dep_file}")

    console.print(f"\n[bold green]✨ Done![/bold green] View at: {output_path}\n")


@app.command()
def list_commits(
    branch: Annotated[Optional[str], typer.Argument(help="Branch name (default: current)")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of commits to show")] = 10,
    base_branch: Annotated[Optional[str], typer.Option("--base", "-b", help="Base branch for comparison")] = None,
    project_path: Annotated[str, typer.Option("--path", "-p", help="Project path")] = ".",
):
    """
    List commits in a branch.

    Examples:
        mem-docgen list-commits
        mem-docgen list-commits feat/new-feature
        mem-docgen list-commits --base main --limit 20
    """
    _, _, _, git_utils = init_components(project_path)

    # Get branch name
    if not branch:
        branch = git_utils.get_current_branch()
        if not branch:
            console.print("[red]✗ Not on a branch[/red]")
            sys.exit(1)

    # Get commits
    if base_branch:
        commits = git_utils.get_branch_commits(branch, base_branch)
    else:
        commits = git_utils.get_commits_in_range("HEAD~10", "HEAD")[:limit]

    if not commits:
        console.print("[yellow]⚠ No commits found[/yellow]")
        return

    # Create table
    table = Table(title=f"Commits in '{branch}'")
    table.add_column("Hash", style="cyan", no_wrap=True)
    table.add_column("Author", style="green")
    table.add_column("Date", style="magenta")
    table.add_column("Message", style="white")

    for commit in commits[:limit]:
        table.add_row(
            commit.hash[:8],
            commit.author,
            commit.date.strftime("%Y-%m-%d %H:%M"),
            commit.message.split('\n')[0][:60]
        )

    console.print()
    console.print(table)
    console.print()


@app.command()
def preview(
    docs_dir: Annotated[str, typer.Option("--dir", "-d", help="Documentation directory")] = ".mem/docs",
    port: Annotated[int, typer.Option("--port", "-p", help="Server port")] = 8000,
    host: Annotated[str, typer.Option("--host", "-h", help="Server host")] = "127.0.0.1",
):
    """
    Start web preview server for documentation.

    Examples:
        mem-docgen preview
        mem-docgen preview --port 8080
        mem-docgen preview --dir ./docs
    """
    console.print(f"\n[cyan]🚀 Starting documentation preview server...[/cyan]\n")

    # Check if docs directory exists
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        console.print(f"[yellow]⚠ Documentation directory not found: {docs_path}[/yellow]")
        console.print("[yellow]  Creating directory...[/yellow]")
        docs_path.mkdir(parents=True, exist_ok=True)

    # Start server
    try:
        start_preview_server(docs_dir=docs_dir, host=host, port=port)
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Server error: {e}[/red]")
        sys.exit(1)


@app.command()
def info(
    project_path: Annotated[str, typer.Option("--path", "-p", help="Project path")] = ".",
):
    """
    Show project information and statistics.

    Examples:
        mem-docgen info
        mem-docgen info --path /path/to/project
    """
    console.print("\n[cyan]📊 Project Information[/cyan]\n")

    # Initialize components
    analyzer, _, _, git_utils = init_components(project_path)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        # Analyze project
        task = progress.add_task("Analyzing project...", total=None)
        modules = analyzer.analyze_directory(project_path)

        if not modules:
            console.print("[yellow]⚠ No Python modules found[/yellow]")
            return

        # Generate summary
        summary = analyzer.generate_summary(modules)

        # Get Git info
        current_branch = git_utils.get_current_branch()
        all_branches = git_utils.get_all_branches()

    # Display information
    console.print("[bold]Project Statistics:[/bold]")
    console.print(f"  Files: {summary['total_files']}")
    console.print(f"  Lines of Code: {summary['total_loc']:,}")
    console.print(f"  Functions: {summary['total_functions']}")
    console.print(f"  Classes: {summary['total_classes']}")
    console.print(f"  Methods: {summary['total_methods']}")
    console.print(f"  Avg LOC/File: {summary['avg_loc_per_file']}")
    console.print()

    console.print("[bold]Git Information:[/bold]")
    console.print(f"  Current Branch: {current_branch or 'detached HEAD'}")
    console.print(f"  Total Branches: {len(all_branches)}")
    console.print()

    if summary.get('external_dependencies'):
        console.print("[bold]External Dependencies:[/bold]")
        for dep in summary['external_dependencies'][:10]:
            console.print(f"  • {dep}")
        if len(summary['external_dependencies']) > 10:
            console.print(f"  ... and {len(summary['external_dependencies']) - 10} more")
        console.print()


def main():
    """Main entry point."""
    setup_logging(".")
    app()


if __name__ == "__main__":
    main()
