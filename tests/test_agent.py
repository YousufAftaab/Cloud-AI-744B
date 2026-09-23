"""Unit tests for agent planning, task state, context management, and RAG."""

import shutil
import unittest
from pathlib import Path
from pc_insider.security.policy import path_policy
from pc_insider.agent.task_state import TaskState
from pc_insider.agent.planner import planner
from pc_insider.agent.context import ContextManager, MAX_CONTEXT_CHARS
from pc_insider.rag.search import CodebaseSearch

class TestAgent(unittest.TestCase):
    def setUp(self):
        self.sandbox = path_policy.workspace_root / "_test_sandbox_agent"
        if self.sandbox.exists():
            shutil.rmtree(self.sandbox, ignore_errors=True)
        self.sandbox.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.sandbox.exists():
            shutil.rmtree(self.sandbox, ignore_errors=True)

    def test_task_state_lifecycle(self):
        task = TaskState("Build and test feature")
        self.assertEqual(task.current_step_id, 1)
        self.assertFalse(task.is_active)

        s1 = task.add_step("Create feature.py")
        s2 = task.add_step("Run unit tests")
        self.assertTrue(task.is_active)
        self.assertEqual(len(task.steps), 2)

        # Step 1 starts running
        task.mark_step_status(1, "running")
        self.assertEqual(s1.status, "running")
        self.assertEqual(task.current_step_id, 1)

        # Step 1 succeeds -> current advances to 2
        task.mark_step_status(1, "success")
        self.assertEqual(s1.status, "success")
        self.assertEqual(task.completed_steps, [1])
        self.assertEqual(task.current_step_id, 2)

        # Step 2 fails
        task.mark_step_status(2, "failed")
        self.assertEqual(s2.status, "failed")
        self.assertEqual(task.failed_steps, [2])
        self.assertFalse(task.is_all_completed())

        plan_repr = task.format_plan_for_context()
        self.assertIn("✅ Step 1: Create feature.py [SUCCESS]", plan_repr)
        self.assertIn("❌ Step 2: Run unit tests [FAILED]", plan_repr)

    def test_planner_decomposition(self):
        # 1. Simple queries should not trigger complex planner
        self.assertFalse(planner.is_complex_goal("hello"))
        self.assertFalse(planner.is_complex_goal("what is your name?"))

        # 2. Compound prompts should trigger planner
        compound_prompt = "Create math_utils.py then run it to verify results"
        self.assertTrue(planner.is_complex_goal(compound_prompt))

        plan = planner.build_plan_from_prompt(compound_prompt)
        self.assertEqual(len(plan.steps), 2)
        self.assertIn("math_utils.py", plan.steps[0].description)
        self.assertIn("verify results", plan.steps[1].description)

    def test_context_manager_pruning(self):
        ctx = ContextManager(base_system_prompt="You are PC Insider v2.")

        # Test dynamic prompt assembly
        task = TaskState("Refactor module")
        task.add_step("Inspect old module")
        sys_prompt = ctx.build_system_prompt(task_state=task)
        self.assertIn("You are PC Insider v2", sys_prompt)
        self.assertIn("Machine Profile", sys_prompt)
        self.assertIn("Refactor module", sys_prompt)

        # Test context pruning with massive history
        large_chunk = "x" * 2000
        messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"Turn {i}: {large_chunk}"} for i in range(15)]

        pruned = ctx.prune_and_assemble(sys_prompt, messages)
        # Total chars in pruned must stay within safe limits
        total_len = sum(len(m["content"]) for m in pruned)
        self.assertLessEqual(total_len, MAX_CONTEXT_CHARS + 2000)

        # Check notice inserted
        has_notice = any("Context Notice:" in m["content"] for m in pruned)
        self.assertTrue(has_notice)

    def test_codebase_search_rag(self):
        doc1 = self.sandbox / "guide.md"
        doc1.write_text("# Offline Assistant Guide\nThis system operates completely local without cloud APIs.")
        doc2 = self.sandbox / "notes.txt"
        doc2.write_text("Random irrelevant text here.")

        searcher = CodebaseSearch(root_dir=self.sandbox)
        results = searcher.search("offline local assistant", directory=str(self.sandbox))
        self.assertTrue(len(results) >= 1)
        self.assertIn("guide.md", results[0]["path"])
        self.assertIn("Offline Assistant Guide", results[0]["snippet"])

if __name__ == "__main__":
    unittest.main()
