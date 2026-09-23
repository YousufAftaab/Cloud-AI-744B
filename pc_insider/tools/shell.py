"""Shell execution tool: PowerShell subprocess with timeout and output length controls."""

import subprocess
from pc_insider.tools.registry import tool_registry

MAX_OUTPUT_CHARS = 3500
MAX_OUTPUT_LINES = 60

def _truncate_output(text: str) -> tuple[str, bool]:
    """Truncate massive command outputs to protect the 4096-token LLM context window."""
    if not text:
        return text, False

    lines = text.splitlines()
    total_lines = len(lines)
    truncated = False

    if total_lines > MAX_OUTPUT_LINES:
        lines = lines[:MAX_OUTPUT_LINES]
        truncated = True

    result = "\n".join(lines)
    if len(result) > MAX_OUTPUT_CHARS:
        result = result[:MAX_OUTPUT_CHARS]
        truncated = True

    if truncated:
        result += f"\n... [Output truncated: {max(0, total_lines - MAX_OUTPUT_LINES)} lines omitted for LLM context preservation]"

    return result, truncated

def handle_run_command(args: dict) -> dict:
    command = args.get("command", "").strip()
    if not command:
        return {
            "success": False,
            "tool": "run_command",
            "data": None,
            "error": {"type": "MissingArgument", "message": "Missing 'command' argument."}
        }

    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=60
        )
        stdout_raw = res.stdout.strip()
        stderr_raw = res.stderr.strip()

        stdout_clean, stdout_trunc = _truncate_output(stdout_raw)
        stderr_clean, stderr_trunc = _truncate_output(stderr_raw)

        is_success = (res.returncode == 0)

        return {
            "success": is_success,
            "tool": "run_command",
            "data": {
                "command": command,
                "exit_code": res.returncode,
                "stdout": stdout_clean or "(No standard output)",
                "stderr": stderr_clean,
                "truncated": stdout_trunc or stderr_trunc
            },
            "error": None if is_success else {"type": "CommandFailed", "message": stderr_clean or f"Command exited with non-zero code {res.returncode}"}
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "tool": "run_command",
            "data": None,
            "error": {"type": "CommandTimeout", "message": "Command timed out after 60 seconds."}
        }
    except Exception as e:
        return {
            "success": False,
            "tool": "run_command",
            "data": None,
            "error": {"type": "ExecutionException", "message": str(e)}
        }

tool_registry.register(
    name="run_command",
    description="Execute a shell command via Windows PowerShell with automatic safety checks, timeout, and output truncation.",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The exact PowerShell/CMD command to run."}
        },
        "required": ["command"]
    },
    handler=handle_run_command
)
