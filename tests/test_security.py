"""Security and policy unit tests."""

import unittest
from pathlib import Path
from pc_insider.security.policy import path_policy
from pc_insider.security.gate import security_gate, RiskLevel

class TestSecurity(unittest.TestCase):
    def test_workspace_containment(self):
        in_p = path_policy.workspace_root / "test_file.txt"
        self.assertTrue(path_policy.is_in_workspace(in_p))

    def test_path_traversal_prevention(self):
        traversal_path = str(path_policy.workspace_root) + r"\..\..\Windows\System32\cmd.exe"
        resolved = path_policy.resolve_path(traversal_path)
        self.assertNotIn("..", str(resolved))
        # Writing to system directory must be blocked
        ok, p, reason = path_policy.validate_access(traversal_path, action="write")
        self.assertFalse(ok)
        self.assertIn("Access denied", reason)

    def test_sensitive_credential_protection(self):
        ssh_path = str(Path.home() / ".ssh" / "id_rsa")
        ok, p, reason = path_policy.validate_access(ssh_path, action="read")
        self.assertFalse(ok)
        self.assertIn("Access denied", reason)

    def test_risk_classification(self):
        # 1. Read is LOW
        risk, _ = security_gate.classify_risk("read_file", {"path": "test.txt"})
        self.assertEqual(risk, RiskLevel.LOW)

        # 2. Write in workspace is MEDIUM
        risk, _ = security_gate.classify_risk("write_file", {"path": "test.txt", "content": "hello"})
        self.assertEqual(risk, RiskLevel.MEDIUM)

        # 3. Kill process is HIGH
        risk, _ = security_gate.classify_risk("run_command", {"command": "Stop-Process -Id 1234"})
        self.assertEqual(risk, RiskLevel.HIGH)

        # 4. Dangerous disk wipe is CRITICAL
        risk, _ = security_gate.classify_risk("run_command", {"command": "Format-Volume -DriveLetter D"})
        self.assertEqual(risk, RiskLevel.CRITICAL)

        # 5. Directory deletion is CRITICAL
        risk, _ = security_gate.classify_risk("delete_file", {"path": str(path_policy.workspace_root)})
        self.assertEqual(risk, RiskLevel.CRITICAL)

    def test_permission_gate_auto_approve_low(self):
        res = security_gate.check_permission("read_file", {"path": "test.txt"})
        self.assertTrue(res.allowed)
        self.assertEqual(res.risk, RiskLevel.LOW)

if __name__ == "__main__":
    unittest.main()
