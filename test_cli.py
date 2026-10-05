"""End-to-end tests of the real CLI using isolated temporary files."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("parking_report.py")
CAR = {"plate": "00-000-00", "street": "Example 1", "datetime": "2026-01-02 03:04"}


class TestCLI(unittest.TestCase):
    def run_cli(self, content, *options):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(content, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT), str(path), *options],
                capture_output=True, text=True, encoding="utf-8", timeout=10,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )

    def test_success_with_options(self):
        result = self.run_cli(json.dumps([CAR]), "--city", "Example City",
                              "--name", "Example Reporter", "--no-photo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("Example City", result.stdout)
        self.assertIn("Example Reporter", result.stdout)
        self.assertNotIn("מצורפת תמונה", result.stdout)

    def test_multiple_reports_separated(self):
        result = self.run_cli(json.dumps([CAR, {**CAR, "plate": "11-111-11"}]))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.strip().split("\n\n")), 2)

    def test_empty_list(self):
        result = self.run_cli("[]")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def test_invalid_inputs_fail_cleanly(self):
        for content in ("{bad json", "{}", "[null]", '[{"plate": null}]',
                        json.dumps([CAR, {**CAR, "datetime": "invalid"}])):
            with self.subTest(content=content):
                result = self.run_cli(content)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("error:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_missing_file_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(Path(directory) / "missing.json")],
                capture_output=True, text=True, timeout=10,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_help(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--no-photo", result.stdout)


class TestValidation(unittest.TestCase):
    def test_required_fields_are_nonempty_strings(self):
        import parking_report as pr
        for field in pr.REQUIRED:
            for value in (None, 123, "", "   "):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, field):
                        pr.build_report({**CAR, field: value})

    def test_invalid_records(self):
        import parking_report as pr
        for value in (None, [], "car", 42):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "JSON object"):
                    pr.build_report(value)

    def test_optional_null_fields(self):
        import parking_report as pr
        report = pr.build_report({**CAR, "notes": None, "car_type": None})
        self.assertNotIn("None", report)
        self.assertIn("בחניה אסורה", report)

    def test_error_identifies_record(self):
        import parking_report as pr
        with self.assertRaisesRegex(ValueError, "car 2:"):
            pr.build_reports([CAR, {}])

    def test_date_edges(self):
        import parking_report as pr
        self.assertEqual(pr.format_datetime(" 2024-02-29T23:59 "), "29.2.2024, 23:59")
        for value in ("2025-02-29 10:00", "2026-01-01 24:00", "2026-13-01 00:00"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    pr.format_datetime(value)

    def test_input_is_not_mutated(self):
        import parking_report as pr
        record = {**CAR, "plate": " 00-000-00 "}
        original = record.copy()
        self.assertIn("00-000-00", pr.build_report(record))
        self.assertEqual(record, original)


if __name__ == "__main__":
    unittest.main()
