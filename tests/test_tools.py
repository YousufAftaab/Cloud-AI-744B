"""Unit tests for filesystem and shell tools."""

import os
import shutil
import unittest
from pathlib import Path
from pc_insider.security.policy import path_policy
from pc_insider.tools.filesystem import (
    handle_read_file,
    handle_write_file,
    handle_edit_file,
    handle_patch_file,
    handle_delete_file,
    handle_list_directory,
    handle_search_files,
)
from pc_insider.tools.shell import handle_run_command

class TestTools(unittest.TestCase):
    def setUp(self):
        # Create a clean temporary directory in workspace
        self.sandbox = path_policy.workspace_root / "_test_sandbox_tools"
        if self.sandbox.exists():
            shutil.rmtree(self.sandbox, ignore_errors=True)
        self.sandbox.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.sandbox.exists():
            shutil.rmtree(self.sandbox, ignore_errors=True)

    def test_write_and_read_file(self):
        target = self.sandbox / "sample.txt"
        content = "Line 1: Hello\nLine 2: World\nLine 3: Foo\nLine 4: Bar"

        # 1. Write file
        w_res = handle_write_file({"path": str(target), "content": content})
        self.assertTrue(w_res["success"])
        self.assertEqual(w_res["data"]["bytes_written"], len(content.encode("utf-8")))
        self.assertTrue(target.exists())
        self.assertTrue(len(w_res["data"]["sha256"]) == 64)

        # 2. Read whole file
        r_res = handle_read_file({"path": str(target)})
        self.assertTrue(r_res["success"])
        self.assertEqual(r_res["data"]["total_lines"], 4)
        self.assertIn("Line 1: Hello", r_res["data"]["content"])

        # 3. Read paginated (lines 2 to 3)
        r_pag = handle_read_file({"path": str(target), "start_line": 2, "end_line": 3})
        self.assertTrue(r_pag["success"])
        self.assertEqual(r_pag["data"]["lines_count"], 2)
        self.assertIn("Line 2: World", r_pag["data"]["content"])
        self.assertIn("Line 3: Foo", r_pag["data"]["content"])
        self.assertNotIn("Line 1: Hello", r_pag["data"]["content"])

    def test_edit_file(self):
        target = self.sandbox / "code.py"
        initial_code = "def greet():\n    msg = 'hello'\n    return msg\n"
        handle_write_file({"path": str(target), "content": initial_code})

        # 1. Edit single match
        e_res = handle_edit_file({
            "path": str(target),
            "old_snippet": "msg = 'hello'",
            "new_snippet": "msg = 'greetings'"
        })
        self.assertTrue(e_res["success"])
        self.assertIn("greetings", target.read_text(encoding="utf-8"))

        # 2. Snippet not found error
        e_err = handle_edit_file({
            "path": str(target),
            "old_snippet": "nonexistent snippet",
            "new_snippet": "anything"
        })
        self.assertFalse(e_err["success"])
        self.assertEqual(e_err["error"]["type"], "SnippetNotFound")

        # 3. Multiple matches safety guard
        multi_file = self.sandbox / "multi.txt"
        handle_write_file({"path": str(multi_file), "content": "alpha beta alpha gamma alpha"})
        m_err = handle_edit_file({
            "path": str(multi_file),
            "old_snippet": "alpha",
            "new_snippet": "omega"
        })
        self.assertFalse(m_err["success"])
        self.assertEqual(m_err["error"]["type"], "MultipleMatches")

        # 4. Multiple matches with allow_multiple=True
        m_ok = handle_edit_file({
            "path": str(multi_file),
            "old_snippet": "alpha",
            "new_snippet": "omega",
            "allow_multiple": True
        })
        self.assertTrue(m_ok["success"])
        self.assertEqual(m_ok["data"]["replacements_made"], 3)
        self.assertNotIn("alpha", multi_file.read_text(encoding="utf-8"))

    def test_delete_file_and_directory(self):
        f = self.sandbox / "to_delete.txt"
        handle_write_file({"path": str(f), "content": "temp"})
        self.assertTrue(f.exists())

        d_res = handle_delete_file({"path": str(f)})
        self.assertTrue(d_res["success"])
        self.assertFalse(f.exists())

        # Non-existent file deletion returns success with notice
        d_res2 = handle_delete_file({"path": str(f)})
        self.assertTrue(d_res2["success"])

        # Directory deletion
        sub = self.sandbox / "subdir"
        sub.mkdir()
        (sub / "subfile.txt").write_text("sub")
        d_dir = handle_delete_file({"path": str(sub)})
        self.assertTrue(d_dir["success"])
        self.assertFalse(sub.exists())

    def test_list_directory_and_search(self):
        (self.sandbox / "file_a.txt").write_text("apple banana cherry")
        (self.sandbox / "file_b.py").write_text("def find_me(): pass")
        (self.sandbox / "subfolder").mkdir()

        # List directory
        l_res = handle_list_directory({"path": str(self.sandbox)})
        self.assertTrue(l_res["success"])
        self.assertIn("file_a.txt", l_res["data"]["output"])
        self.assertIn("file_b.py", l_res["data"]["output"])
        self.assertIn("<DIR>", l_res["data"]["output"])

        # Search by pattern
        s_pat = handle_search_files({"directory": str(self.sandbox), "filename_pattern": "*.py"})
        self.assertTrue(s_pat["success"])
        self.assertEqual(len(s_pat["data"]["results"]), 1)
        self.assertEqual(s_pat["data"]["results"][0]["path"], "file_b.py")

        # Search by content
        s_cnt = handle_search_files({"directory": str(self.sandbox), "content_query": "banana"})
        self.assertTrue(s_cnt["success"])
        self.assertEqual(len(s_cnt["data"]["results"]), 1)
        self.assertEqual(s_cnt["data"]["results"][0]["path"], "file_a.txt")

    def test_run_command_execution(self):
        # Successful command
        cmd_res = handle_run_command({"command": "Write-Output 'PowerShell Unit Test'"})
        self.assertTrue(cmd_res["success"])
        self.assertEqual(cmd_res["data"]["exit_code"], 0)
        self.assertIn("PowerShell Unit Test", cmd_res["data"]["stdout"])

        # Failing command (non-zero exit code)
        fail_res = handle_run_command({"command": "Write-Error 'TestError'; exit 7"})
        self.assertEqual(fail_res["data"]["exit_code"], 7)

if __name__ == "__main__":
    unittest.main()
