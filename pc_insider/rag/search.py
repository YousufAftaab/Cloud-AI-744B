"""Lightweight local RAG and codebase search without heavy vector databases."""

import os
import re
from pathlib import Path
from pc_insider.config import settings
from pc_insider.security.policy import path_policy
from pc_insider.tools.registry import tool_registry

ALLOWED_EXTS = {".py", ".md", ".txt", ".json", ".bat", ".cmd", ".toml", ".yaml", ".yml", ".c", ".h"}

class CodebaseSearch:
    def __init__(self, root_dir: Path = None):
        self.root_dir = (root_dir or settings.workspace_dir).resolve()

    def search(self, query: str, directory: str = ".", max_chunks: int = 4) -> list[dict]:
        """Search local project files and extract relevant contextual snippets."""
        terms = [t.lower() for t in re.findall(r'[a-zA-Z0-9_]{3,}', query) if t.lower() not in ("what", "how", "where", "tell", "show", "find")]
        if not terms:
            return []

        search_path = path_policy.resolve_path(directory)
        if not search_path.exists() or not search_path.is_dir():
            search_path = self.root_dir

        scored_chunks = []

        for root, dirs, files in os.walk(search_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules", "venv", ".git", "colibri")]
            for fname in files:
                ext = Path(fname).suffix.lower()
                if ext not in ALLOWED_EXTS:
                    continue

                fpath = Path(root, fname)
                try:
                    text = fpath.read_text(encoding="utf-8", errors="replace")
                    lines = text.splitlines()
                except Exception:
                    continue

                # Search lines for matching terms
                for i, line in enumerate(lines):
                    line_lower = line.lower()
                    matches = sum(1 for t in terms if t in line_lower)
                    if matches > 0:
                        # Grab small surrounding context window (3 lines before, 3 lines after)
                        start_idx = max(0, i - 2)
                        end_idx = min(len(lines), i + 4)
                        snippet = "\n".join(lines[start_idx:end_idx])
                        rel_path = str(fpath.relative_to(self.root_dir)) if self.root_dir in fpath.parents or fpath == self.root_dir else str(fpath)
                        scored_chunks.append({
                            "path": rel_path,
                            "line_number": i + 1,
                            "score": matches,
                            "snippet": snippet
                        })

        # Sort by score descending and return top chunks
        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        return scored_chunks[:max_chunks]

codebase_search = CodebaseSearch()

def handle_search_knowledge(args: dict) -> dict:
    query = args.get("query", "").strip()
    directory = args.get("directory", ".").strip() or "."
    if not query:
        return {"success": False, "tool": "search_knowledge", "data": None, "error": {"type": "MissingArgument", "message": "Missing 'query'."}}

    chunks = codebase_search.search(query, directory=directory)
    if not chunks:
        return {"success": True, "tool": "search_knowledge", "data": {"output": "No relevant documentation or code found."}, "error": None}

    formatted = []
    for c in chunks:
        formatted.append(f"📄 {c['path']} (Line {c['line_number']}):\n```\n{c['snippet']}\n```")

    return {
        "success": True,
        "tool": "search_knowledge",
        "data": {
            "query": query,
            "chunks_found": len(chunks),
            "output": "\n\n".join(formatted)
        },
        "error": None
    }

tool_registry.register(
    name="search_knowledge",
    description="Retrieve relevant code snippets and documentation from the local project without external internet.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Keywords or topic to search for in project files."},
            "directory": {"type": "string", "description": "Directory to search (defaults to current folder)."}
        },
        "required": ["query"]
    },
    handler=handle_search_knowledge
)
