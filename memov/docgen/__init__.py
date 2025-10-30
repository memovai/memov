"""
Documentation generation module for code analysis and documentation.

This module provides tools for:
- Code parsing and analysis
- Document generation using LLM
- Mermaid diagram generation
- Multi-level documentation (commit, branch, repository)
- Git integration for commit/branch analysis
- Web preview server
"""

from .code_analyzer import CodeAnalyzer, ClassInfo, FunctionInfo, ModuleInfo
from .diagram_generator import DiagramGenerator, DiagramType
from .doc_generator import DocType, DocumentGenerator, DocumentStructure, GeneratedDocument
from .git_utils import CommitInfo, GitUtils

# Preview server is optional (requires starlette)
try:
    from .preview_server import PreviewServer, start_preview_server
    _HAS_PREVIEW_SERVER = True
except ImportError:
    PreviewServer = None
    start_preview_server = None
    _HAS_PREVIEW_SERVER = False

__all__ = [
    # Code Analysis
    "CodeAnalyzer",
    "ModuleInfo",
    "ClassInfo",
    "FunctionInfo",
    # Document Generation
    "DocumentGenerator",
    "DocumentStructure",
    "GeneratedDocument",
    "DocType",
    # Diagram Generation
    "DiagramGenerator",
    "DiagramType",
    # Git Utilities
    "GitUtils",
    "CommitInfo",
    # Preview Server (optional)
    "PreviewServer",
    "start_preview_server",
]
