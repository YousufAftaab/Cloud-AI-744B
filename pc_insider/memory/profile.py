"""Machine profile: hardware, OS, and runtime detection with SQLite caching."""

import os
import platform
import subprocess
import shutil
from pathlib import Path
from pc_insider.memory.db import db

class PCProfile:
    def __init__(self):
        self.cached = False

    def get_all(self, refresh: bool = False) -> dict[str, str]:
        """Get machine profile, using SQLite cache if available."""
        if not refresh:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT key, value FROM pc_profile")
                rows = cursor.fetchall()
                if rows:
                    return {r["key"]: r["value"] for r in rows}

        # Probe system metrics
        profile = self._probe()
        # Save to SQLite
        with db.get_connection() as conn:
            cursor = conn.cursor()
            for k, v in profile.items():
                cursor.execute(
                    "INSERT INTO pc_profile (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
                    (k, v)
                )
            conn.commit()
        return profile

    def _probe(self) -> dict[str, str]:
        prof = {}
        # OS & Arch
        prof["os"] = f"{platform.system()} {platform.release()} ({platform.version()})"
        prof["arch"] = platform.machine()
        prof["python"] = platform.python_version()

        # CPU info
        prof["cpu"] = platform.processor() or "x86_64"
        try:
            cmd = 'Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name'
            r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                prof["cpu"] = r.stdout.strip()
        except Exception:
            pass

        # Total RAM
        try:
            cmd = '[math]::round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 2)'
            r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                prof["ram_total_gb"] = f"{r.stdout.strip()} GB"
        except Exception:
            prof["ram_total_gb"] = "16 GB"

        # Drive C: Free space
        try:
            total, used, free = shutil.disk_usage("C:\\")
            prof["disk_c_free_gb"] = f"{free / (1024**3):.1f} GB"
        except Exception:
            pass

        # Development Tools
        prof["git"] = "Not found"
        try:
            r = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=3)
            if r.returncode == 0:
                prof["git"] = r.stdout.strip()
        except Exception:
            pass

        return prof

    def to_compact_summary(self) -> str:
        """Format a compact 2-line machine summary for system prompt context."""
        p = self.get_all()
        os_str = p.get("os", "Windows 11")
        cpu_str = p.get("cpu", "Intel Core i3")
        ram_str = p.get("ram_total_gb", "16 GB")
        disk_str = p.get("disk_c_free_gb", "20+ GB")
        py_str = p.get("python", "3.12")
        return f"[Machine Profile: {os_str} | CPU: {cpu_str} | RAM: {ram_str} | Disk C: Free: {disk_str} | Python: {py_str}]"

pc_profile = PCProfile()
