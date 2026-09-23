#!/usr/bin/env python3
"""PC Insider v2 — Autonomous 100% Offline Local PC Assistant.

Architecture:
- Central Security Gate (LOW / MEDIUM / HIGH / CRITICAL)
- Filesystem Policy (Workspace, Protected Paths, Traversal Prevention)
- Centralized Tool Registry with Structured Results
- Verification Engine (AST syntax checks, file existence, exit codes)
- Deterministic Error Recovery (Fuzzy filename search, bounded retries)
- SQLite Persistent Memory (Preferences, Profile, Projects, Task History)
- Context Management (Budgeting within 4096 tokens, condensation)
- Local Codebase Search (RAG without heavy vector DBs)
- Fast-Path Conversational Token Streaming
"""

import sys
import os

# Ensure project root is in Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Ensure UTF-8 output on Windows terminal
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pc_insider.config import settings
from pc_insider.agent.controller import (
    AgentController,
    CYAN, GREEN, YELLOW, RED, BOLD, DIM, RESET
)

def main():
    os.system("")  # Enable ANSI in Windows terminal

    print(f"\n{BOLD}{CYAN}==============================================================================={RESET}")
    print(f"{BOLD}{CYAN}            PC INSIDER v2.0 — AUTONOMOUS 100% OFFLINE LOCAL AGENT{RESET}")
    print(f"{BOLD}{CYAN}==============================================================================={RESET}")
    print(f"{GREEN}Model:{RESET} {settings.model} | {GREEN}Engine:{RESET} Ollama AVX2 CPU | {GREEN}Memory:{RESET} SQLite Persistent")
    print(f"{GREEN}Workspace:{RESET} {settings.workspace_dir} | {GREEN}Security Gate:{RESET} Active")
    print(f"{DIM}Commands: 'clear' to reset | 'exit' to quit | '/profile' for specs | '/prefs' for memories{RESET}")
    print(f"{BOLD}{CYAN}==============================================================================={RESET}\n")

    controller = AgentController()

    while True:
        try:
            user_input = input(f"{BOLD}{CYAN}You > {RESET}")
        except (KeyboardInterrupt, EOFError):
            print(f"\n{GREEN}Assistant >{RESET} Goodbye!")
            break

        try:
            controller.run_turn(user_input)
        except Exception as e:
            print(f"\n{RED}[Controller Exception]: {e}{RESET}\n")

if __name__ == "__main__":
    main()
