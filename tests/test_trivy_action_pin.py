"""No network/credentials: enforce official Trivy fixed GitHub Actions pin."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SECURITY = ROOT / ".github/workflows/security.yml"
PIN = "57a97c7e7821a5776cebc9bb87c984fa69cba8f1"


class TrivyPinContract(unittest.TestCase):
    def test_fixed_verifiable_commit_only(self):
        content = SECURITY.read_text(encoding="utf-8")
        actual = re.findall(r"(?m)^\s+uses:\s+aquasecurity/trivy-action@([^\s#]+)", content)
        self.assertEqual(actual, [PIN])

    def test_rejected_vulnerable_trivy_release(self):
        content = SECURITY.read_text(encoding="utf-8")
        self.assertNotIn("aquasecurity/trivy-action@0.12.0", content)
        self.assertIn("scan-type: fs", content)
        self.assertIn("severity: CRITICAL,HIGH", content)
        self.assertIn("exit-code: 1", content)

    def test_security_workflow_has_no_push_trigger(self):
        content = SECURITY.read_text(encoding="utf-8")
        self.assertNotRegex(content, r"(?m)^  push:\s*")


if __name__ == "__main__":
    unittest.main()
