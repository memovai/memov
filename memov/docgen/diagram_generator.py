"""
Mermaid diagram generator for visualizing code structure and flow.

Generates:
- Architecture diagrams
- Class diagrams
- Sequence diagrams
- Flow charts
- Dependency graphs
"""

import logging
from enum import Enum
from typing import Dict, List, Optional, Set

from memov.debugging.llm_client import LLMClient
from memov.docgen.code_analyzer import ClassInfo, ModuleInfo

logger = logging.getLogger(__name__)


class DiagramType(Enum):
    """Types of Mermaid diagrams."""
    FLOWCHART = "flowchart"
    CLASS_DIAGRAM = "classDiagram"
    SEQUENCE = "sequenceDiagram"
    ER_DIAGRAM = "erDiagram"
    STATE = "stateDiagram"
    GRAPH = "graph"


class DiagramGenerator:
    """Generates Mermaid diagrams from code analysis."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        """
        Initialize diagram generator.

        Args:
            llm_client: Optional LLM client for intelligent diagram generation
        """
        self.llm_client = llm_client

    def generate_architecture_diagram(
        self,
        modules: List[ModuleInfo],
        title: str = "System Architecture"
    ) -> str:
        """
        Generate architecture diagram showing module relationships.

        Args:
            modules: List of analyzed modules
            title: Diagram title

        Returns:
            Mermaid diagram as string
        """
        lines = []
        lines.append("```mermaid")
        lines.append("graph TB")
        lines.append(f"    title[\"{title}\"]")
        lines.append("")

        # Group modules by directory
        module_groups: Dict[str, List[ModuleInfo]] = {}
        for module in modules:
            # Get parent directory
            parts = module.file_path.split('/')
            if len(parts) > 1:
                group = parts[-2]
            else:
                group = "root"

            if group not in module_groups:
                module_groups[group] = []
            module_groups[group].append(module)

        # Create subgraphs for each directory
        node_id = 0
        node_map = {}

        for group_name, group_modules in module_groups.items():
            lines.append(f"    subgraph {group_name}[\"{group_name}\"]")

            for module in group_modules:
                module_name = module.file_path.split('/')[-1].replace('.py', '')
                node_id += 1
                node_name = f"mod{node_id}"
                node_map[module.file_path] = node_name

                # Count elements
                num_classes = len(module.classes)
                num_functions = len(module.functions)
                label = f"{module_name}\\n{num_classes}C {num_functions}F"

                lines.append(f"        {node_name}[\"{label}\"]")

            lines.append("    end")
            lines.append("")

        # Add dependencies
        lines.append("    %% Dependencies")
        for module in modules:
            if module.file_path not in node_map:
                continue

            source_node = node_map[module.file_path]

            for dep in module.dependencies:
                # Try to find matching module
                for other in modules:
                    if dep in other.file_path and other.file_path in node_map:
                        target_node = node_map[other.file_path]
                        lines.append(f"    {source_node} --> {target_node}")

        lines.append("")
        lines.append("    style title fill:#f9f,stroke:#333,stroke-width:2px")
        lines.append("```")

        return "\n".join(lines)

    def generate_class_diagram(
        self,
        classes: List[ClassInfo],
        title: str = "Class Diagram"
    ) -> str:
        """
        Generate UML class diagram.

        Args:
            classes: List of class information
            title: Diagram title

        Returns:
            Mermaid diagram as string
        """
        lines = []
        lines.append("```mermaid")
        lines.append("classDiagram")
        lines.append(f"    %% {title}")
        lines.append("")

        for cls in classes:
            # Add class
            lines.append(f"    class {cls.name} {{")

            # Add attributes
            if cls.attributes:
                for attr in cls.attributes[:10]:  # Limit to 10
                    lines.append(f"        +{attr}")

            # Add methods
            if cls.methods:
                for method in cls.methods[:10]:  # Limit to 10
                    params = ", ".join(method.params) if method.params else ""
                    return_type = f" {method.return_type}" if method.return_type else ""
                    lines.append(f"        +{method.name}({params}){return_type}")

            lines.append("    }")
            lines.append("")

            # Add inheritance relationships
            if cls.bases:
                for base in cls.bases:
                    # Clean up base name
                    base_name = base.split('.')[-1].split('(')[0]
                    lines.append(f"    {base_name} <|-- {cls.name}")

        lines.append("```")

        return "\n".join(lines)

    def generate_dependency_graph(
        self,
        dependencies: Dict[str, Set[str]],
        title: str = "Dependency Graph"
    ) -> str:
        """
        Generate dependency graph showing module dependencies.

        Args:
            dependencies: Dictionary mapping modules to their dependencies
            title: Diagram title

        Returns:
            Mermaid diagram as string
        """
        lines = []
        lines.append("```mermaid")
        lines.append("graph LR")
        lines.append(f"    title[\"{title}\"]")
        lines.append("")

        # Create nodes
        all_modules = set(dependencies.keys())
        for deps in dependencies.values():
            all_modules.update(deps)

        node_map = {}
        for idx, module in enumerate(sorted(all_modules)):
            module_name = module.split('/')[-1].replace('.py', '')
            node_id = f"M{idx}"
            node_map[module] = node_id
            lines.append(f"    {node_id}[\"{module_name}\"]")

        lines.append("")

        # Add dependencies
        for source, deps in dependencies.items():
            if source not in node_map:
                continue

            source_id = node_map[source]
            for dep in deps:
                if dep in node_map:
                    target_id = node_map[dep]
                    lines.append(f"    {source_id} --> {target_id}")

        lines.append("```")

        return "\n".join(lines)

    def generate_flowchart(
        self,
        steps: List[str],
        title: str = "Process Flow"
    ) -> str:
        """
        Generate flowchart from list of steps.

        Args:
            steps: List of process steps
            title: Diagram title

        Returns:
            Mermaid diagram as string
        """
        lines = []
        lines.append("```mermaid")
        lines.append("flowchart TD")
        lines.append(f"    A[Start: {title}]")

        for idx, step in enumerate(steps):
            current = chr(66 + idx)  # B, C, D, ...
            next_node = chr(67 + idx) if idx < len(steps) - 1 else "Z"

            # Determine node shape based on content
            if "decision" in step.lower() or "if" in step.lower() or "?" in step:
                lines.append(f"    {current}{{{step}}}")
            elif "end" in step.lower() or "return" in step.lower():
                lines.append(f"    {current}([{step}])")
            else:
                lines.append(f"    {current}[{step}]")

            # Add connection
            if idx < len(steps) - 1:
                lines.append(f"    {current} --> {next_node}")
            else:
                lines.append(f"    {current} --> Z[End]")

        lines.append("```")

        return "\n".join(lines)

    def generate_sequence_diagram(
        self,
        interactions: List[tuple[str, str, str]],
        title: str = "Sequence Diagram"
    ) -> str:
        """
        Generate sequence diagram showing interactions.

        Args:
            interactions: List of (actor1, actor2, message) tuples
            title: Diagram title

        Returns:
            Mermaid diagram as string
        """
        lines = []
        lines.append("```mermaid")
        lines.append("sequenceDiagram")
        lines.append(f"    title {title}")
        lines.append("")

        # Collect all actors
        actors = set()
        for actor1, actor2, _ in interactions:
            actors.add(actor1)
            actors.add(actor2)

        # Declare participants
        for actor in sorted(actors):
            lines.append(f"    participant {actor}")

        lines.append("")

        # Add interactions
        for actor1, actor2, message in interactions:
            lines.append(f"    {actor1}->>+{actor2}: {message}")

        lines.append("```")

        return "\n".join(lines)

    def generate_with_llm(
        self,
        diagram_type: DiagramType,
        context: Dict,
        prompt: Optional[str] = None
    ) -> str:
        """
        Generate diagram using LLM for intelligent interpretation.

        Args:
            diagram_type: Type of diagram to generate
            context: Context information for diagram generation
            prompt: Optional custom prompt

        Returns:
            Mermaid diagram as string
        """
        if not self.llm_client:
            raise ValueError("LLM client required for intelligent diagram generation")

        if prompt is None:
            prompt = self._build_diagram_prompt(diagram_type, context)

        system_prompt = """You are an expert in creating Mermaid diagrams for software documentation.
Generate clear, well-structured Mermaid diagrams based on the provided information.

Guidelines:
- Use proper Mermaid syntax
- Keep diagrams clear and readable
- Limit complexity (max 20 nodes for graphs)
- Use appropriate node shapes and styles
- Add clear labels and titles
- Ensure diagram is properly formatted with ```mermaid markers"""

        try:
            response = self.llm_client.query_single(
                model=self.llm_client.models[0],
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=2000
            )

            if response.get('error'):
                logger.error(f"LLM error: {response['error']}")
                return self._generate_fallback_diagram(diagram_type, context)

            content = response.get('content', '')

            # Extract mermaid code block if present
            if '```mermaid' in content:
                return content
            elif '```' in content:
                # Wrap in mermaid block
                code = content.split('```')[1]
                return f"```mermaid\n{code}\n```"
            else:
                return f"```mermaid\n{content}\n```"

        except Exception as e:
            logger.error(f"Error generating diagram with LLM: {e}")
            return self._generate_fallback_diagram(diagram_type, context)

    def _build_diagram_prompt(
        self,
        diagram_type: DiagramType,
        context: Dict
    ) -> str:
        """Build prompt for LLM diagram generation."""
        lines = []

        lines.append(f"Generate a {diagram_type.value} Mermaid diagram based on the following information:")
        lines.append("")

        if 'modules' in context:
            modules = context['modules']
            lines.append(f"Number of modules: {len(modules)}")
            lines.append("Module names:")
            for module in modules[:10]:
                name = module.file_path.split('/')[-1]
                lines.append(f"- {name} ({len(module.functions)}F, {len(module.classes)}C)")
            lines.append("")

        if 'classes' in context:
            classes = context['classes']
            lines.append(f"Number of classes: {len(classes)}")
            lines.append("Class names:")
            for cls in classes[:10]:
                lines.append(f"- {cls.name} (methods: {', '.join([m.name for m in cls.methods[:3]])})")
            lines.append("")

        if 'summary' in context:
            summary = context['summary']
            lines.append("Project summary:")
            for key, value in summary.items():
                lines.append(f"- {key}: {value}")
            lines.append("")

        lines.append("Please generate a clear and well-structured Mermaid diagram.")
        lines.append("Include the ```mermaid code block markers in your response.")

        return "\n".join(lines)

    def _generate_fallback_diagram(
        self,
        diagram_type: DiagramType,
        context: Dict
    ) -> str:
        """Generate basic diagram as fallback."""
        if diagram_type == DiagramType.CLASS_DIAGRAM and 'classes' in context:
            return self.generate_class_diagram(context['classes'])
        elif diagram_type == DiagramType.GRAPH and 'modules' in context:
            return self.generate_architecture_diagram(context['modules'])
        else:
            # Generic flowchart
            return self.generate_flowchart(
                steps=["Start", "Process", "Decision?", "End"],
                title="Process Flow"
            )
