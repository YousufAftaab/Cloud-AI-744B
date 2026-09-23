"""Configuration loader and settings manager for PC Insider v2."""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"

DEFAULT_CONFIG = {
    "model": "qwen2.5-coder:7b",
    "ollama_url": "http://127.0.0.1:11434/api",
    "temperature": 0.2,
    "context_limit_tokens": 4096,
    "max_steps": 6,
    "max_retries": 2,
    "workspace_dir": str(BASE_DIR),
    "security": {
        "require_confirmation_medium": False,
        "require_confirmation_high": True,
        "require_confirmation_critical": True,
        "block_critical_system_paths": True,
    },
    "logging": {
        "log_file": "pc_insider.log",
        "log_level": "INFO",
        "max_bytes": 2097152,
        "backup_count": 3,
    },
    "memory": {
        "db_file": "pc_insider_memory.db",
    },
}

class Settings:
    def __init__(self, config_path: Path = CONFIG_PATH):
        self.config_path = config_path
        self.data = self._load()

    def _load(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    user_cfg = json.load(f)
                    cfg = DEFAULT_CONFIG.copy()
                    for k, v in user_cfg.items():
                        if isinstance(v, dict) and k in cfg and isinstance(cfg[k], dict):
                            cfg[k].update(v)
                        else:
                            cfg[k] = v
                    return cfg
            except Exception:
                pass
        return DEFAULT_CONFIG.copy()

    @property
    def model(self) -> str:
        return self.data.get("model", "qwen2.5-coder:7b")

    @property
    def ollama_url(self) -> str:
        return self.data.get("ollama_url", "http://127.0.0.1:11434/api")

    @property
    def temperature(self) -> float:
        return float(self.data.get("temperature", 0.2))

    @property
    def context_limit_tokens(self) -> int:
        return int(self.data.get("context_limit_tokens", 4096))

    @property
    def max_steps(self) -> int:
        return int(self.data.get("max_steps", 6))

    @property
    def max_retries(self) -> int:
        return int(self.data.get("max_retries", 2))

    @property
    def project_root(self) -> Path:
        return BASE_DIR

    @property
    def workspace_dir(self) -> Path:
        raw = self.data.get("workspace_dir", str(BASE_DIR))
        return Path(raw).resolve()

    @property
    def security(self) -> dict:
        return self.data.get("security", DEFAULT_CONFIG["security"])

    @property
    def logging_config(self) -> dict:
        return self.data.get("logging", DEFAULT_CONFIG["logging"])

    @property
    def memory_db_path(self) -> Path:
        db_file = self.data.get("memory", {}).get("db_file", "pc_insider_memory.db")
        p = Path(db_file)
        if not p.is_absolute():
            p = BASE_DIR / p
        return p

settings = Settings()
