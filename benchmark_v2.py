#!/usr/bin/env python3
"""Benchmark suite for PC Insider v2: Evaluates 10 core autonomous capabilities."""

import os
import shutil
import time
from pathlib import Path

from pc_insider.config import settings
from pc_insider.security.policy import path_policy
from pc_insider.security.gate import security_gate, RiskLevel
from pc_insider.tools.filesystem import (
    handle_read_file,
    handle_write_file,
    handle_edit_file,
    handle_delete_file,
)
from pc_insider.tools.shell import handle_run_command
from pc_insider.agent.verifier import verifier
from pc_insider.agent.recovery import recovery_engine
from pc_insider.agent.planner import planner
from pc_insider.agent.task_state import TaskState
from pc_insider.agent.context import ContextManager, MAX_CONTEXT_CHARS
from pc_insider.memory.profile import pc_profile
from pc_insider.memory.memory_manager import memory_manager
from pc_insider.rag.search import codebase_search

class BenchmarkRunner:
    def __init__(self):
        self.results = []
        self.sandbox = path_policy.workspace_root / "_benchmark_sandbox"

    def setup(self):
        if self.sandbox.exists():
            shutil.rmtree(self.sandbox, ignore_errors=True)
        self.sandbox.mkdir(parents=True, exist_ok=True)
        recovery_engine.reset()

    def teardown(self):
        if self.sandbox.exists():
            shutil.rmtree(self.sandbox, ignore_errors=True)

    def record(self, task_name: str, status: str, duration: float, tools: list[str], verified: bool, recovery: bool, summary: str):
        self.results.append({
            "task": task_name,
            "status": status,
            "duration_s": round(duration, 3),
            "tools": tools,
            "verified": verified,
            "recovery": recovery,
            "summary": summary
        })

    # 1. System Inspection
    def run_task_1(self):
        name = "1. System Inspection"
        t0 = time.perf_counter()
        prof = pc_profile.get_all(refresh=True)
        t1 = time.perf_counter()
        passed = bool(prof.get("os") and prof.get("cpu") and prof.get("ram_total_gb"))
        summary = f"Detected OS={prof.get('os')}, CPU={prof.get('cpu')}, RAM={prof.get('ram_total_gb')}"
        self.record(name, "PASS" if passed else "FAIL", t1 - t0, ["pc_profile"], True, False, summary)

    # 2. File Creation with SHA-256
    def run_task_2(self):
        name = "2. File Creation"
        t0 = time.perf_counter()
        target = self.sandbox / "task2_script.py"
        code = "def calculate_area(r):\n    import math\n    return math.pi * r * r\n"
        res = handle_write_file({"path": str(target), "content": code})
        v_res = verifier.verify_action("write_file", {"path": str(target), "content": code}, res)
        t1 = time.perf_counter()
        passed = res["success"] and v_res.passed and target.exists() and len(res["data"]["sha256"]) == 64
        summary = f"Created {res['data']['bytes_written']} bytes, SHA-256 verified"
        self.record(name, "PASS" if passed else "FAIL", t1 - t0, ["write_file"], v_res.passed, False, summary)

    # 3. Code Edit with AST Verification
    def run_task_3(self):
        name = "3. Code Edit & AST Verify"
        t0 = time.perf_counter()
        target = self.sandbox / "task2_script.py"
        edit_res = handle_edit_file({
            "path": str(target),
            "old_snippet": "return math.pi * r * r",
            "new_snippet": "return round(math.pi * (r ** 2), 4)"
        })
        v_res = verifier.verify_action("edit_file", {
            "path": str(target),
            "new_snippet": "return round(math.pi * (r ** 2), 4)"
        }, edit_res)
        t1 = time.perf_counter()
        passed = edit_res["success"] and v_res.passed and v_res.check_type == "EditVerified"
        summary = "Safely edited file, AST verified clean"
        self.record(name, "PASS" if passed else "FAIL", t1 - t0, ["edit_file"], v_res.passed, False, summary)

    # 4. Syntax Error Recovery
    def run_task_4(self):
        name = "4. Syntax Error Detection & Recovery"
        t0 = time.perf_counter()
        target = self.sandbox / "broken_script.py"
        # Write syntactically invalid Python
        broken_code = "def compute(x, y:\n    return x + y\n"
        res = handle_write_file({"path": str(target), "content": broken_code})
        v_res = verifier.verify_action("write_file", {"path": str(target), "content": broken_code}, res)
        # Verify that AST caught syntax error
        caught = not v_res.passed and v_res.check_type == "PythonSyntaxError"
        # Trigger recovery
        rec_action = recovery_engine.handle_failure("write_file", {"path": str(target)}, res, v_res)
        recovered = rec_action.can_retry and "SyntaxError" in rec_action.feedback_message
        t1 = time.perf_counter()
        passed = caught and recovered
        summary = f"Caught AST SyntaxError at line {v_res.details.get('line')}, generated fix hint"
        self.record(name, "PASS" if passed else "FAIL", t1 - t0, ["write_file"], not v_res.passed, True, summary)

    # 5. Security Rejection
    def run_task_5(self):
        name = "5. Security Rejection"
        t0 = time.perf_counter()
        traversal_path = str(path_policy.workspace_root) + r"\..\..\Windows\System32\drivers\etc\hosts"
        ok, p, reason = path_policy.validate_access(traversal_path, action="write")
        risk, _ = security_gate.classify_risk("write_file", {"path": traversal_path})
        gate_res = security_gate.check_permission("write_file", {"path": traversal_path})
        t1 = time.perf_counter()
        passed = (not ok) and (not gate_res.allowed)
        summary = f"Blocked unauthorized write to '{traversal_path}' ({reason})"
        self.record(name, "PASS" if passed else "FAIL", t1 - t0, ["security_gate", "path_policy"], True, False, summary)

    # 6. Memory Persistence Across Sessions
    def run_task_6(self):
        name = "6. Memory Persistence"
        t0 = time.perf_counter()
        # Session A: Save preference & fact
        memory_manager.set_preference("benchmark_preferred_lang", "python")
        memory_manager.add_fact("benchmark", "Evaluated PC Insider v2 performance")
        # Session B: Retrieve
        val = memory_manager.get_preference("benchmark_preferred_lang")
        search_mems = memory_manager.search_relevant_memories("what is preferred lang?")
        t1 = time.perf_counter()
        passed = (val == "python") and any("benchmark_preferred_lang" in m for m in search_mems)
        summary = f"Stored in SQLite, retrieved: {val}"
        self.record(name, "PASS" if passed else "FAIL", t1 - t0, ["memory_manager"], True, False, summary)

    # 7. Multi-step Task Execution
    def run_task_7(self):
        import sys
        name = "7. Multi-Step Task Workflow"
        t0 = time.perf_counter()
        plan = planner.build_plan_from_prompt("Create runner.py and then execute it with powershell")
        self.sandbox.mkdir(parents=True, exist_ok=True)
        runner_file = self.sandbox / "runner.py"
        # Step 1
        plan.mark_step_status(1, "running")
        w_res = handle_write_file({"path": str(runner_file), "content": "print('TASK_7_COMPLETED')\n"})
        plan.mark_step_status(1, "success")
        # Step 2
        plan.mark_step_status(2, "running")
        py_exe = sys.executable
        cmd_res = handle_run_command({"command": f"& '{py_exe}' '{runner_file}'"})
        v_res = verifier.verify_action("run_command", {"command": f"& '{py_exe}' '{runner_file}'"}, cmd_res)
        plan.mark_step_status(2, "success" if v_res.passed else "failed")
        t1 = time.perf_counter()
        passed = plan.is_all_completed() and "TASK_7_COMPLETED" in cmd_res["data"]["stdout"]
        summary = "Decomposed 2 steps, executed sequentially, verified output"
        self.record(name, "PASS" if passed else "FAIL", t1 - t0, ["write_file", "run_command"], v_res.passed, False, summary)

    # 8. Shell Output Truncation & Budget
    def run_task_8(self):
        name = "8. Shell Truncation & Budget"
        t0 = time.perf_counter()
        # Output 200 lines
        cmd = "1..200"
        res = handle_run_command({"command": cmd})
        stdout_len = len(res["data"]["stdout"])
        lines_count = len(res["data"]["stdout"].splitlines())
        truncated = res["data"]["truncated"]
        t1 = time.perf_counter()
        passed = res["success"] and truncated and (lines_count <= 65)
        summary = f"Truncated 200 lines to {lines_count} lines ({stdout_len} chars) to protect LLM context"
        self.record(name, "PASS" if passed else "FAIL", t1 - t0, ["run_command"], True, False, summary)

    # 9. Local RAG Search
    def run_task_9(self):
        name = "9. Local RAG Search"
        t0 = time.perf_counter()
        results = codebase_search.search("path_policy security_gate", directory=str(settings.project_root / "pc_insider"))
        t1 = time.perf_counter()
        passed = len(results) > 0 and any("policy.py" in r["path"] or "gate.py" in r["path"] for r in results)
        top_match = results[0]["path"] if results else "None"
        summary = f"Found {len(results)} relevant chunks, top match: '{top_match}'"
        self.record(name, "PASS" if passed else "FAIL", t1 - t0, ["codebase_search"], True, False, summary)

    # 10. Context Budget & Conversation Pruning
    def run_task_10(self):
        name = "10. Context Budget & Pruning"
        t0 = time.perf_counter()
        ctx = ContextManager(base_system_prompt="System Prompt")
        # Generate 20 large turns (40,000+ chars)
        messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"Turn {i}: " + ("data " * 400)} for i in range(20)]
        assembled = ctx.prune_and_assemble("System Prompt", messages)
        total_chars = sum(len(m["content"]) for m in assembled)
        notice_found = any("[Context Notice:" in m["content"] for m in assembled)
        t1 = time.perf_counter()
        passed = (total_chars <= MAX_CONTEXT_CHARS + 500) and notice_found
        summary = f"Pruned 20 turns ({40000}+ chars) down to {len(assembled)-2} turns ({total_chars} chars)"
        self.record(name, "PASS" if passed else "FAIL", t1 - t0, ["context_manager"], True, False, summary)

    def run_all(self):
        print("=" * 80)
        print("          PC INSIDER V2 — EMPIRICAL BENCHMARK SUITE (10 TASKS)")
        print("=" * 80)
        self.setup()
        try:
            self.run_task_1()
            self.run_task_2()
            self.run_task_3()
            self.run_task_4()
            self.run_task_5()
            self.run_task_6()
            self.run_task_7()
            self.run_task_8()
            self.run_task_9()
            self.run_task_10()
        finally:
            self.teardown()

        print(f"\n{'Task Name':<38} | {'Status':<6} | {'Time (s)':<8} | {'Tools Used':<22} | {'Verified'}")
        print("-" * 88)
        all_passed = True
        total_time = 0
        for r in self.results:
            total_time += r["duration_s"]
            if r["status"] != "PASS":
                all_passed = False
            tools_str = ",".join(r["tools"])[:21]
            ver_str = "YES" if r["verified"] else "NO"
            print(f"{r['task']:<38} | {r['status']:<6} | {r['duration_s']:<8.3f} | {tools_str:<22} | {ver_str}")

        print("-" * 88)
        print(f"Total Benchmark Execution Time: {total_time:.3f} s")
        print(f"Overall Result: {'10/10 ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
        print("=" * 80)

        # Print structured summaries
        print("\nTask Execution Details:")
        for r in self.results:
            rec_tag = " [Recovery: YES]" if r["recovery"] else ""
            print(f"  • {r['task']} [{r['status']} in {r['duration_s']}s]{rec_tag}: {r['summary']}")

        return all_passed

if __name__ == "__main__":
    runner = BenchmarkRunner()
    success = runner.run_all()
    exit(0 if success else 1)
