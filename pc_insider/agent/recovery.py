"""Deterministic error recovery engine with bounded retries and fuzzy filename matching."""

import difflib
from pathlib import Path
from pc_insider.config import settings
from pc_insider.agent.verifier import VerificationResult
from pc_insider.logger import log_recovery

class RecoveryAction:
    def __init__(self, can_retry: bool, feedback_message: str, suggestion: dict = None):
        self.can_retry = can_retry
        self.feedback_message = feedback_message
        self.suggestion = suggestion or {}

class RecoveryEngine:
    def __init__(self, max_retries: int = None):
        self.max_retries = max_retries if max_retries is not None else settings.max_retries
        self.retry_counts: dict[str, int] = {}

    def reset(self):
        self.retry_counts.clear()

    def handle_failure(
        self,
        tool_name: str,
        args: dict,
        tool_result: dict,
        verification_result: VerificationResult = None
    ) -> RecoveryAction:
        """Analyze failure and produce deterministic recovery feedback for the LLM."""
        key = f"{tool_name}:{args.get('path', '') or args.get('command', '')[:30]}"
        current_count = self.retry_counts.get(key, 0)

        # Enforce bounded retry limit
        if current_count >= self.max_retries:
            log_recovery(key, "RetryLimitExceeded", False)
            return RecoveryAction(
                can_retry=False,
                feedback_message=(
                    f"Action failed after {current_count} retry attempt(s). Halting to prevent infinite loop. "
                    f"Please ask the user for clarification or try a fundamentally different approach."
                )
            )

        self.retry_counts[key] = current_count + 1
        err_info = tool_result.get("error") or {}
        err_type = err_info.get("type", "")
        err_msg = err_info.get("message", "")

        # 1. FILENOTFOUND RECOVERY: Fuzzy search parent folder
        if err_type == "FileNotFound" or "File not found" in err_msg:
            path_str = args.get("path", "")
            p = Path(path_str)
            parent = p.parent if p.parent.exists() else Path.cwd()
            if parent.exists() and parent.is_dir():
                try:
                    candidates = [item.name for item in parent.iterdir()]
                    close = difflib.get_close_matches(p.name, candidates, n=3, cutoff=0.5)
                    if close:
                        rec_msg = f"[Recovery Hint]: File '{p.name}' was not found. Closest matching files in '{parent}': {close}. Check if you meant one of these."
                        log_recovery(key, f"SuggestFiles:{close}", True)
                        return RecoveryAction(can_retry=True, feedback_message=rec_msg, suggestion={"close_matches": close})
                except Exception:
                    pass

        # 2. PYTHON SYNTAX ERROR RECOVERY
        if verification_result and verification_result.check_type == "PythonSyntaxError":
            details = verification_result.details
            line = details.get("line", "?")
            err_text = details.get("error", "Syntax error")
            failing_code = details.get("text", "").strip()
            rec_msg = (
                f"[Verification Recovery]: The file was written but contains a Python SyntaxError at line {line}: '{err_text}'.\n"
                f"Failing line content: `{failing_code}`.\n"
                f"Use edit_file or write_file to correct the syntax error immediately."
            )
            log_recovery(key, f"SyntaxFixLine:{line}", True)
            return RecoveryAction(can_retry=True, feedback_message=rec_msg, suggestion=details)

        # 3. PERMISSION DENIED RECOVERY
        if err_type == "PermissionDenied" or "Access is denied" in err_msg or "Permission denied" in err_msg:
            rec_msg = (
                f"[Security Recovery]: Operation was blocked due to permissions or security gate policy: {err_msg}.\n"
                f"Do NOT attempt the exact same blocked operation. Explain the permission boundary to the user or operate within the allowed workspace."
            )
            log_recovery(key, "PermissionBoundaryExceeded", False)
            return RecoveryAction(can_retry=False, feedback_message=rec_msg)

        # 4. COMMAND FAILURE RECOVERY
        if tool_name == "run_command":
            rec_msg = (
                f"[Command Recovery]: PowerShell command exited with an error: {err_msg}.\n"
                f"Analyze the error message above, adjust parameters or command syntax, and retry (Attempt {current_count+1}/{self.max_retries})."
            )
            log_recovery(key, f"CommandRetry:{current_count+1}", True)
            return RecoveryAction(can_retry=True, feedback_message=rec_msg)

        # Generic recovery
        rec_msg = f"[Error Observation]: {err_msg}. Review the failure and formulate an alternate step (Attempt {current_count+1}/{self.max_retries})."
        log_recovery(key, f"GenericRetry:{current_count+1}", True)
        return RecoveryAction(can_retry=True, feedback_message=rec_msg)

recovery_engine = RecoveryEngine()
