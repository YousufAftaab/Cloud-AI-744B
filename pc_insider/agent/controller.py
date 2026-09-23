"""Agent Controller V2: Dual-mode ReAct loop, context management, verification, and recovery."""

import json
import os
import re
import sys
import time
import urllib.request
from pc_insider.config import settings
from pc_insider.tools.registry import tool_registry
# Ensure tool modules are imported to trigger registration
import pc_insider.tools.filesystem
import pc_insider.tools.shell
import pc_insider.rag.search
from pc_insider.security.gate import security_gate
from pc_insider.agent.context import ContextManager
from pc_insider.agent.planner import planner
from pc_insider.agent.task_state import TaskState
from pc_insider.agent.verifier import verifier
from pc_insider.agent.recovery import recovery_engine
from pc_insider.memory.memory_manager import memory_manager
from pc_insider.memory.profile import pc_profile

# ANSI formatting
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

BASE_SYSTEM_PROMPT = """You are an intelligent, friendly AI companion and autonomous PC assistant running directly on the user's Windows machine.
You have access to tools to inspect files, search code, edit scripts, list directories, and execute PowerShell commands.

Behavior Guidelines:
1. Natural Conversation:
   - For greetings, everyday chat, questions, or brainstorming, respond warmly, naturally, and concisely without invoking tools.
2. Autonomous PC Operations:
   - When asked to inspect, read, write, edit, delete, or run commands on the PC, use your available tools to perform the task accurately.
   - Always verify your work and report clean, helpful summaries once complete.
"""

class AgentController:
    def __init__(self):
        self.context_manager = ContextManager(BASE_SYSTEM_PROMPT)
        self.task_state = TaskState()
        self.conversation_history: list[dict] = []

    def is_conversational_only(self, text: str) -> bool:
        """Fast-path check to route greetings and casual chat away from heavy tool schemas."""
        lower = text.lower().strip()
        if lower.startswith(("/pc", "/tool", "/tools", "pc:", "tool:")):
            return False
        if lower.startswith(("/chat", "/talk", "chat:")):
            return True
        # Common greeting words
        tokens = lower.split()
        if len(tokens) <= 3 and any(g in lower for g in ("hey", "hello", "hi", "howdy", "sup", "good morning", "good evening")):
            return True
        if lower in ("who are you", "what is your name", "how are you", "tell me a joke"):
            return True
        return False

    def stream_ollama(self, messages: list[dict], with_tools: bool = True) -> dict:
        """Send chat completion request to local Ollama with token streaming."""
        payload = {
            "model": settings.model,
            "messages": messages,
            "stream": True,
            "keep_alive": -1,
            "options": {
                "temperature": settings.temperature
            }
        }
        if with_tools:
            payload["tools"] = tool_registry.list_schemas()

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(settings.ollama_url + "/chat", data=data, headers={"Content-Type": "application/json"})

        full_text = []
        suppress_print = False
        first_token_printed = False

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

                    # Suppress console printing if generating structured tool call
                    if "```json" in accumulated or '{"name"' in accumulated or '{ "name"' in accumulated or accumulated.strip().startswith("{"):
                        suppress_print = True

                    if not suppress_print:
                        if not first_token_printed:
                            print(f"{BOLD}{GREEN}Assistant > {RESET}", end="", flush=True)
                            first_token_printed = True
                        sys.stdout.write(token)
                        sys.stdout.flush()

            if first_token_printed and not suppress_print:
                print()

        except Exception as e:
            return {"error": str(e), "full_text": "".join(full_text)}

        return {"full_text": "".join(full_text)}

    def extract_tool_call(self, text: str) -> dict:
        """Extract tool call JSON using balanced-braces parser."""
        known_tools = set(tool_registry._tools.keys())
        # 1. Code blocks
        blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        for b in blocks:
            try:
                p = json.loads(b.strip())
                if isinstance(p, dict) and p.get("name") in known_tools:
                    return p
            except Exception:
                pass

        # 2. Balanced braces
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
                            p = json.loads(text[start:i+1])
                            if isinstance(p, dict) and p.get("name") in known_tools:
                                return p
                        except Exception:
                            break
        return None

    def handle_command(self, cmd_line: str) -> bool:
        """Handle internal CLI slash commands."""
        parts = cmd_line.strip().split(maxsplit=2)
        cmd = parts[0].lower()

        if cmd in ("exit", "quit", "bye"):
            print(f"{GREEN}Assistant >{RESET} Goodbye!")
            sys.exit(0)

        elif cmd == "clear":
            self.conversation_history.clear()
            self.task_state.reset()
            recovery_engine.reset()
            print(f"{YELLOW}[Conversation history and active plan reset]{RESET}\n")
            return True

        elif cmd in ("/profile", "/refresh-profile"):
            refresh = (cmd == "/refresh-profile")
            prof = pc_profile.get_all(refresh=refresh)
            print(f"\n{BOLD}{CYAN}=== PC HARDWARE & RUNTIME PROFILE ==={RESET}")
            for k, v in prof.items():
                print(f"  {k:15s}: {v}")
            print()
            return True

        elif cmd == "/prefs":
            prefs = memory_manager.list_preferences()
            print(f"\n{BOLD}{CYAN}=== USER PREFERENCES (SQLite) ==={RESET}")
            if not prefs:
                print("  (No stored preferences)")
            for k, v in prefs.items():
                print(f"  {k}: {v}")
            print()
            return True

        elif cmd == "/set-pref":
            if len(parts) >= 3:
                key = parts[1]
                val = parts[2]
                memory_manager.set_preference(key, val)
                print(f"{GREEN}Saved preference:{RESET} {key} = {val}\n")
            else:
                print(f"{RED}Usage: /set-pref <key> <value>{RESET}\n")
            return True

        elif cmd == "/history":
            tasks = memory_manager.get_recent_tasks(limit=5)
            print(f"\n{BOLD}{CYAN}=== RECENT TASK HISTORY ==={RESET}")
            for t in tasks:
                print(f"  [{t['created_at']}] [{t['status'].upper()}] {t['goal']} -> {t['summary']}")
            print()
            return True

        return False

    def run_turn(self, user_input: str):
        """Execute one complete user interaction turn."""
        if not user_input.strip():
            return

        if self.handle_command(user_input):
            return

        clean_prompt = user_input.strip()
        if clean_prompt.lower().startswith(("/pc ", "/tool ", "/tools ")):
            clean_prompt = clean_prompt.split(" ", 1)[1]
        elif clean_prompt.lower().startswith(("/chat ", "/talk ")):
            clean_prompt = clean_prompt.split(" ", 1)[1]

        # Check fast conversational path
        if self.is_conversational_only(user_input):
            prompt_msgs = [{"role": "system", "content": BASE_SYSTEM_PROMPT}]
            prompt_msgs.extend(self.conversation_history[-4:])
            prompt_msgs.append({"role": "user", "content": clean_prompt})

            res = self.stream_ollama(prompt_msgs, with_tools=False)
            reply = res.get("full_text", "").strip()
            self.conversation_history.append({"role": "user", "content": clean_prompt})
            self.conversation_history.append({"role": "assistant", "content": reply})
            return

        # Multi-Step Planning Assessment
        if planner.is_complex_goal(clean_prompt):
            self.task_state = planner.build_plan_from_prompt(clean_prompt)
            print(f"{DIM}{self.task_state.format_plan_for_context()}{RESET}\n")
        else:
            self.task_state.reset(goal=clean_prompt)

        self.conversation_history.append({"role": "user", "content": clean_prompt})
        recovery_engine.reset()

        step = 0
        max_steps = settings.max_steps
        task_success = False

        while step < max_steps:
            step += 1
            if step == 1:
                print(f"{DIM}Thinking...{RESET}", end="\r", flush=True)

            # Build context payload with budget controls
            dyn_system_prompt = self.context_manager.build_system_prompt(self.task_state, query=clean_prompt)
            assembled_messages = self.context_manager.prune_and_assemble(dyn_system_prompt, self.conversation_history)

            res = self.stream_ollama(assembled_messages, with_tools=True)
            if "error" in res:
                print(f"\r{RED}[Ollama Error]: {res['error']}{RESET}\n")
                break

            output_text = res.get("full_text", "").strip()
            tool_call = self.extract_tool_call(output_text)

            if not tool_call:
                # Direct conversational conclusion
                self.conversation_history.append({"role": "assistant", "content": output_text})
                task_success = True
                print()
                break

            fn_name = tool_call.get("name")
            fn_args = tool_call.get("arguments", {})
            if isinstance(fn_args, str):
                try:
                    fn_args = json.loads(fn_args)
                except Exception:
                    fn_args = {}

            print(f"\r{BOLD}{YELLOW}[PC Action]{RESET} Running {BOLD}{fn_name}{RESET} with {fn_args}")

            # Execute tool through Security Gate & Registry
            exec_result = tool_registry.execute(fn_name, fn_args)

            # Post-Action Verification Engine
            verif_result = verifier.verify_action(fn_name, fn_args, exec_result)

            if verif_result.passed:
                preview = "Done"
                data = exec_result.get("data")
                if isinstance(data, dict):
                    preview = data.get("message") or data.get("stdout") or str(data)[:80]
                elif data:
                    preview = str(data)[:80]
                print(f"{CYAN}  -> Result [VERIFIED]:{RESET} {preview.strip().splitlines()[0] if preview else 'Success'}\n")

                # Format observation and advance task state
                obs_text = self.context_manager.format_tool_observation(fn_name, exec_result)
                self.conversation_history.append({"role": "assistant", "content": json.dumps(tool_call)})
                self.conversation_history.append({"role": "user", "content": obs_text})
                self.task_state.mark_step_status(self.task_state.current_step_id, "success")
            else:
                # Verification or Tool Execution FAILED -> Deterministic Error Recovery
                print(f"{RED}  -> Verification Failure: {verif_result.message}{RESET}\n")
                recovery_action = recovery_engine.handle_failure(fn_name, fn_args, exec_result, verif_result)

                obs_text = self.context_manager.format_tool_observation(fn_name, exec_result)
                self.conversation_history.append({"role": "assistant", "content": json.dumps(tool_call)})
                feedback = f"{obs_text}\n{recovery_action.feedback_message}"
                self.conversation_history.append({"role": "user", "content": feedback})

                if not recovery_action.can_retry:
                    print(f"{RED}[Halt]: Maximum retries exceeded for this operation.{RESET}\n")
                    break

        # Record task outcome in SQLite Task History
        if self.task_state.goal:
            status = "completed" if task_success else "partial"
            summary = self.conversation_history[-1].get("content", "")[:300] if self.conversation_history else "No summary"
            memory_manager.record_task(self.task_state.goal, status, step, summary)
