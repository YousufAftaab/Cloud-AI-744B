"""Verification engine: post-action assertions, file presence checks, and Python syntax validation."""

import ast
from pathlib import Path
from pc_insider.logger import log_verification

class VerificationResult:
    def __init__(self, passed: bool, check_type: str, message: str, details: dict = None):
        self.passed = passed
        self.check_type = check_type
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "check_type": self.check_type,
            "message": self.message,
            "details": self.details
        }

    def __repr__(self):
        return f"<VerificationResult passed={self.passed} type={self.check_type} msg={self.message}>"

class Verifier:
    def verify_action(self, tool_name: str, args: dict, tool_result: dict) -> VerificationResult:
        """Verify that the tool's intended post-condition was actually achieved on Windows."""
        if not tool_result.get("success", False):
            # Tool itself reported failure
            res = VerificationResult(passed=False, check_type="ToolExecution", message="Tool execution failed prior to verification.")
            log_verification(tool_name, str(args), False, res.message)
            return res

        data = tool_result.get("data", {})

        # 1. WRITE_FILE VERIFICATION
        if tool_name == "write_file":
            path_str = data.get("path") or args.get("path")
            p = Path(path_str)
            if not p.exists():
                res = VerificationResult(passed=False, check_type="FilePresence", message=f"Post-verification failed: File '{p}' does not exist on disk.")
                log_verification(tool_name, str(p), False, res.message)
                return res
            if p.stat().st_size == 0 and len(args.get("content", "")) > 0:
                res = VerificationResult(passed=False, check_type="FileSize", message=f"Post-verification failed: File '{p}' was written but has 0 bytes.")
                log_verification(tool_name, str(p), False, res.message)
                return res

            # Python syntax check if writing a .py file
            if p.suffix.lower() == ".py":
                syntax_res = self.check_python_syntax(p)
                if not syntax_res.passed:
                    log_verification(tool_name, str(p), False, syntax_res.message)
                    return syntax_res

            res = VerificationResult(passed=True, check_type="WriteVerified", message=f"Verified file exists on disk ({p.stat().st_size:,} bytes).")
            log_verification(tool_name, str(p), True, res.message)
            return res

        # 2. EDIT_FILE / PATCH_FILE VERIFICATION
        elif tool_name in ("edit_file", "patch_file"):
            path_str = data.get("path") or args.get("path")
            p = Path(path_str)
            if not p.exists():
                res = VerificationResult(passed=False, check_type="FilePresence", message=f"Target file '{p}' disappeared after edit.")
                log_verification(tool_name, str(p), False, res.message)
                return res

            new_snippet = args.get("new_snippet", "")
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                if new_snippet and new_snippet not in content:
                    res = VerificationResult(passed=False, check_type="SnippetPresence", message=f"New snippet was not found in '{p}' after edit operation.")
                    log_verification(tool_name, str(p), False, res.message)
                    return res
            except Exception as e:
                res = VerificationResult(passed=False, check_type="ReadCheck", message=f"Could not re-read file for verification: {e}")
                log_verification(tool_name, str(p), False, res.message)
                return res

            # Python syntax check
            if p.suffix.lower() == ".py":
                syntax_res = self.check_python_syntax(p)
                if not syntax_res.passed:
                    log_verification(tool_name, str(p), False, syntax_res.message)
                    return syntax_res

            res = VerificationResult(passed=True, check_type="EditVerified", message="Verified new snippet present and syntax valid.")
            log_verification(tool_name, str(p), True, res.message)
            return res

        # 3. DELETE_FILE VERIFICATION
        elif tool_name == "delete_file":
            path_str = data.get("path") or args.get("path")
            p = Path(path_str)
            if p.exists():
                res = VerificationResult(passed=False, check_type="DeletionCheck", message=f"Path '{p}' still exists on disk after delete operation.")
                log_verification(tool_name, str(p), False, res.message)
                return res
            res = VerificationResult(passed=True, check_type="DeletionVerified", message=f"Verified '{p}' is completely removed from disk.")
            log_verification(tool_name, str(p), True, res.message)
            return res

        # 4. RUN_COMMAND VERIFICATION
        elif tool_name == "run_command":
            exit_code = data.get("exit_code", 0)
            if exit_code != 0:
                res = VerificationResult(passed=False, check_type="ProcessExitCode", message=f"Command exited with non-zero exit code: {exit_code}.")
                log_verification(tool_name, args.get("command", "")[:50], False, res.message)
                return res
            res = VerificationResult(passed=True, check_type="CommandVerified", message="Command executed successfully (exit code 0).")
            log_verification(tool_name, args.get("command", "")[:50], True, res.message)
            return res

        # Default pass for read-only tools
        return VerificationResult(passed=True, check_type="ReadOnlyVerified", message="Read operation completed.")

    def check_python_syntax(self, file_path: Path) -> VerificationResult:
        """Parse Python AST to verify syntax validity."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            ast.parse(content, filename=str(file_path))
            return VerificationResult(passed=True, check_type="PythonAST", message="Python AST syntax is valid.")
        except SyntaxError as e:
            msg = f"Python SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"
            return VerificationResult(
                passed=False,
                check_type="PythonSyntaxError",
                message=msg,
                details={"line": e.lineno, "offset": e.offset, "error": e.msg, "text": e.text}
            )
        except Exception as e:
            return VerificationResult(passed=False, check_type="PythonASTException", message=f"AST verification error: {e}")

verifier = Verifier()
