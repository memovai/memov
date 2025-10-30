"""
Code analyzer for extracting structure and information from source code.

Uses AST parsing to extract:
- Functions, classes, methods
- Parameters, return types, docstrings
- Dependencies and imports
- Call relationships
"""

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class FunctionInfo:
    """Information about a function or method."""
    name: str
    params: List[str]
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    is_async: bool = False
    line_start: int = 0
    line_end: int = 0
    body_preview: str = ""


@dataclass
class ClassInfo:
    """Information about a class."""
    name: str
    bases: List[str]
    methods: List[FunctionInfo]
    attributes: List[str]
    docstring: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    line_start: int = 0
    line_end: int = 0


@dataclass
class ModuleInfo:
    """Information about a module/file."""
    file_path: str
    imports: List[str]
    functions: List[FunctionInfo]
    classes: List[ClassInfo]
    docstring: Optional[str] = None
    dependencies: Set[str] = field(default_factory=set)
    loc: int = 0  # Lines of code


class CodeAnalyzer:
    """Analyzes Python code to extract structural information."""

    def __init__(self, project_path: str):
        """
        Initialize code analyzer.

        Args:
            project_path: Path to the project root
        """
        self.project_path = Path(project_path)

    def analyze_file(self, file_path: str) -> Optional[ModuleInfo]:
        """
        Analyze a single Python file.

        Args:
            file_path: Path to the file to analyze

        Returns:
            ModuleInfo object or None if parsing fails
        """
        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                logger.warning(f"File not found: {file_path}")
                return None

            with open(file_path_obj, 'r', encoding='utf-8') as f:
                code = f.read()

            # Parse AST
            tree = ast.parse(code, filename=str(file_path_obj))

            # Extract information
            module_info = ModuleInfo(
                file_path=str(file_path_obj),
                imports=[],
                functions=[],
                classes=[],
                docstring=ast.get_docstring(tree),
                loc=len(code.splitlines())
            )

            # Visit AST nodes
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_info.imports.append(alias.name)
                        module_info.dependencies.add(alias.name.split('.')[0])

                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module_info.imports.append(node.module)
                        module_info.dependencies.add(node.module.split('.')[0])

            # Extract top-level functions and classes
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    func_info = self._extract_function(node)
                    module_info.functions.append(func_info)

                elif isinstance(node, ast.ClassDef):
                    class_info = self._extract_class(node)
                    module_info.classes.append(class_info)

            return module_info

        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {e}")
            return None

    def analyze_directory(
        self,
        directory: str,
        extensions: List[str] = None,
        exclude_patterns: List[str] = None
    ) -> List[ModuleInfo]:
        """
        Analyze all Python files in a directory.

        Args:
            directory: Directory to analyze
            extensions: File extensions to include (default: ['.py'])
            exclude_patterns: Patterns to exclude (e.g., ['test_', '__pycache__'])

        Returns:
            List of ModuleInfo objects
        """
        if extensions is None:
            extensions = ['.py']
        if exclude_patterns is None:
            exclude_patterns = ['__pycache__', '.git', '.venv', 'venv', 'node_modules']

        directory_path = Path(directory)
        modules = []

        for ext in extensions:
            for file_path in directory_path.rglob(f'*{ext}'):
                # Check exclude patterns
                if any(pattern in str(file_path) for pattern in exclude_patterns):
                    continue

                module_info = self.analyze_file(str(file_path))
                if module_info:
                    modules.append(module_info)

        return modules

    def analyze_files(self, file_paths: List[str]) -> List[ModuleInfo]:
        """
        Analyze a list of files.

        Args:
            file_paths: List of file paths to analyze

        Returns:
            List of ModuleInfo objects
        """
        modules = []
        for file_path in file_paths:
            module_info = self.analyze_file(file_path)
            if module_info:
                modules.append(module_info)
        return modules

    def _extract_function(self, node: ast.FunctionDef) -> FunctionInfo:
        """Extract information from a function/method node."""
        # Extract parameters
        params = []
        for arg in node.args.args:
            param_str = arg.arg
            if arg.annotation:
                param_str += f": {ast.unparse(arg.annotation)}"
            params.append(param_str)

        # Extract return type
        return_type = None
        if node.returns:
            return_type = ast.unparse(node.returns)

        # Extract decorators
        decorators = [ast.unparse(dec) for dec in node.decorator_list]

        # Get body preview (first few lines)
        body_lines = []
        for stmt in node.body[:3]:  # First 3 statements
            try:
                body_lines.append(ast.unparse(stmt))
            except:
                pass
        body_preview = '\n'.join(body_lines)

        return FunctionInfo(
            name=node.name,
            params=params,
            return_type=return_type,
            docstring=ast.get_docstring(node),
            decorators=decorators,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            body_preview=body_preview
        )

    def _extract_class(self, node: ast.ClassDef) -> ClassInfo:
        """Extract information from a class node."""
        # Extract base classes
        bases = [ast.unparse(base) for base in node.bases]

        # Extract methods
        methods = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._extract_function(item))

        # Extract attributes (simple assignments)
        attributes = []
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                attr_name = item.target.id
                if item.annotation:
                    attr_name += f": {ast.unparse(item.annotation)}"
                attributes.append(attr_name)
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        attributes.append(target.id)

        # Extract decorators
        decorators = [ast.unparse(dec) for dec in node.decorator_list]

        return ClassInfo(
            name=node.name,
            bases=bases,
            methods=methods,
            attributes=attributes,
            docstring=ast.get_docstring(node),
            decorators=decorators,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno
        )

    def get_dependencies(self, modules: List[ModuleInfo]) -> Dict[str, Set[str]]:
        """
        Build dependency graph from modules.

        Args:
            modules: List of analyzed modules

        Returns:
            Dictionary mapping file paths to their dependencies
        """
        dependencies = {}

        for module in modules:
            deps = set()
            for imp in module.imports:
                # Check if import is internal (within project)
                imp_path = self.project_path / (imp.replace('.', '/') + '.py')
                if imp_path.exists():
                    deps.add(str(imp_path))
            dependencies[module.file_path] = deps

        return dependencies

    def get_call_graph(self, modules: List[ModuleInfo]) -> Dict[str, List[str]]:
        """
        Build function call graph (simplified).

        Args:
            modules: List of analyzed modules

        Returns:
            Dictionary mapping function names to called functions
        """
        call_graph = {}

        # Collect all function names
        all_functions = set()
        for module in modules:
            for func in module.functions:
                all_functions.add(func.name)
            for cls in module.classes:
                for method in cls.methods:
                    all_functions.add(f"{cls.name}.{method.name}")

        # Analyze function bodies for calls
        for module in modules:
            for func in module.functions:
                calls = self._find_function_calls(func.body_preview, all_functions)
                if calls:
                    call_graph[func.name] = calls

            for cls in module.classes:
                for method in cls.methods:
                    calls = self._find_function_calls(method.body_preview, all_functions)
                    if calls:
                        call_graph[f"{cls.name}.{method.name}"] = calls

        return call_graph

    def _find_function_calls(self, code: str, known_functions: Set[str]) -> List[str]:
        """Find function calls in code snippet."""
        calls = []
        for func_name in known_functions:
            # Simple pattern matching for function calls
            if re.search(rf'\b{re.escape(func_name)}\s*\(', code):
                calls.append(func_name)
        return calls

    def generate_summary(self, modules: List[ModuleInfo]) -> Dict[str, Any]:
        """
        Generate summary statistics from analyzed modules.

        Args:
            modules: List of analyzed modules

        Returns:
            Summary dictionary
        """
        total_loc = sum(m.loc for m in modules)
        total_functions = sum(len(m.functions) for m in modules)
        total_classes = sum(len(m.classes) for m in modules)
        total_methods = sum(
            sum(len(cls.methods) for cls in m.classes)
            for m in modules
        )

        # Count dependencies
        all_deps = set()
        for module in modules:
            all_deps.update(module.dependencies)

        # Find entry points (files with main or __main__)
        entry_points = []
        for module in modules:
            if module.docstring and 'entry point' in module.docstring.lower():
                entry_points.append(module.file_path)
            for func in module.functions:
                if func.name == 'main':
                    entry_points.append(module.file_path)

        return {
            'total_files': len(modules),
            'total_loc': total_loc,
            'total_functions': total_functions,
            'total_classes': total_classes,
            'total_methods': total_methods,
            'external_dependencies': sorted(all_deps),
            'entry_points': entry_points,
            'avg_loc_per_file': total_loc // len(modules) if modules else 0,
        }
