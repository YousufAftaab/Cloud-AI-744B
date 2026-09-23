"""Filesystem access policy: workspace containment, protected paths, and path traversal prevention."""

import os
from pathlib import Path
from pc_insider.config import settings

class PathPolicy:
    def __init__(self, workspace_root: Path = None):
        self.workspace_root = (workspace_root or settings.workspace_dir).resolve()
        
        # User home directory
        self.user_home = Path.home().resolve()
        
        # System directories (Protected from modification/deletion)
        win_dir = os.environ.get("SystemRoot", r"C:\Windows")
        self.system_dirs = [
            Path(win_dir).resolve(),
            Path(win_dir, "System32").resolve(),
            Path(win_dir, "SysWOW64").resolve(),
            Path(r"C:\Program Files").resolve(),
            Path(r"C:\Program Files (x86)").resolve(),
            Path(r"C:\ProgramData").resolve(),
        ]
        
        # Sensitive credential locations (Protected from reading/modification)
        self.sensitive_dirs = [
            self.user_home / ".ssh",
            self.user_home / ".aws",
            self.user_home / ".azure",
            self.user_home / ".gnupg",
            self.user_home / "AppData" / "Local" / "Microsoft" / "Credentials",
            self.user_home / "AppData" / "Roaming" / "Microsoft" / "Vault",
        ]
        
        # Files that must never be written or deleted
        self.critical_files = [
            "pagefile.sys", "swapfile.sys", "hiberfil.sys", "bootmgr", "ntldr"
        ]

    def resolve_path(self, raw_path: str) -> Path:
        """Resolve path and eliminate path traversal (.. sequences)."""
        p = Path(raw_path).expanduser()
        if not p.is_absolute():
            p = self.workspace_root / p
        return p.resolve()

    def is_in_workspace(self, path: Path) -> bool:
        """Check if path is inside the configured workspace root."""
        try:
            return path == self.workspace_root or self.workspace_root in path.parents
        except Exception:
            return False

    def is_sensitive(self, path: Path) -> bool:
        """Check if path points to a sensitive credential or secret location."""
        try:
            for s in self.sensitive_dirs:
                if path == s or s in path.parents:
                    return True
            # Browser credential files
            name_lower = path.name.lower()
            if name_lower in ("login data", "cookies", "web data", "id_rsa", "id_ed25519", "credentials"):
                return True
        except Exception:
            pass
        return False

    def is_system_path(self, path: Path) -> bool:
        """Check if path is inside Windows or Program Files system directories."""
        try:
            for sys_dir in self.system_dirs:
                if path == sys_dir or sys_dir in path.parents:
                    return True
            if path.name.lower() in self.critical_files:
                return True
        except Exception:
            pass
        return False

    def validate_access(self, raw_path: str, action: str = "read") -> tuple[bool, Path, str]:
        """Validate if the requested action (read, write, delete) is allowed for path.
        
        Returns:
            (allowed: bool, resolved_path: Path, reason: str)
        """
        try:
            resolved = self.resolve_path(raw_path)
        except Exception as e:
            return False, Path(raw_path), f"Invalid path syntax: {e}"

        # 1. Block access to sensitive credential stores
        if self.is_sensitive(resolved):
            return False, resolved, f"Access denied: '{resolved}' is a protected credential/secrets directory."

        # 2. Block write or delete in Windows system directories
        if action in ("write", "edit", "delete", "patch"):
            if self.is_system_path(resolved):
                return False, resolved, f"Access denied: '{resolved}' is a critical Windows system path."

        # 3. Check workspace containment
        in_workspace = self.is_in_workspace(resolved)

        if action == "delete" and resolved == resolved.anchor:
            return False, resolved, "Access denied: Root drive deletion is strictly prohibited."

        return True, resolved, "Allowed" if in_workspace else "Outside workspace"

path_policy = PathPolicy()
