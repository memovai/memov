"""
Web server for previewing generated documentation with Mermaid support.

Features:
- Markdown rendering
- Mermaid diagram rendering
- Syntax highlighting
- File browser navigation
- Responsive design
"""

import logging
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route
from starlette.staticfiles import StaticFiles
import uvicorn

logger = logging.getLogger(__name__)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>

    <!-- Mermaid JS -->
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            securityLevel: 'loose',
        }});
    </script>

    <!-- Marked.js for Markdown rendering -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>

    <!-- Highlight.js for syntax highlighting -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/styles/github.min.css">
    <script src="https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/es/highlight.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/es/languages/python.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/es/languages/javascript.min.js"></script>

    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
                'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }}

        .container {{
            display: flex;
            min-height: 100vh;
        }}

        .sidebar {{
            width: 280px;
            background: #fff;
            border-right: 1px solid #e1e4e8;
            overflow-y: auto;
            position: fixed;
            height: 100vh;
        }}

        .sidebar-header {{
            padding: 20px;
            background: #0366d6;
            color: white;
        }}

        .sidebar-header h1 {{
            font-size: 20px;
            font-weight: 600;
        }}

        .nav-list {{
            list-style: none;
            padding: 10px 0;
        }}

        .nav-item {{
            padding: 8px 20px;
            cursor: pointer;
            transition: background 0.2s;
        }}

        .nav-item:hover {{
            background: #f6f8fa;
        }}

        .nav-item a {{
            color: #0366d6;
            text-decoration: none;
            display: block;
        }}

        .nav-item.active {{
            background: #e1ecf7;
            border-left: 3px solid #0366d6;
        }}

        .main-content {{
            flex: 1;
            margin-left: 280px;
            padding: 40px;
            max-width: 1200px;
        }}

        .content-card {{
            background: white;
            border-radius: 8px;
            padding: 40px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}

        /* Markdown Styles */
        .markdown-body {{
            font-size: 16px;
        }}

        .markdown-body h1 {{
            font-size: 32px;
            font-weight: 600;
            margin: 24px 0 16px;
            padding-bottom: 8px;
            border-bottom: 1px solid #e1e4e8;
        }}

        .markdown-body h2 {{
            font-size: 24px;
            font-weight: 600;
            margin: 24px 0 16px;
            padding-bottom: 8px;
            border-bottom: 1px solid #e1e4e8;
        }}

        .markdown-body h3 {{
            font-size: 20px;
            font-weight: 600;
            margin: 16px 0;
        }}

        .markdown-body p {{
            margin: 16px 0;
        }}

        .markdown-body ul, .markdown-body ol {{
            margin: 16px 0;
            padding-left: 32px;
        }}

        .markdown-body li {{
            margin: 8px 0;
        }}

        .markdown-body pre {{
            background: #f6f8fa;
            border-radius: 6px;
            padding: 16px;
            overflow-x: auto;
            margin: 16px 0;
        }}

        .markdown-body code {{
            background: #f6f8fa;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 14px;
        }}

        .markdown-body pre code {{
            background: transparent;
            padding: 0;
        }}

        .markdown-body blockquote {{
            border-left: 4px solid #0366d6;
            padding-left: 16px;
            margin: 16px 0;
            color: #6a737d;
        }}

        .markdown-body table {{
            border-collapse: collapse;
            width: 100%;
            margin: 16px 0;
        }}

        .markdown-body th, .markdown-body td {{
            border: 1px solid #e1e4e8;
            padding: 8px 12px;
        }}

        .markdown-body th {{
            background: #f6f8fa;
            font-weight: 600;
        }}

        .markdown-body a {{
            color: #0366d6;
            text-decoration: none;
        }}

        .markdown-body a:hover {{
            text-decoration: underline;
        }}

        /* Mermaid diagram styling */
        .mermaid {{
            margin: 24px 0;
            text-align: center;
        }}

        .breadcrumb {{
            margin-bottom: 20px;
            font-size: 14px;
            color: #6a737d;
        }}

        .breadcrumb a {{
            color: #0366d6;
            text-decoration: none;
        }}

        .breadcrumb a:hover {{
            text-decoration: underline;
        }}

        .empty-state {{
            text-align: center;
            padding: 60px 20px;
            color: #6a737d;
        }}

        .empty-state h2 {{
            font-size: 24px;
            margin-bottom: 8px;
        }}

        @media (max-width: 768px) {{
            .sidebar {{
                width: 100%;
                position: static;
                height: auto;
            }}

            .main-content {{
                margin-left: 0;
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <nav class="sidebar">
            <div class="sidebar-header">
                <h1>📚 Documentation</h1>
            </div>
            <ul class="nav-list">
                {nav_items}
            </ul>
        </nav>

        <main class="main-content">
            <div class="breadcrumb">
                <a href="/">Home</a> {breadcrumb}
            </div>
            <div class="content-card">
                <div id="content" class="markdown-body">
                    {content}
                </div>
            </div>
        </main>
    </div>

    <script>
        // Configure marked.js
        marked.setOptions({{
            highlight: function(code, lang) {{
                if (lang && hljs.getLanguage(lang)) {{
                    return hljs.highlight(code, {{ language: lang }}).value;
                }}
                return hljs.highlightAuto(code).value;
            }},
            breaks: true,
            gfm: true,
        }});

        // Render markdown if present
        const contentElement = document.getElementById('content');
        const rawContent = contentElement.textContent;

        if (rawContent && !contentElement.querySelector('*')) {{
            contentElement.innerHTML = marked.parse(rawContent);

            // Highlight code blocks
            document.querySelectorAll('pre code').forEach((block) => {{
                hljs.highlightElement(block);
            }});
        }}

        // Activate current nav item
        const currentPath = window.location.pathname;
        document.querySelectorAll('.nav-item a').forEach((link) => {{
            if (link.getAttribute('href') === currentPath) {{
                link.parentElement.classList.add('active');
            }}
        }});
    </script>
</body>
</html>
"""


class PreviewServer:
    """Web server for previewing documentation."""

    def __init__(self, docs_dir: str = ".mem/docs", host: str = "127.0.0.1", port: int = 8000):
        """
        Initialize preview server.

        Args:
            docs_dir: Directory containing documentation files
            host: Host to bind to
            port: Port to bind to
        """
        self.docs_dir = Path(docs_dir).resolve()
        self.host = host
        self.port = port

        if not self.docs_dir.exists():
            logger.warning(f"Documentation directory not found: {self.docs_dir}")
            self.docs_dir.mkdir(parents=True, exist_ok=True)

    def _get_all_docs(self) -> list:
        """Get list of all documentation files."""
        docs = []
        if not self.docs_dir.exists():
            return docs

        for md_file in self.docs_dir.rglob("*.md"):
            rel_path = md_file.relative_to(self.docs_dir)
            docs.append({
                'path': str(rel_path),
                'name': md_file.stem,
                'full_path': md_file
            })

        return sorted(docs, key=lambda x: x['path'])

    def _build_nav_items(self, current_path: Optional[str] = None) -> str:
        """Build navigation menu HTML."""
        docs = self._get_all_docs()

        if not docs:
            return '<li class="nav-item">No documents found</li>'

        nav_html = []
        current_dir = None

        for doc in docs:
            parts = Path(doc['path']).parts
            doc_dir = parts[0] if len(parts) > 1 else ''

            # Add directory header if changed
            if doc_dir != current_dir:
                if current_dir is not None:
                    nav_html.append('</ul></li>')
                current_dir = doc_dir
                if doc_dir:
                    nav_html.append(f'<li class="nav-item"><strong>{doc_dir}</strong><ul>')

            # Add document link
            link_path = f"/view/{doc['path']}"
            active = 'active' if current_path == link_path else ''
            nav_html.append(
                f'<li class="nav-item {active}"><a href="{link_path}">{doc["name"]}</a></li>'
            )

        if current_dir:
            nav_html.append('</ul></li>')

        return '\n'.join(nav_html)

    def _build_breadcrumb(self, path: str) -> str:
        """Build breadcrumb navigation."""
        parts = Path(path).parts
        breadcrumb = []

        for i, part in enumerate(parts[:-1]):
            breadcrumb.append(f'<span> / {part}</span>')

        if parts:
            breadcrumb.append(f'<span> / <strong>{parts[-1]}</strong></span>')

        return ''.join(breadcrumb)

    async def index(self, request):
        """Serve index page."""
        docs = self._get_all_docs()

        if not docs:
            content = """
            <div class="empty-state">
                <h2>No Documentation Found</h2>
                <p>Generate some documentation first using the mem-docgen tool.</p>
            </div>
            """
        else:
            content = "<h1>📚 Documentation Index</h1>\n<ul>\n"
            for doc in docs:
                link = f"/view/{doc['path']}"
                content += f'<li><a href="{link}">{doc["path"]}</a></li>\n'
            content += "</ul>"

        html = HTML_TEMPLATE.format(
            title="Documentation Index",
            nav_items=self._build_nav_items(),
            breadcrumb="",
            content=content
        )

        return HTMLResponse(html)

    async def view_doc(self, request):
        """Serve a specific documentation file."""
        # Get path from URL
        path = request.path_params.get('path', '')
        path = unquote(path)

        doc_path = self.docs_dir / path

        if not doc_path.exists() or not doc_path.is_file():
            return HTMLResponse(
                HTML_TEMPLATE.format(
                    title="Not Found",
                    nav_items=self._build_nav_items(),
                    breadcrumb="",
                    content="<h1>404 - Document Not Found</h1>"
                ),
                status_code=404
            )

        # Read markdown content
        try:
            with open(doc_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
        except Exception as e:
            logger.error(f"Error reading {doc_path}: {e}")
            return HTMLResponse(
                HTML_TEMPLATE.format(
                    title="Error",
                    nav_items=self._build_nav_items(),
                    breadcrumb="",
                    content=f"<h1>Error</h1><p>Failed to read document: {e}</p>"
                ),
                status_code=500
            )

        # Generate HTML
        title = doc_path.stem
        breadcrumb = self._build_breadcrumb(path)
        current_path = f"/view/{path}"

        html = HTML_TEMPLATE.format(
            title=title,
            nav_items=self._build_nav_items(current_path),
            breadcrumb=breadcrumb,
            content=md_content  # Will be rendered by marked.js on client side
        )

        return HTMLResponse(html)

    def create_app(self) -> Starlette:
        """Create Starlette application."""
        routes = [
            Route("/", self.index),
            Route("/view/{path:path}", self.view_doc),
        ]

        app = Starlette(debug=True, routes=routes)
        return app

    def start(self):
        """Start the preview server."""
        app = self.create_app()

        logger.info(f"Starting preview server at http://{self.host}:{self.port}")
        logger.info(f"Serving documentation from: {self.docs_dir}")

        print(f"\n{'='*60}")
        print(f"📚 Documentation Preview Server")
        print(f"{'='*60}")
        print(f"  URL: http://{self.host}:{self.port}")
        print(f"  Docs: {self.docs_dir}")
        print(f"{'='*60}\n")

        uvicorn.run(
            app,
            host=self.host,
            port=self.port,
            log_level="info"
        )


def start_preview_server(
    docs_dir: str = ".mem/docs",
    host: str = "127.0.0.1",
    port: int = 8000
):
    """
    Start the documentation preview server.

    Args:
        docs_dir: Directory containing documentation
        host: Host to bind to
        port: Port to listen on
    """
    server = PreviewServer(docs_dir=docs_dir, host=host, port=port)
    server.start()


if __name__ == "__main__":
    start_preview_server()
