"""Synthetic runner tests; never execute real integration effects."""

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci_test_report.py"
spec = importlib.util.spec_from_file_location("ci_test_report", SCRIPT)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class CITestReportTests(unittest.TestCase):
    def test_functional_counts_and_failing_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "test_synthetic.py").write_text("""import unittest
class Synthetic(unittest.TestCase):
 def test_pass(self): pass
 def test_fail(self): self.fail('PRIVATE_MARKER')
 def test_error(self): raise ValueError('PRIVATE_MARKER')
 @unittest.skip('Optional backend unavailable')
 def test_skip(self): pass
 @unittest.expectedFailure
 def test_expected(self): self.fail('PRIVATE_MARKER')
 @unittest.expectedFailure
 def test_unexpected(self): pass
""")
            output = root / "metrics.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "run",
                    "--start",
                    tmp,
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            metrics = json.loads(output.read_text())
            details = metrics.pop("details")
            self.assertEqual(len(details), 6)
            self.assertEqual(
                metrics,
                {
                    "tests": 6,
                    "passed": 1,
                    "failures": 1,
                    "errors": 1,
                    "skipped": 1,
                    "expected_failures": 1,
                    "unexpected_successes": 1,
                    "success": False,
                },
            )
            text = c.summary(output)
            self.assertIn("FAIL", text)
            self.assertNotIn("PRIVATE_MARKER", text)
            self.assertIn("test_synthetic", text)
            self.assertIn("Per-test results", text)
            self.assertLess(text.index("| failed |"), text.index("| passed |"))

    def test_success_and_import_error_counts(self):
        for source, success in [
            (
                "import unittest\nclass T(unittest.TestCase):\n def test_ok(self): pass\n",
                True,
            ),
            ('raise ImportError("private")', False),
        ]:
            with self.subTest(success=success), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "test_sample.py").write_text(source)
                output = root / "metrics.json"
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "run",
                        "--start",
                        tmp,
                        "--output",
                        str(output),
                    ],
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0 if success else 1)
                data = json.loads(output.read_text())
                self.assertEqual(data["tests"], 1)
                self.assertEqual(data["success"], success)

    def test_coverage_and_append_summary_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metrics = root / "metrics.json"
            metrics.write_text(
                json.dumps(
                    {
                        "tests": 2,
                        "passed": 2,
                        "failures": 0,
                        "errors": 0,
                        "skipped": 0,
                        "expected_failures": 0,
                        "unexpected_successes": 0,
                        "success": True,
                    }
                )
            )
            coverage = root / "coverage.json"
            coverage.write_text(
                json.dumps(
                    {
                        "totals": {"percent_covered": 81.125},
                        "files": {"private.py": "never include"},
                    }
                )
            )
            output = root / "summary.md"
            output.write_text("Earlier summary\n")
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(output)}):
                self.assertEqual(
                    c.main(
                        [
                            "summary",
                            "--metrics",
                            str(metrics),
                            "--coverage",
                            str(coverage),
                        ]
                    ),
                    0,
                )
            text = output.read_text()
            self.assertIn("Earlier summary", text)
            self.assertIn("81.12%", text)
            self.assertIn("PASS", text)
            self.assertNotIn("private.py", text)

    def test_summary_budget_keeps_coverage_failures_and_skips_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            metrics = Path(tmp) / "metrics.json"
            rows = [
                {"status": "passed", "test": f"test_{i}", "checks": "א" * 500}
                for i in range(2000)
            ]
            rows += [
                {
                    "status": "failed",
                    "test": "test_failure",
                    "reason": "AssertionError",
                },
                {
                    "status": "skipped",
                    "test": "test_skip",
                    "reason": "Optional backend",
                },
            ]
            metrics.write_text(json.dumps({"details": rows}))
            text = (
                "## Test results: FAIL\nCoverage: 93.41%\n<details>" + "x" * 1_100_000
            )
            result = c.bounded_summary(text, metrics)
            self.assertLessEqual(len(result.encode("utf-8")), c.SUMMARY_BYTE_LIMIT)
            self.assertIn("93.41%", result)
            self.assertIn("test_failure", result)
            self.assertIn("Optional backend", result)
            self.assertLess(result.index("test_failure"), result.index("test_skip"))
            self.assertLess(result.index("test_skip"), result.index("test_0"))
            self.assertIn("Remaining per-test rows omitted", result)
            self.assertEqual(c.bounded_summary("small", metrics), "small")

    def test_oversized_summary_tolerates_unreadable_or_malformed_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            metrics = Path(tmp) / "metrics.json"
            text = "Coverage: 93.41%\n<details>" + "x" * 1_100_000
            for content in [None, "{bad", "[]", '{"details": [null]}']:
                if content is not None:
                    metrics.write_text(content)
                result = c.bounded_summary(text, metrics)
                self.assertIn("\n\nPer-test details unavailable.", result)
                self.assertIn("93.41%", result)
                self.assertLessEqual(len(result.encode()), c.SUMMARY_BYTE_LIMIT)

    def test_coverage_workflow_measures_imported_package_and_rejects_empty_data(self):
        path = ROOT / ".github/workflows/tests.yml"
        if not path.exists():
            self.skipTest("Source-only workflow excluded from Docker test image")
        text = path.read_text()
        self.assertIn("--source=parking_report ", text)
        self.assertNotIn("--source=src/parking_report", text)
        self.assertIn('t["covered_lines"] > 0', text)
        self.assertIn("            coverage.json", text)

    def test_missing_corrupt_or_non_numeric_input_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.json"
            self.assertIn("unavailable", c.summary(path))
            for content in ["{broken", "{}", json.dumps({"tests": "secret"})]:
                path.write_text(content)
                self.assertIn("unavailable", c.summary(path))
                self.assertNotIn("secret", c.summary(path))

    def test_per_test_reasons_redacted_and_markup_escaped(self):
        text = c.safe_text(
            "<script>alert(1)</script> plate 12345678 user@example.invalid token=abc123 /private/photo.jpg"
        )
        self.assertNotIn("<script>", text)
        self.assertNotIn("12345678", text)
        self.assertNotIn("user@example.invalid", text)
        self.assertNotIn("abc123", text)
        self.assertNotIn("/private/photo.jpg", text)
        self.assertEqual(
            c.safe_text("Optional GPU not available"), "Optional GPU not available"
        )

    def test_workflow_always_publishes_summary_and_preserves_coverage_failure(self):
        path = ROOT / ".github/workflows/tests.yml"
        if not path.exists():
            self.skipTest("Source-only workflow excluded from Docker test image")
        text = path.read_text()
        self.assertIn("scripts/ci_test_report.py run", text)
        self.assertGreaterEqual(text.count("if: ${{ always() }}"), 2)
        self.assertIn("--coverage coverage.json", text)
        self.assertIn('exit "$status"', text)
        # continue-on-error is banned for gating jobs; the single allowed
        # exception is the informational Python 3.15 job (#216), which must
        # never block a merge. Exactly one occurrence, inside py315 only.
        self.assertEqual(text.count("continue-on-error: true"), 1)
        py315 = re.search(r"(?ms)^  py315:.*?(?=^  \w|\Z)", text)
        self.assertIsNotNone(py315, "py315 informational job missing")
        self.assertIn("continue-on-error: true", py315.group(0))


if __name__ == "__main__":
    unittest.main()
