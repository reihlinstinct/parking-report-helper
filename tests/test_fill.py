"""Tests for the optional browser fill helper, run against a local mock form only."""
import json
from pathlib import Path
import tempfile
import unittest

from parking_report.fill import FillError, check_attachments, check_url, fill_form
from parking_report.municipality import build_submission, load_config

try:
    import playwright.sync_api  # noqa: F401
    HAVE_PLAYWRIGHT = True
except ImportError:
    HAVE_PLAYWRIGHT = False

MOCK = (Path(__file__).parent / "fixtures" / "mock_106_form.html").resolve()
CAR = {"plate": "00-000-00", "street": "Example 12", "datetime": "2026-01-02 03:04"}
REPORTER = {
    "first_name": "A", "last_name": "B", "id_type": "דרכון",
    "id_number": "000000000", "phone": "0500000000", "email": "a@example.com",
}


class TestChecks(unittest.TestCase):
    def setUp(self):
        self.config = load_config("jerusalem")

    def test_url_allowlist(self):
        self.assertTrue(check_url(self.config["channel"]["url"], self.config))
        self.assertTrue(check_url(MOCK.as_uri(), self.config))
        self.assertTrue(check_url("http://localhost:8000/x", self.config))
        for bad in ("https://example.com/form", "http://evil.localhost.example/"):
            with self.assertRaises(FillError):
                check_url(bad, self.config)

    def test_attachment_limits(self):
        with tempfile.TemporaryDirectory() as d:
            ok = Path(d, "a.jpg"); ok.write_bytes(b"x")
            bad = Path(d, "a.exe"); bad.write_bytes(b"x")
            big = Path(d, "b.png"); big.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
            self.assertEqual(len(check_attachments([str(ok)], self.config)), 1)
            for paths in ([str(bad)], [str(big)], [str(Path(d, "none.jpg"))], [str(ok)] * 4):
                with self.assertRaises(FillError):
                    check_attachments(paths, self.config)


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright extra not installed")
class TestFillMockForm(unittest.TestCase):
    def test_fills_fields_and_never_submits(self):
        from playwright.sync_api import sync_playwright
        import parking_report.fill as fill

        config = load_config("jerusalem")
        rows = build_submission(CAR, config, REPORTER)
        with tempfile.TemporaryDirectory() as d:
            photo = Path(d, "p.jpg"); photo.write_bytes(b"\xff\xd8\xff")
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(MOCK.as_uri())
                report = fill.fill_page(page, config, rows, [str(photo)])
                values = page.evaluate(
                    """() => ({a: a.value, b: b.value, c: c.value, d: d.value, e: e.value,
                      e2: e2.value, g: g.value, h: h.value, i: i.value, j: j.value,
                      k: k.value, files: files.files.length,
                      submitted: window.__submitted === true})"""
                )
                browser.close()
        self.assertEqual(values["a"], "A")
        self.assertEqual(values["c"], "דרכון")
        self.assertEqual(values["h"], "ירושלים")
        self.assertEqual(values["i"], "Example")
        self.assertEqual(values["j"], "12")
        self.assertIn("00-000-00", values["k"])
        self.assertEqual(values["e2"], "")
        self.assertEqual(values["files"], 1)
        self.assertFalse(values["submitted"])
        self.assertIn("phone2", report["skipped"])
        self.assertEqual(report["not_found"], [])

    def test_fill_form_entry_point(self):
        config = load_config("jerusalem")
        rows = build_submission(CAR, config, REPORTER)
        report = fill_form(config, rows, url=MOCK.as_uri(), headless=True, wait_for_user=False)
        self.assertIn("first_name", report["filled"])

    def test_missing_values_left_blank(self):
        config = load_config("jerusalem")
        rows = build_submission(CAR, config, {})
        report = fill_form(config, rows, url=MOCK.as_uri(), headless=True, wait_for_user=False)
        self.assertIn("first_name", report["skipped"])

    def test_no_submit_calls_in_source(self):
        source = Path(fill_source()).read_text(encoding="utf-8")
        for forbidden in (".click(", ".submit(", "press(", "requestSubmit", "recaptcha"):
            self.assertNotIn(forbidden, source.replace("never submits", ""))


def fill_source():
    import parking_report.fill as fill
    return fill.__file__


if __name__ == "__main__":
    unittest.main()
