"""Unit tests for Verifier and RecoveryEngine."""

import shutil
import unittest
from pathlib import Path
from pc_insider.security.policy import path_policy
from pc_insider.agent.verifier import verifier, VerificationResult
from pc_insider.agent.recovery import RecoveryEngine

class TestVerifier(unittest.TestCase):
    def setUp(self):
        self.sandbox = path_policy.workspace_root / "_test_sandbox_verifier"
        if self.sandbox.exists():
            shutil.rmtree(self.sandbox, ignore_errors=True)
        self.sandbox.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.sandbox.exists():
            shutil.rmtree(self.sandbox, ignore_errors=True)

    def test_python_syntax_validation(self):
        # 1. Valid Python
        valid_file = self.sandbox / "valid.py"
        valid_file.write_text("def add(a, b):\n    return a + b\n")
        res = verifier.check_python_syntax(valid_file)
        self.assertTrue(res.passed)
        self.assertEqual(res.check_type, "PythonAST")

        # 2. Invalid Python
        invalid_file = self.sandbox / "invalid.py"
        invalid_file.write_text("def bad_syntax(:\n    return True\n")
        res2 = verifier.check_python_syntax(invalid_file)
        self.assertFalse(res2.passed)
        self.assertEqual(res2.check_type, "PythonSyntaxError")
        self.assertEqual(res2.details.get("line"), 1)

    def test_verify_write_action(self):
        py_file = self.sandbox / "written.py"

        # Valid write
        py_file.write_text("x = 42\n")
        res = verifier.verify_action("write_file", {"path": str(py_file), "content": "x = 42\n"}, {"success": True, "data": {"path": str(py_file)}})
        self.assertTrue(res.passed)

        # Invalid write (corrupt syntax)
        py_file.write_text("x = [1, 2,\n")
        res_bad = verifier.verify_action("write_file", {"path": str(py_file), "content": "x = [1, 2,\n"}, {"success": True, "data": {"path": str(py_file)}})
        self.assertFalse(res_bad.passed)
        self.assertEqual(res_bad.check_type, "PythonSyntaxError")

        # Empty file write when content expected
        py_file.write_text("")
        res_empty = verifier.verify_action("write_file", {"path": str(py_file), "content": "hello world"}, {"success": True, "data": {"path": str(py_file)}})
        self.assertFalse(res_empty.passed)
        self.assertEqual(res_empty.check_type, "FileSize")

    def test_verify_delete_action(self):
        d_file = self.sandbox / "del.txt"
        # 1. File does not exist -> verified deleted
        res = verifier.verify_action("delete_file", {"path": str(d_file)}, {"success": True, "data": {"path": str(d_file)}})
        self.assertTrue(res.passed)

        # 2. File still exists -> verification fails
        d_file.write_text("still here")
        res2 = verifier.verify_action("delete_file", {"path": str(d_file)}, {"success": True, "data": {"path": str(d_file)}})
        self.assertFalse(res2.passed)
        self.assertEqual(res2.check_type, "DeletionCheck")

    def test_verify_command_action(self):
        # Exit code 0
        res = verifier.verify_action("run_command", {"command": "dir"}, {"success": True, "data": {"exit_code": 0}})
        self.assertTrue(res.passed)

        # Exit code non-zero
        res_fail = verifier.verify_action("run_command", {"command": "false"}, {"success": True, "data": {"exit_code": 1}})
        self.assertFalse(res_fail.passed)
        self.assertEqual(res_fail.check_type, "ProcessExitCode")

    def test_recovery_engine_retries_and_hints(self):
        engine = RecoveryEngine(max_retries=2)

        # Test fuzzy filename recovery
        target = self.sandbox / "my_script_v2.py"
        target.write_text("# script")
        wrong_path = self.sandbox / "my_script_v1.py"

        action = engine.handle_failure(
            "read_file",
            {"path": str(wrong_path)},
            {"success": False, "error": {"type": "FileNotFound", "message": f"File '{wrong_path}' not found."}}
        )
        self.assertTrue(action.can_retry)
        self.assertIn("my_script_v2.py", action.feedback_message)

        # Second attempt for same key
        action2 = engine.handle_failure(
            "read_file",
            {"path": str(wrong_path)},
            {"success": False, "error": {"type": "FileNotFound", "message": f"File '{wrong_path}' not found."}}
        )
        self.assertTrue(action2.can_retry)

        # Third attempt exceeds max_retries=2
        action3 = engine.handle_failure(
            "read_file",
            {"path": str(wrong_path)},
            {"success": False, "error": {"type": "FileNotFound", "message": f"File '{wrong_path}' not found."}}
        )
        self.assertFalse(action3.can_retry)
        self.assertIn("Halting to prevent infinite loop", action3.feedback_message)

if __name__ == "__main__":
    unittest.main()
