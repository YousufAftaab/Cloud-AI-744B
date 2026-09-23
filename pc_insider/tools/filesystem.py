"""Filesystem tools: paginated reading, safe writing, single-match editing, searching, and deletion."""

import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Optional
from pc_insider.tools.registry import tool_registry
from pc_insider.security.policy import path_policy

def _read_with_fallback_encoding(p: Path, max_bytes: int = 65536) -> tuple[str, str]:
    """Read file with encoding fallback (utf-8, latin-1, cp1252)."""
    raw_data = p.read_bytes()
    truncated = False
    if len(raw_data) > max_bytes:
        raw_data = raw_data[:max_bytes]
        truncated = True

    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw_data.decode(enc), truncated
        except UnicodeDecodeError:
            continue
    return raw_data.decode("utf-8", errors="replace"), truncated

# ----------------- 1. READ_FILE -----------------

def handle_read_file(args: dict) -> dict:
    path_str = args.get("path", "").strip()
    if not path_str:
        return {"success": False, "tool": "read_file", "data": None, "error": {"type": "MissingArgument", "message": "Missing 'path' argument."}}

    p = path_policy.resolve_path(path_str)
    if not p.exists():
        return {"success": False, "tool": "read_file", "data": None, "error": {"type": "FileNotFound", "message": f"File not found at '{p}'."}}
    if not p.is_file():
        return {"success": False, "tool": "read_file", "data": None, "error": {"type": "NotAFile", "message": f"Path '{p}' is a directory, not a file."}}

    start_line = max(1, int(args.get("start_line", 1)))
    end_line = args.get("end_line")
    end_line = int(end_line) if end_line is not None else None
    max_bytes = int(args.get("max_bytes", 65536))

    try:
        text, byte_truncated = _read_with_fallback_encoding(p, max_bytes)
        all_lines = text.splitlines()
        total_lines = len(all_lines)

        # 1-based line slicing
        start_idx = start_line - 1
        end_idx = end_line if end_line is not None else total_lines
        sliced_lines = all_lines[start_idx:end_idx]

        formatted = [f"{start_line + i:5d} | {line}" for i, line in enumerate(sliced_lines)]
        output_text = "\n".join(formatted)

        return {
            "success": True,
            "tool": "read_file",
            "data": {
                "path": str(p),
                "total_lines": total_lines,
                "start_line": start_line,
                "end_line": start_line + len(sliced_lines) - 1,
                "lines_count": len(sliced_lines),
                "content": output_text,
                "truncated": byte_truncated or (end_line is not None and end_line < total_lines),
            },
            "error": None
        }
    except Exception as e:
        return {"success": False, "tool": "read_file", "data": None, "error": {"type": "ReadError", "message": str(e)}}

# ----------------- 2. WRITE_FILE -----------------

def handle_write_file(args: dict) -> dict:
    path_str = args.get("path", "").strip()
    content = args.get("content", "")
    if not path_str:
        return {"success": False, "tool": "write_file", "data": None, "error": {"type": "MissingArgument", "message": "Missing 'path' argument."}}

    p = path_policy.resolve_path(path_str)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        encoded = content.encode("utf-8")
        p.write_bytes(encoded)
        sha256 = hashlib.sha256(encoded).hexdigest()
        return {
            "success": True,
            "tool": "write_file",
            "data": {
                "path": str(p),
                "bytes_written": len(encoded),
                "sha256": sha256,
                "message": f"Successfully wrote {len(encoded)} bytes to '{p}'."
            },
            "error": None
        }
    except Exception as e:
        return {"success": False, "tool": "write_file", "data": None, "error": {"type": "WriteError", "message": str(e)}}

# ----------------- 3. EDIT_FILE -----------------

def handle_edit_file(args: dict) -> dict:
    path_str = args.get("path", "").strip()
    old_snippet = args.get("old_snippet", "")
    new_snippet = args.get("new_snippet", "")
    allow_multiple = bool(args.get("allow_multiple", False))

    if not path_str or not old_snippet:
        return {"success": False, "tool": "edit_file", "data": None, "error": {"type": "MissingArgument", "message": "Missing 'path' or 'old_snippet'."}}

    p = path_policy.resolve_path(path_str)
    if not p.exists():
        return {"success": False, "tool": "edit_file", "data": None, "error": {"type": "FileNotFound", "message": f"File '{p}' does not exist."}}

    try:
        text = p.read_text(encoding="utf-8")
        count = text.count(old_snippet)
        if count == 0:
            return {"success": False, "tool": "edit_file", "data": None, "error": {"type": "SnippetNotFound", "message": f"Target snippet not found in '{p}'. Check whitespace and indentation exactly."}}
        if count > 1 and not allow_multiple:
            return {"success": False, "tool": "edit_file", "data": None, "error": {"type": "MultipleMatches", "message": f"Snippet found {count} times in '{p}'. Specify more surrounding context or set 'allow_multiple'=true."}}

        replaced_text = text.replace(old_snippet, new_snippet, 1 if not allow_multiple else -1)
        p.write_text(replaced_text, encoding="utf-8")

        return {
            "success": True,
            "tool": "edit_file",
            "data": {
                "path": str(p),
                "replacements_made": 1 if not allow_multiple else count,
                "message": f"Successfully replaced {1 if not allow_multiple else count} occurrence(s) in '{p}'."
            },
            "error": None
        }
    except Exception as e:
        return {"success": False, "tool": "edit_file", "data": None, "error": {"type": "EditError", "message": str(e)}}

# ----------------- 4. PATCH_FILE -----------------

def handle_patch_file(args: dict) -> dict:
    """Multi-line structural patch alias."""
    return handle_edit_file(args)

# ----------------- 5. DELETE_FILE -----------------

def handle_delete_file(args: dict) -> dict:
    path_str = args.get("path", "").strip()
    if not path_str:
        return {"success": False, "tool": "delete_file", "data": None, "error": {"type": "MissingArgument", "message": "Missing 'path' argument."}}

    p = path_policy.resolve_path(path_str)
    if not p.exists():
        return {"success": True, "tool": "delete_file", "data": {"path": str(p), "message": "Notice: Target path did not exist on disk."}, "error": None}

    try:
        if p.is_file():
            p.unlink()
            return {"success": True, "tool": "delete_file", "data": {"path": str(p), "deleted": "file", "message": f"Deleted file '{p}'."}, "error": None}
        elif p.is_dir():
            shutil.rmtree(p)
            return {"success": True, "tool": "delete_file", "data": {"path": str(p), "deleted": "directory", "message": f"Deleted directory tree '{p}'."}, "error": None}
    except Exception as e:
        return {"success": False, "tool": "delete_file", "data": None, "error": {"type": "DeleteError", "message": str(e)}}

# ----------------- 6. LIST_DIRECTORY -----------------

def handle_list_directory(args: dict) -> dict:
    path_str = args.get("path", ".").strip() or "."
    max_items = int(args.get("max_items", 100))

    p = path_policy.resolve_path(path_str)
    if not p.exists():
        return {"success": False, "tool": "list_directory", "data": None, "error": {"type": "DirectoryNotFound", "message": f"Directory '{p}' not found."}}
    if not p.is_dir():
        return {"success": False, "tool": "list_directory", "data": None, "error": {"type": "NotADirectory", "message": f"Path '{p}' is a file, not a directory."}}

    try:
        entries = []
        count = 0
        truncated = False
        for item in sorted(p.iterdir()):
            count += 1
            if count > max_items:
                truncated = True
                break
            is_dir = item.is_dir()
            size = item.stat().st_size if not is_dir else 0
            entries.append({
                "name": item.name,
                "is_dir": is_dir,
                "size_bytes": size if not is_dir else None
            })

        table_lines = []
        for e in entries:
            kind = "<DIR> " if e["is_dir"] else "      "
            sz = f"{e['size_bytes']:,} bytes" if e["size_bytes"] is not None else ""
            table_lines.append(f"{kind} {e['name']:35s} {sz}")
        output = "\n".join(table_lines) if table_lines else "(Directory is empty)"
        if truncated:
            output += f"\n... ({count - max_items} more items truncated)"

        return {
            "success": True,
            "tool": "list_directory",
            "data": {
                "path": str(p),
                "entries_count": len(entries),
                "output": output,
                "truncated": truncated
            },
            "error": None
        }
    except Exception as e:
        return {"success": False, "tool": "list_directory", "data": None, "error": {"type": "ListError", "message": str(e)}}

# ----------------- 7. SEARCH_FILES -----------------

def handle_search_files(args: dict) -> dict:
    dir_str = args.get("directory", ".").strip() or "."
    pattern = args.get("filename_pattern", "").strip()
    content_query = args.get("content_query", "").strip()
    max_results = int(args.get("max_results", 25))

    p = path_policy.resolve_path(dir_str)
    if not p.exists() or not p.is_dir():
        return {"success": False, "tool": "search_files", "data": None, "error": {"type": "DirectoryNotFound", "message": f"Search directory '{p}' not found."}}

    matches = []
    try:
        pat_re = re.compile(re.escape(pattern).replace(r"\*", ".*"), re.IGNORECASE) if pattern else None
        content_re = re.compile(content_query, re.IGNORECASE) if content_query else None

        for root, dirs, files in os.walk(p):
            # Skip hidden and cache folders
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules", "venv", ".git")]
            for f in files:
                if len(matches) >= max_results:
                    break
                if pat_re and not pat_re.search(f):
                    continue
                file_path = Path(root, f)
                if content_re:
                    try:
                        text, _ = _read_with_fallback_encoding(file_path, max_bytes=32768)
                        line_matches = []
                        for idx, line in enumerate(text.splitlines()):
                            if content_re.search(line):
                                line_matches.append(f"L{idx+1}: {line.strip()[:80]}")
                                if len(line_matches) >= 3:
                                    break
                        if line_matches:
                            matches.append({
                                "path": str(file_path.relative_to(p)),
                                "matches": line_matches
                            })
                    except Exception:
                        continue
                else:
                    matches.append({
                        "path": str(file_path.relative_to(p)),
                        "size_bytes": file_path.stat().st_size
                    })

        output_lines = []
        for m in matches:
            if "matches" in m:
                output_lines.append(f"📄 {m['path']}")
                for lm in m["matches"]:
                    output_lines.append(f"   {lm}")
            else:
                output_lines.append(f"📄 {m['path']} ({m.get('size_bytes', 0):,} bytes)")

        return {
            "success": True,
            "tool": "search_files",
            "data": {
                "directory": str(p),
                "matches_count": len(matches),
                "results": matches,
                "output": "\n".join(output_lines) if output_lines else "No matching files found.",
            },
            "error": None
        }
    except Exception as e:
        return {"success": False, "tool": "search_files", "data": None, "error": {"type": "SearchError", "message": str(e)}}

# ----------------- REGISTRATION -----------------

tool_registry.register(
    name="read_file",
    description="Read the contents of a text file line-by-line with pagination support.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative file path."},
            "start_line": {"type": "integer", "description": "Starting line number (1-based, default 1)."},
            "end_line": {"type": "integer", "description": "Ending line number (inclusive, optional)."},
            "max_bytes": {"type": "integer", "description": "Max bytes to read (default 65536)."}
        },
        "required": ["path"]
    },
    handler=handle_read_file
)

tool_registry.register(
    name="write_file",
    description="Create or overwrite a file with UTF-8 text content.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to write."},
            "content": {"type": "string", "description": "Full text content."}
        },
        "required": ["path", "content"]
    },
    handler=handle_write_file
)

tool_registry.register(
    name="edit_file",
    description="Replace an exact target snippet in an existing file. Guards against accidental multi-replacements.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to file."},
            "old_snippet": {"type": "string", "description": "The exact existing text to find and replace."},
            "new_snippet": {"type": "string", "description": "The replacement text."},
            "allow_multiple": {"type": "boolean", "description": "If true, replace all occurrences. Default false."}
        },
        "required": ["path", "old_snippet", "new_snippet"]
    },
    handler=handle_edit_file
)

tool_registry.register(
    name="patch_file",
    description="Apply multi-line patch or replacement to a file.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to file."},
            "old_snippet": {"type": "string", "description": "Target text."},
            "new_snippet": {"type": "string", "description": "Replacement text."}
        },
        "required": ["path", "old_snippet", "new_snippet"]
    },
    handler=handle_patch_file
)

tool_registry.register(
    name="delete_file",
    description="Delete a file or folder from the filesystem.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file or directory to delete."}
        },
        "required": ["path"]
    },
    handler=handle_delete_file
)

tool_registry.register(
    name="list_directory",
    description="List files and subdirectories within a directory path.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to directory (defaults to current folder)."},
            "max_items": {"type": "integer", "description": "Max entries to list (default 100)."}
        }
    },
    handler=handle_list_directory
)

tool_registry.register(
    name="search_files",
    description="Search for files by filename pattern (e.g. *.py) or search within file contents using text/regex.",
    parameters={
        "type": "object",
        "properties": {
            "directory": {"type": "string", "description": "Directory to search (defaults to current folder)."},
            "filename_pattern": {"type": "string", "description": "Filename pattern (e.g. *.py, test_*)."},
            "content_query": {"type": "string", "description": "Text or regex to search inside files."},
            "max_results": {"type": "integer", "description": "Maximum matching files to return (default 25)."}
        }
    },
    handler=handle_search_files
)
