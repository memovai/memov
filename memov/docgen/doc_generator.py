"""
Document generator using LLM to create comprehensive documentation.

Supports:
- Multiple documentation structures (README, API, Tutorial, etc.)
- Commit-level and branch-level documentation
- Integration with code analysis
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from memov.debugging.llm_client import LLMClient
from memov.docgen.code_analyzer import CodeAnalyzer, ModuleInfo

logger = logging.getLogger(__name__)


class DocType(Enum):
    """Types of documentation that can be generated."""
    README = "readme"
    API_REFERENCE = "api_reference"
    ARCHITECTURE = "architecture"
    TUTORIAL = "tutorial"
    CHANGELOG = "changelog"
    FEATURE = "feature"


@dataclass
class DocumentStructure:
    """Template structure for generated documentation."""
    doc_type: DocType
    sections: List[str]
    templates: Dict[str, str] = field(default_factory=dict)

    @staticmethod
    def get_readme_structure() -> 'DocumentStructure':
        """Get structure for README documentation."""
        return DocumentStructure(
            doc_type=DocType.README,
            sections=[
                "title",
                "overview",
                "features",
                "installation",
                "quick_start",
                "usage",
                "api_overview",
                "architecture",
                "contributing",
                "license"
            ],
            templates={
                "title": "# {project_name}\n\n{description}",
                "overview": "## Overview\n\n{overview_text}",
                "features": "## Features\n\n{feature_list}",
                "installation": "## Installation\n\n```bash\n{install_commands}\n```",
                "quick_start": "## Quick Start\n\n{quick_start_example}",
                "usage": "## Usage\n\n{usage_examples}",
                "api_overview": "## API Overview\n\n{api_summary}",
                "architecture": "## Architecture\n\n{architecture_diagram}",
            }
        )

    @staticmethod
    def get_api_structure() -> 'DocumentStructure':
        """Get structure for API reference documentation."""
        return DocumentStructure(
            doc_type=DocType.API_REFERENCE,
            sections=[
                "title",
                "overview",
                "modules",
                "classes",
                "functions",
                "examples"
            ],
            templates={
                "title": "# API Reference\n\n",
                "modules": "## Modules\n\n{module_list}",
                "classes": "## Classes\n\n{class_descriptions}",
                "functions": "## Functions\n\n{function_descriptions}",
            }
        )

    @staticmethod
    def get_feature_structure() -> 'DocumentStructure':
        """Get structure for feature documentation."""
        return DocumentStructure(
            doc_type=DocType.FEATURE,
            sections=[
                "title",
                "overview",
                "motivation",
                "design",
                "implementation",
                "usage",
                "testing",
                "related_changes"
            ],
            templates={
                "title": "# Feature: {feature_name}\n\n",
                "overview": "## Overview\n\n{overview_text}",
                "motivation": "## Motivation\n\n{motivation_text}",
                "design": "## Design\n\n{design_details}",
                "implementation": "## Implementation\n\n{implementation_details}",
                "usage": "## Usage\n\n{usage_examples}",
            }
        )

    @staticmethod
    def get_architecture_structure() -> 'DocumentStructure':
        """Get structure for architecture documentation."""
        return DocumentStructure(
            doc_type=DocType.ARCHITECTURE,
            sections=[
                "title",
                "overview",
                "components",
                "data_flow",
                "diagrams",
                "design_patterns",
                "dependencies"
            ],
            templates={
                "title": "# Architecture Documentation\n\n",
                "overview": "## Overview\n\n{overview_text}",
                "components": "## Components\n\n{component_list}",
                "data_flow": "## Data Flow\n\n{data_flow_diagram}",
                "diagrams": "## Architecture Diagrams\n\n{diagrams}",
            }
        )


@dataclass
class GeneratedDocument:
    """A generated documentation document."""
    doc_type: DocType
    title: str
    content: str
    metadata: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)


class DocumentGenerator:
    """Generates documentation using LLM and code analysis."""

    def __init__(
        self,
        code_analyzer: CodeAnalyzer,
        llm_client: Optional[LLMClient] = None,
        model: str = "gpt-4o-mini"
    ):
        """
        Initialize document generator.

        Args:
            code_analyzer: CodeAnalyzer instance
            llm_client: LLMClient instance (optional)
            model: Model to use for generation
        """
        self.code_analyzer = code_analyzer
        self.model = model

        if llm_client:
            self.llm_client = llm_client
        else:
            try:
                self.llm_client = LLMClient(models=[model])
            except ImportError:
                logger.warning("LiteLLM not available. Using fallback mode.")
                self.llm_client = None

    def generate_for_commit(
        self,
        commit_hash: str,
        changed_files: List[str],
        commit_message: str,
        doc_type: DocType = DocType.FEATURE
    ) -> GeneratedDocument:
        """
        Generate documentation for a specific commit.

        Args:
            commit_hash: Commit hash
            changed_files: List of files changed in the commit
            commit_message: Commit message
            doc_type: Type of documentation to generate

        Returns:
            GeneratedDocument object
        """
        logger.info(f"Generating {doc_type.value} documentation for commit {commit_hash[:8]}")

        # Analyze changed files
        modules = self.code_analyzer.analyze_files(changed_files)

        # Get appropriate structure
        structure = self._get_structure(doc_type)

        # Build context for LLM
        context = self._build_commit_context(
            commit_hash=commit_hash,
            commit_message=commit_message,
            modules=modules,
            changed_files=changed_files
        )

        # Generate documentation content
        content = self._generate_content(structure, context)

        return GeneratedDocument(
            doc_type=doc_type,
            title=f"Commit {commit_hash[:8]}: {commit_message.splitlines()[0][:50]}",
            content=content,
            metadata={
                'commit_hash': commit_hash,
                'commit_message': commit_message,
                'changed_files': changed_files,
                'num_files': len(changed_files),
            }
        )

    def generate_for_branch(
        self,
        branch_name: str,
        directory: str,
        doc_type: DocType = DocType.README,
        commit_range: Optional[tuple[str, str]] = None
    ) -> GeneratedDocument:
        """
        Generate documentation for a branch.

        Args:
            branch_name: Branch name
            directory: Directory to analyze
            doc_type: Type of documentation to generate
            commit_range: Optional tuple of (start_commit, end_commit)

        Returns:
            GeneratedDocument object
        """
        logger.info(f"Generating {doc_type.value} documentation for branch {branch_name}")

        # Analyze all files in directory
        modules = self.code_analyzer.analyze_directory(directory)

        # Get appropriate structure
        structure = self._get_structure(doc_type)

        # Build context for LLM
        context = self._build_branch_context(
            branch_name=branch_name,
            modules=modules,
            commit_range=commit_range
        )

        # Generate documentation content
        content = self._generate_content(structure, context)

        return GeneratedDocument(
            doc_type=doc_type,
            title=f"Branch: {branch_name}",
            content=content,
            metadata={
                'branch_name': branch_name,
                'num_modules': len(modules),
                'total_loc': sum(m.loc for m in modules),
            }
        )

    def generate_for_repository(
        self,
        directory: str,
        doc_types: List[DocType] = None
    ) -> List[GeneratedDocument]:
        """
        Generate comprehensive documentation for entire repository.

        Args:
            directory: Repository directory
            doc_types: List of documentation types to generate

        Returns:
            List of GeneratedDocument objects
        """
        if doc_types is None:
            doc_types = [DocType.README, DocType.API_REFERENCE, DocType.ARCHITECTURE]

        logger.info(f"Generating repository documentation: {doc_types}")

        # Analyze entire repository
        modules = self.code_analyzer.analyze_directory(directory)

        documents = []
        for doc_type in doc_types:
            doc = self.generate_for_branch(
                branch_name="main",
                directory=directory,
                doc_type=doc_type
            )
            documents.append(doc)

        return documents

    def _get_structure(self, doc_type: DocType) -> DocumentStructure:
        """Get document structure for given type."""
        structure_map = {
            DocType.README: DocumentStructure.get_readme_structure(),
            DocType.API_REFERENCE: DocumentStructure.get_api_structure(),
            DocType.FEATURE: DocumentStructure.get_feature_structure(),
            DocType.ARCHITECTURE: DocumentStructure.get_architecture_structure(),
        }
        return structure_map.get(doc_type, DocumentStructure.get_readme_structure())

    def _build_commit_context(
        self,
        commit_hash: str,
        commit_message: str,
        modules: List[ModuleInfo],
        changed_files: List[str]
    ) -> Dict[str, Any]:
        """Build context for commit-level documentation."""
        # Extract code information
        functions = []
        classes = []
        for module in modules:
            functions.extend(module.functions)
            classes.extend(module.classes)

        # Build context dictionary
        context = {
            'commit_hash': commit_hash,
            'commit_message': commit_message,
            'changed_files': changed_files,
            'num_functions': len(functions),
            'num_classes': len(classes),
            'function_names': [f.name for f in functions],
            'class_names': [c.name for c in classes],
            'modules': modules,
        }

        # Add detailed function/class info
        if functions:
            context['main_functions'] = [
                {
                    'name': f.name,
                    'params': f.params,
                    'return_type': f.return_type,
                    'docstring': f.docstring
                }
                for f in functions[:5]  # First 5 functions
            ]

        if classes:
            context['main_classes'] = [
                {
                    'name': c.name,
                    'methods': [m.name for m in c.methods],
                    'docstring': c.docstring
                }
                for c in classes[:5]  # First 5 classes
            ]

        return context

    def _build_branch_context(
        self,
        branch_name: str,
        modules: List[ModuleInfo],
        commit_range: Optional[tuple[str, str]] = None
    ) -> Dict[str, Any]:
        """Build context for branch-level documentation."""
        # Generate summary
        summary = self.code_analyzer.generate_summary(modules)

        # Build dependency graph
        dependencies = self.code_analyzer.get_dependencies(modules)

        # Extract all functions and classes
        all_functions = []
        all_classes = []
        for module in modules:
            all_functions.extend(module.functions)
            all_classes.extend(module.classes)

        context = {
            'branch_name': branch_name,
            'summary': summary,
            'dependencies': dependencies,
            'modules': modules,
            'all_functions': all_functions,
            'all_classes': all_classes,
            'commit_range': commit_range,
        }

        return context

    def _generate_content(
        self,
        structure: DocumentStructure,
        context: Dict[str, Any]
    ) -> str:
        """Generate documentation content using LLM."""
        if not self.llm_client:
            # Fallback: generate basic structure without LLM
            return self._generate_fallback_content(structure, context)

        # Build prompt for LLM
        prompt = self._build_prompt(structure, context)

        system_prompt = """You are an expert technical writer and software documentation specialist.
Your task is to generate clear, comprehensive, and well-structured documentation based on code analysis.

Guidelines:
- Write in clear, concise language
- Include code examples where appropriate
- Use proper markdown formatting
- Structure information logically
- Focus on practical usage
- Explain complex concepts simply"""

        try:
            # Query LLM
            response = self.llm_client.query_single(
                model=self.model,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=4000
            )

            if response.get('error'):
                logger.error(f"LLM error: {response['error']}")
                return self._generate_fallback_content(structure, context)

            return response.get('content', '')

        except Exception as e:
            logger.error(f"Error generating content: {e}")
            return self._generate_fallback_content(structure, context)

    def _build_prompt(
        self,
        structure: DocumentStructure,
        context: Dict[str, Any]
    ) -> str:
        """Build prompt for LLM based on structure and context."""
        lines = []

        lines.append(f"Generate {structure.doc_type.value} documentation with the following structure:")
        lines.append("")
        lines.append("Required sections:")
        for section in structure.sections:
            lines.append(f"- {section}")
        lines.append("")

        lines.append("Code Analysis Context:")
        lines.append("")

        # Add relevant context based on what's available
        if 'commit_message' in context:
            lines.append(f"Commit Message: {context['commit_message']}")
            lines.append(f"Changed Files: {', '.join(context.get('changed_files', []))}")
            lines.append("")

        if 'branch_name' in context:
            lines.append(f"Branch: {context['branch_name']}")
            lines.append("")

        if 'summary' in context:
            summary = context['summary']
            lines.append("Project Summary:")
            lines.append(f"- Total Files: {summary.get('total_files', 0)}")
            lines.append(f"- Total LOC: {summary.get('total_loc', 0)}")
            lines.append(f"- Functions: {summary.get('total_functions', 0)}")
            lines.append(f"- Classes: {summary.get('total_classes', 0)}")
            lines.append("")

        # Add function details
        if 'main_functions' in context:
            lines.append("Key Functions:")
            for func in context['main_functions'][:3]:
                lines.append(f"- {func['name']}({', '.join(func['params'])})")
                if func.get('docstring'):
                    lines.append(f"  {func['docstring'][:100]}")
            lines.append("")

        # Add class details
        if 'main_classes' in context:
            lines.append("Key Classes:")
            for cls in context['main_classes'][:3]:
                lines.append(f"- {cls['name']}")
                if cls.get('methods'):
                    lines.append(f"  Methods: {', '.join(cls['methods'][:5])}")
            lines.append("")

        lines.append("Please generate comprehensive documentation following the structure above.")
        lines.append("Use proper markdown formatting including headers, code blocks, and lists.")

        return "\n".join(lines)

    def _generate_fallback_content(
        self,
        structure: DocumentStructure,
        context: Dict[str, Any]
    ) -> str:
        """Generate basic documentation without LLM."""
        lines = []

        # Title
        if 'commit_message' in context:
            title = f"# Commit Documentation\n\n**Commit**: {context['commit_hash'][:8]}\n"
            title += f"**Message**: {context['commit_message']}\n"
            lines.append(title)
        elif 'branch_name' in context:
            lines.append(f"# {structure.doc_type.value.replace('_', ' ').title()}\n")
            lines.append(f"**Branch**: {context['branch_name']}\n")

        # Summary
        if 'summary' in context:
            summary = context['summary']
            lines.append("## Summary\n")
            lines.append(f"- Files: {summary.get('total_files', 0)}")
            lines.append(f"- Lines of Code: {summary.get('total_loc', 0)}")
            lines.append(f"- Functions: {summary.get('total_functions', 0)}")
            lines.append(f"- Classes: {summary.get('total_classes', 0)}")
            lines.append("")

        # Functions
        if 'main_functions' in context:
            lines.append("## Functions\n")
            for func in context['main_functions'][:10]:
                lines.append(f"### `{func['name']}`\n")
                if func.get('params'):
                    lines.append(f"**Parameters**: `{', '.join(func['params'])}`\n")
                if func.get('return_type'):
                    lines.append(f"**Returns**: `{func['return_type']}`\n")
                if func.get('docstring'):
                    lines.append(f"{func['docstring']}\n")
                lines.append("")

        # Classes
        if 'main_classes' in context:
            lines.append("## Classes\n")
            for cls in context['main_classes'][:10]:
                lines.append(f"### `{cls['name']}`\n")
                if cls.get('methods'):
                    lines.append(f"**Methods**: {', '.join(cls['methods'])}\n")
                if cls.get('docstring'):
                    lines.append(f"{cls['docstring']}\n")
                lines.append("")

        return "\n".join(lines)
