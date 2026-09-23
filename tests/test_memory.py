"""Unit tests for SQLite persistent memory and PC profile."""

import unittest
from pc_insider.memory.db import db
from pc_insider.memory.memory_manager import memory_manager
from pc_insider.memory.profile import pc_profile

class TestMemory(unittest.TestCase):
    def setUp(self):
        # Ensure tables exist
        db.init_tables()

    def test_preferences_storage_and_update(self):
        memory_manager.set_preference("editor", "vscode")
        val = memory_manager.get_preference("editor")
        self.assertEqual(val, "vscode")

        # Update existing
        memory_manager.set_preference("editor", "neovim")
        val2 = memory_manager.get_preference("editor")
        self.assertEqual(val2, "neovim")

        # Default fallback
        non_val = memory_manager.get_preference("nonexistent_key", default="default_val")
        self.assertEqual(non_val, "default_val")

        prefs = memory_manager.list_preferences()
        self.assertIn("editor", prefs)
        self.assertEqual(prefs["editor"], "neovim")

    def test_facts_storage(self):
        memory_manager.add_fact("hardware", "User has 16GB RAM installed")
        facts = memory_manager.list_facts(category="hardware")
        self.assertTrue(len(facts) >= 1)
        self.assertIn("16GB RAM", facts[0]["fact"])

    def test_task_history(self):
        memory_manager.record_task(
            goal="Upgrade assistant to v2",
            status="success",
            steps_count=4,
            summary="Implemented all modular components"
        )
        recent = memory_manager.get_recent_tasks(limit=3)
        self.assertTrue(len(recent) >= 1)
        self.assertEqual(recent[0]["goal"], "Upgrade assistant to v2")
        self.assertEqual(recent[0]["status"], "success")

    def test_keyword_memory_retrieval(self):
        memory_manager.set_preference("shell_theme", "dark_mode")
        memory_manager.add_fact("project", "Colibri is a local offline assistant")

        # Search for keyword "theme"
        res_theme = memory_manager.search_relevant_memories("what is my current theme?")
        self.assertTrue(any("shell_theme = dark_mode" in m for m in res_theme))

        # Search for keyword "colibri"
        res_colibri = memory_manager.search_relevant_memories("tell me about colibri")
        self.assertTrue(any("Colibri" in m for m in res_colibri))

    def test_pc_profile_probe_and_summary(self):
        prof = pc_profile.get_all(refresh=True)
        self.assertIn("os", prof)
        self.assertIn("cpu", prof)
        self.assertIn("ram_total_gb", prof)
        self.assertIn("disk_c_free_gb", prof)

        summary = pc_profile.to_compact_summary()
        self.assertIn("Machine Profile", summary)
        self.assertIn("CPU", summary)
        self.assertIn("RAM", summary)

if __name__ == "__main__":
    unittest.main()
