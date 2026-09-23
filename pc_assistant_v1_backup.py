#!/usr/bin/env python3
"""Autonomous 100% Offline Local PC Assistant powered by Qwen 2.5 Coder 7B.

Features:
- Always-On Tools: Never says "I cannot access your PC".
- Autonomous PC Insider: Inspects files, directories, installed programs/games, and executes PowerShell commands.
- Live Streaming: Conversational responses stream in real-time typewriter style.
- Smart Action Display: Tool executions are formatted cleanly without raw JSON clutter.
- 100% Offline & Private: Zero internet or external cloud dependencies.
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OLLAMA_API_BASE = "http://127.0.0.1:11434/api"
MODEL_NAME = "qwen2.5-coder:7b"

# ANSI Color codes for Windows Terminal / Command Prompt
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

# ----------------- SYSTEM PROMPT -----------------

SYSTEM_PROMPT = """You are an intelligent, friendly AI companion and autonomous PC assistant running directly on the user's Windows machine.
You have full local access to their computer through your available tools: read_file, write_file, edit_file, delete_file, list_directory, and run_command.

Rules:
1. Autonomous PC Access:
   - When the user asks about files, folders, games, installed programs, disk space, processes, or system information, YOU MUST USE YOUR TOOLS (such as run_command with PowerShell or list_directory) to inspect their machine.
   - NEVER say "I cannot access your PC", "I don't have access to your files", or "As an AI I can't look". You DO have access via your tools! Use them!
   - To inspect installed games and programs on Windows, you can query the registry via run_command:
     Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*, HKLM:\\Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*, HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | Where-Object DisplayName | Select-Object DisplayName
     or inspect game folders like Steam: 'C:\\Program Files (x86)\\Steam\\steamapps\\common' using list_directory.
2. Natural Conversation:
   - When the user is just saying hello, asking general questions, discussing topics, or joking, answer naturally, warmly, and helpfully. Do not call tools when simple conversation is requested.
3. Be concise, direct, and helpful.
"""

# ----------------- TOOL DEFINITIONS -----------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a text file from the local filesystem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or overwrite an existing file with the provided content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write."},
                    "content": {"type": "string", "description": "Full text content to write."}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace an exact target snippet in an existing file with new content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to edit."},
                    "old_snippet": {"type": "string", "description": "The exact existing text to find and replace."},
                    "new_snippet": {"type": "string", "description": "The replacement text."}
                },
                "required": ["path", "old_snippet", "new_snippet"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file or folder from the local filesystem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file or directory to delete."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and subdirectories within a directory path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the directory (defaults to current folder)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command (PowerShell / cmd) on the local Windows machine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The exact command line string to run."}
                },
                "required": ["command"]
            }
        }
    }
]

# ----------------- TOOL IMPLEMENTATIONS -----------------

def tool_read_file(path: str) -> str:
    p = Path(path).resolve()
    if not p.exists():
        return f"Error: File not found at {p}"
    if not p.is_file():
        return f"Error: {p} is a directory, not a file."
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        preview = [f"{i+1:4d} | {line}" for i, line in enumerate(lines[:300])]
        if len(lines) > 300:
            preview.append(f"... ({len(lines) - 300} more lines truncated)")
        return "\n".join(preview)
    except Exception as e:
        return f"Error reading file: {e}"

def tool_write_file(path: str, content: str) -> str:
    p = Path(path).resolve()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Success: File written to {p} ({len(content)} characters)."
    except Exception as e:
        return f"Error writing file: {e}"

def tool_edit_file(path: str, old_snippet: str, new_snippet: str) -> str:
    p = Path(path).resolve()
    if not p.exists():
        return f"Error: File not found at {p}"
    try:
        text = p.read_text(encoding="utf-8")
        if old_snippet not in text:
            return f"Error: Target snippet not found in {p}. Ensure exact whitespace match."
        updated = text.replace(old_snippet, new_snippet, 1)
        p.write_text(updated, encoding="utf-8")
        return f"Success: Replaced target snippet in {p}."
    except Exception as e:
        return f"Error editing file: {e}"

def tool_delete_file(path: str) -> str:
    p = Path(path).resolve()
    if not p.exists():
        return f"Notice: File does not exist at {p}."
    try:
        if p.is_file():
            p.unlink()
            return f"Success: Deleted file {p}."
        elif p.is_dir():
            import shutil
            shutil.rmtree(p)
            return f"Success: Deleted directory {p}."
    except Exception as e:
        return f"Error deleting: {e}"

def tool_list_directory(path: str = ".") -> str:
    p = Path(path or ".").resolve()
    if not p.exists():
        return f"Error: Path not found: {p}"
    try:
        entries = []
        for item in sorted(p.iterdir()):
            kind = "<DIR> " if item.is_dir() else "      "
            size = f"{item.stat().st_size:,} bytes" if item.is_file() else ""
            entries.append(f"{kind} {item.name:35s} {size}")
        return "\n".join(entries) if entries else "(Directory is empty)"
    except Exception as e:
        return f"Error listing directory: {e}"

def tool_run_command(command: str) -> str:
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=60
        )
        out = res.stdout.strip()
        err = res.stderr.strip()
        result = []
        if out:
            result.append(out)
        if err:
            result.append(f"[STDERR]: {err}")
        return "\n".join(result) if result else "(Command executed with no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 60 seconds."
    except Exception as e:
        return f"Error executing command: {e}"

DISPATCH = {
    "read_file": lambda args: tool_read_file(args.get("path", "")),
    "write_file": lambda args: tool_write_file(args.get("path", ""), args.get("content", "")),
    "edit_file": lambda args: tool_edit_file(args.get("path", ""), args.get("old_snippet", ""), args.get("new_snippet", "")),
    "delete_file": lambda args: tool_delete_file(args.get("path", "")),
    "list_directory": lambda args: tool_list_directory(args.get("path", ".")),
    "run_command": lambda args: tool_run_command(args.get("command", ""))
}

# ----------------- STREAMING & TOOL PARSING -----------------

def stream_response(messages):
    """Stream response from Ollama. Streams conversation live while suppressing raw tool JSON."""
    url = f"{OLLAMA_API_BASE}/chat"
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "tools": TOOLS,
        "stream": True,
        "keep_alive": -1,
        "options": {
            "temperature": 0.2
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    buffer = []
    full_text = []
    first_token_printed = False
    suppress = False

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for line in resp:
                if not line:
                    continue
                chunk = json.loads(line.decode("utf-8"))
                token = chunk.get("message", {}).get("content", "")
                if not token:
                    continue

                full_text.append(token)
                accumulated = "".join(full_text)

                # Check if output is turning into a tool call
                if "```json" in accumulated or '{"name"' in accumulated or '{ "name"' in accumulated or accumulated.strip().startswith("{"):
                    suppress = True

                if not suppress:
                    if not first_token_printed:
                        print(f"{BOLD}{GREEN}Assistant > {RESET}", end="", flush=True)
                        first_token_printed = True
                    sys.stdout.write(token)
                    sys.stdout.flush()

        if first_token_printed and not suppress:
            print()  # End line after streaming conversation

    except Exception as e:
        return {"error": str(e), "full_text": "".join(full_text)}

    return {"full_text": "".join(full_text)}

def extract_tool_call(raw_text):
    """Extract tool call dictionary if present in the text, handling markdown blocks and nested JSON."""
    text = raw_text.strip()
    known_tools = set(DISPATCH.keys())

    # 1. Check markdown code blocks ```json ... ```
    blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    for b in blocks:
        try:
            parsed = json.loads(b.strip())
            if isinstance(parsed, dict) and parsed.get("name") in known_tools:
                return parsed
        except Exception:
            pass

    # 2. Try full JSON parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and parsed.get("name") in known_tools:
            return parsed
    except Exception:
        pass

    # 3. Balanced braces parser to handle nested JSON objects
    start = text.find('{"name"')
    if start == -1:
        start = text.find('{ "name"')
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start:i+1])
                        if parsed.get("name") in known_tools:
                            return parsed
                    except Exception:
                        break

    return None

# ----------------- MAIN INTERACTIVE LOOP -----------------

def main():
    os.system("")  # Enable ANSI in Windows terminal

    print(f"\n{BOLD}{CYAN}==============================================================================={RESET}")
    print(f"{BOLD}{CYAN}            QWEN 2.5 CODER 7B — AUTONOMOUS OFFLINE PC ASSISTANT{RESET}")
    print(f"{BOLD}{CYAN}==============================================================================={RESET}")
    print(f"{GREEN}Local Engine:{RESET} Ollama AVX2 CPU | {GREEN}Storage:{RESET} 100% Offline | {GREEN}Tools:{RESET} ALWAYS-ON")
    print(f"{DIM}Commands: 'clear' to reset chat | 'exit' to quit{RESET}")
    print(f"{BOLD}{CYAN}==============================================================================={RESET}\n")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user_input = input(f"{BOLD}{CYAN}You > {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print(f"{GREEN}Assistant >{RESET} Goodbye!")
            break
        if user_input.lower() == "clear":
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            print(f"{YELLOW}[Conversation history cleared]{RESET}\n")
            continue

        messages.append({"role": "user", "content": user_input})

        # Agent Step Loop
        step = 0
        max_steps = 6
        while step < max_steps:
            step += 1
            if step == 1:
                print(f"{DIM}Thinking...{RESET}", end="\r", flush=True)

            res = stream_response(messages)
            if "error" in res:
                print(f"\r{RED}[Error]: {res['error']}{RESET}\n")
                break

            output_text = res.get("full_text", "").strip()
            tool_call = extract_tool_call(output_text)

            if not tool_call:
                # Direct response or completion
                messages.append({"role": "assistant", "content": output_text})
                print()  # Spacer
                break

            # Process tool execution
            fn_name = tool_call.get("name")
            fn_args = tool_call.get("arguments", {})
            if isinstance(fn_args, str):
                try:
                    fn_args = json.loads(fn_args)
                except Exception:
                    fn_args = {}

            print(f"\r{BOLD}{YELLOW}[PC Action]{RESET} Running {BOLD}{fn_name}{RESET} with {fn_args}")
            handler = DISPATCH.get(fn_name)
            result = handler(fn_args) if handler else f"Error: Unknown tool {fn_name}"

            preview = result.strip().splitlines()[0] if result.strip() else "(Empty output)"
            if len(preview) > 90:
                preview = preview[:90] + "..."
            print(f"{CYAN}  -> Result:{RESET} {preview}\n")

            # Feed the tool execution and result back into the agent context
            messages.append({"role": "assistant", "content": json.dumps(tool_call)})
            messages.append({"role": "user", "content": f"[Tool Result for {fn_name}]: {result}"})
            # Loop continues so model can synthesize the findings and answer!

if __name__ == "__main__":
    main()
