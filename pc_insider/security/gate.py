"""Security gate: tool invocation risk classification and user permission validation."""

import re
from enum import Enum
from pathlib import Path
from pc_insider.config import settings
from pc_insider.security.policy import path_policy
from pc_insider.logger import log_tool_invocation

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class PermissionResult:
    def __init__(self, allowed: bool, risk: RiskLevel, reason: str, requires_prompt: bool = False):
        self.allowed = allowed
        self.risk = risk
        self.reason = reason
        self.requires_prompt = requires_prompt

    def __repr__(self):
        return f"<PermissionResult allowed={self.allowed} risk={self.risk.value} reason={self.reason}>"

# High-risk PowerShell / Shell command patterns
SHELL_CRITICAL_PATTERNS = [
    re.compile(r'\b(format-volume|diskpart|bcdedit)\b', re.IGNORECASE),
    re.compile(r'(\biex\b|invoke-expression)\s+', re.IGNORECASE),
    re.compile(r'(rmdir|rd)\s+/[sq]\s+[c-z]:\\', re.IGNORECASE),
    re.compile(r'remove-item\s+.*-(recurse|force)\s+[c-z]:\\', re.IGNORECASE),
    re.compile(r'\b(net\s+user|net\s+localgroup)\b.*(/add|/delete)', re.IGNORECASE),
]

SHELL_HIGH_PATTERNS = [
    re.compile(r'\b(stop-process|taskkill|kill)\b', re.IGNORECASE),
    re.compile(r'\b(start-service|stop-service|restart-service|sc\.exe|net\s+start|net\s+stop)\b', re.IGNORECASE),
    re.compile(r'\b(set-itemproperty|remove-itemproperty|reg\s+add|reg\s+delete)\b', re.IGNORECASE),
    re.compile(r'\b(netsh|new-netfirewallrule|set-netfirewallrule)\b', re.IGNORECASE),
    re.compile(r'\b(takeown|icacls)\b', re.IGNORECASE),
]

SHELL_MEDIUM_PATTERNS = [
    re.compile(r'\b(pip|npm|yarn|cargo|winget)\s+(install|uninstall|update)\b', re.IGNORECASE),
    re.compile(r'\b(python|py|node|deno)\s+[\w\.\-\/\\]+\.py\b', re.IGNORECASE),
    re.compile(r'\b(git\s+(commit|push|checkout|merge|reset|rebase))\b', re.IGNORECASE),
    re.compile(r'\b(mkdir|md|new-item)\b', re.IGNORECASE),
]

class SecurityGate:
    def __init__(self, prompt_callback=None):
        self.prompt_callback = prompt_callback or self._default_prompt

    def _default_prompt(self, tool_name: str, target: str, risk: RiskLevel, reason: str) -> bool:
        """Terminal interactive prompt for user confirmation."""
        print(f"\n\033[93m================================================================================")
        print(f" [SECURITY PERMISSION REQUIRED — {risk.value} RISK]")
        print(f" Tool   : {tool_name}")
        print(f" Target : {target}")
        print(f" Details: {reason}")
        print(f"================================================================================\033[0m")
        try:
            choice = input(f"\033[1mAllow this action? [y/N]: \033[0m").strip().lower()
            return choice in ("y", "yes")
        except (KeyboardInterrupt, EOFError):
            print()
            return False

    def classify_risk(self, tool_name: str, args: dict) -> tuple[RiskLevel, str]:
        """Classify the risk level of any tool invocation."""
        if tool_name in ("read_file", "list_directory", "search_files"):
            path_str = args.get("path", "") or args.get("directory", ".")
            ok, p, reason = path_policy.validate_access(path_str, action="read")
            if not ok:
                return RiskLevel.CRITICAL, reason
            return RiskLevel.LOW, "Read-only inspection"

        elif tool_name in ("write_file", "edit_file", "patch_file"):
            path_str = args.get("path", "")
            ok, p, reason = path_policy.validate_access(path_str, action="write")
            if not ok:
                return RiskLevel.CRITICAL, reason
            if path_policy.is_in_workspace(p):
                return RiskLevel.MEDIUM, f"Modifying file within workspace ({p.name})"
            return RiskLevel.HIGH, f"Modifying file outside workspace ({p})"

        elif tool_name == "delete_file":
            path_str = args.get("path", "")
            ok, p, reason = path_policy.validate_access(path_str, action="delete")
            if not ok:
                return RiskLevel.CRITICAL, reason
            if p.is_dir():
                return RiskLevel.CRITICAL, f"Recursive deletion of directory: {p}"
            if path_policy.is_in_workspace(p):
                return RiskLevel.MEDIUM, f"Deleting file inside workspace: {p.name}"
            return RiskLevel.HIGH, f"Deleting file outside workspace: {p}"

        elif tool_name == "run_command":
            cmd = args.get("command", "").strip()
            # 1. Critical shell patterns
            for pat in SHELL_CRITICAL_PATTERNS:
                if pat.search(cmd):
                    return RiskLevel.CRITICAL, f"Potentially destructive command pattern: {cmd[:60]}"
            # 2. High shell patterns
            for pat in SHELL_HIGH_PATTERNS:
                if pat.search(cmd):
                    return RiskLevel.HIGH, f"System/Process modification command: {cmd[:60]}"
            # 3. Medium shell patterns
            for pat in SHELL_MEDIUM_PATTERNS:
                if pat.search(cmd):
                    return RiskLevel.MEDIUM, f"Package/Script execution command: {cmd[:60]}"
            # Default low
            return RiskLevel.LOW, "General system/inspection command"

        return RiskLevel.HIGH, f"Unknown tool: {tool_name}"

    def check_permission(self, tool_name: str, args: dict, bypass_prompt: bool = False) -> PermissionResult:
        """Central security decision function."""
        risk, reason = self.classify_risk(tool_name, args)

        # 1. Blocked critical actions
        if risk == RiskLevel.CRITICAL and "Access denied" in reason:
            log_tool_invocation(tool_name, args, risk.value, approved=False)
            return PermissionResult(allowed=False, risk=risk, reason=reason)

        sec_cfg = settings.security

        # 2. LOW Risk: Auto-approve
        if risk == RiskLevel.LOW:
            log_tool_invocation(tool_name, args, risk.value, approved=True)
            return PermissionResult(allowed=True, risk=risk, reason=reason)

        # 3. MEDIUM Risk
        if risk == RiskLevel.MEDIUM:
            req_prompt = sec_cfg.get("require_confirmation_medium", False)
            if not req_prompt or bypass_prompt:
                log_tool_invocation(tool_name, args, risk.value, approved=True)
                return PermissionResult(allowed=True, risk=risk, reason=reason)
            allowed = self.prompt_callback(tool_name, str(args), risk, reason)
            log_tool_invocation(tool_name, args, risk.value, approved=allowed)
            return PermissionResult(allowed=allowed, risk=risk, reason=reason, requires_prompt=True)

        # 4. HIGH Risk
        if risk == RiskLevel.HIGH:
            req_prompt = sec_cfg.get("require_confirmation_high", True)
            if not req_prompt or bypass_prompt:
                log_tool_invocation(tool_name, args, risk.value, approved=True)
                return PermissionResult(allowed=True, risk=risk, reason=reason)
            allowed = self.prompt_callback(tool_name, str(args), risk, reason)
            log_tool_invocation(tool_name, args, risk.value, approved=allowed)
            return PermissionResult(allowed=allowed, risk=risk, reason=reason, requires_prompt=True)

        # 5. CRITICAL Risk
        if risk == RiskLevel.CRITICAL:
            req_prompt = sec_cfg.get("require_confirmation_critical", True)
            if not req_prompt or bypass_prompt:
                log_tool_invocation(tool_name, args, risk.value, approved=True)
                return PermissionResult(allowed=True, risk=risk, reason=reason)
            allowed = self.prompt_callback(tool_name, str(args), risk, reason)
            log_tool_invocation(tool_name, args, risk.value, approved=allowed)
            return PermissionResult(allowed=allowed, risk=risk, reason=reason, requires_prompt=True)

        return PermissionResult(allowed=False, risk=risk, reason="Default security block")

security_gate = SecurityGate()
