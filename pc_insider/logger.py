"""Structured local logging system with size rotation and credential sanitization."""

import logging
from logging.handlers import RotatingFileHandler
import os
import re
from pathlib import Path
from pc_insider.config import settings

LOG_FILE = Path(settings.logging_config.get("log_file", "pc_insider.log"))
if not LOG_FILE.is_absolute():
    LOG_FILE = Path(settings.workspace_dir) / LOG_FILE

MAX_BYTES = int(settings.logging_config.get("max_bytes", 2097152))
BACKUP_COUNT = int(settings.logging_config.get("backup_count", 3))

# Regex patterns for sensitive data masking
SENSITIVE_PATTERNS = [
    (re.compile(r'(password|passwd|pwd|secret|api_key|token)[\s:=]+["\']?([^"\'\s]+)["\']?', re.IGNORECASE), r'\1=***REDACTED***'),
    (re.compile(r'(sk-[a-zA-Z0-9]{20,})', re.IGNORECASE), r'sk-***REDACTED***'),
    (re.compile(r'(ghp_[a-zA-Z0-9]{20,})', re.IGNORECASE), r'ghp_***REDACTED***'),
    (re.compile(r'(Bearer\s+)[a-zA-Z0-9_\-\.]{15,}', re.IGNORECASE), r'\1***REDACTED***'),
]

def sanitize(text: str) -> str:
    """Mask credentials and sensitive tokens from log messages."""
    if not isinstance(text, str):
        text = str(text)
    for pattern, repl in SENSITIVE_PATTERNS:
        text = pattern.sub(repl, text)
    return text

class SanitizingFormatter(logging.Formatter):
    def format(self, record):
        msg = super().format(record)
        return sanitize(msg)

def get_logger(name: str = "pc_insider") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        try:
            handler = RotatingFileHandler(LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
            formatter = SanitizingFormatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        except Exception:
            # Fallback to null handler if file cannot be opened
            logger.addHandler(logging.NullHandler())
    return logger

logger = get_logger()

def log_tool_invocation(tool_name: str, args: dict, risk_level: str, approved: bool):
    logger.info(f"TOOL_CALL name={tool_name} risk={risk_level} approved={approved} args={sanitize(str(args))}")

def log_tool_result(tool_name: str, success: bool, duration_sec: float, error: str = None):
    status = "SUCCESS" if success else "FAIL"
    err_str = f" error={sanitize(error)}" if error else ""
    logger.info(f"TOOL_RESULT name={tool_name} status={status} duration={duration_sec:.3f}s{err_str}")

def log_verification(action: str, target: str, passed: bool, details: str = ""):
    status = "PASS" if passed else "FAIL"
    logger.info(f"VERIFICATION action={action} target={target} status={status} details={details}")

def log_recovery(trigger: str, action: str, success: bool):
    status = "RESOLVED" if success else "FAILED"
    logger.info(f"RECOVERY trigger={trigger} action={action} status={status}")
