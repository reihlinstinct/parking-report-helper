"""Functional tests of the browser helpers against a local fake municipal site.

No real municipality traffic: the live 106 site answers 403 to cloud IPs, so every
scenario (form, HTTP block, captcha wall) is served by FakeSite.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from parking_report.fill import FillError, fill_form, fill_page
from parking_report.municipality import build_submissions, load_config

from support import HAVE_PLAYWRIGHT, REPORTER, SAMPLE, FakeSite

CARS = json.loads(SAMPLE.read_text(encoding="utf-8"))
FIELD_IDS = {"first_name": "a", "last_name": "b", "id_number": "d", "phone": "e",
             "email": "g", "city": "h", "street": "i", "house_number": "j",
             "description": "k"}


def config_for(url):
    config = copy.deepcopy(load_config("jerusalem"))
    config["channel"]["url"] = url
    return config


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright extra not installed")
class TestFillEndToEnd(unittest.TestCase):
    def test_sample_input_to_filled_form_without_submitting(self):
        from playwright.sync_api import sync_playwright

        with FakeSite() as site, tempfile.TemporaryDirectory() as d:
            config = config_for(site.url("/form"))
            rows = build_submissions(CARS, config, REPORTER)[0]
            photo = Path(d, "photo.jpg")
            photo.write_bytes(b"\xff\xd8\xff")
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.goto(site.url("/form"))
                    report = fill_page(page, config, rows, [str(photo)])
                    values = {k: page.input_value("#" + i) for k, i in FIELD_IDS.items()}
                    id_type = page.input_value("#c")
                    uploaded = page.eval_on_selector("#files", "e => e.files.length")
                    submitted = page.evaluate("window.__submitted === true")
                finally:
                    browser.close()
        self.assertEqual(report["not_found"], [])
        self.assertEqual(values["first_name"], "דנה")
        self.assertEqual(values["street"], "הדוגמה")
        self.assertEqual(values["house_number"], "1")
        self.assertIn("00-000-00", values["description"])
        self.assertEqual(id_type, "תעודת זהות")
        self.assertEqual(uploaded, 1)
        self.assertFalse(submitted, "the helper must never submit the form")
        self.assertEqual([m for m, _ in site.requests if m != "GET"], [])

    def test_missing_reporter_details_leave_fields_blank(self):
        from playwright.sync_api import sync_playwright

        with FakeSite() as site:
            config = config_for(site.url("/form"))
            rows = build_submissions(CARS, config, {})[0]
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.goto(site.url("/form"))
                    report = fill_page(page, config, rows)
                    first_name = page.input_value("#a")
                finally:
                    browser.close()
        self.assertEqual(first_name, "")
        self.assertIn("first_name", report["skipped"])

    def test_fill_form_refuses_a_non_local_unofficial_url_before_launching(self):
        config = load_config("jerusalem")
        rows = build_submissions(CARS, config, REPORTER)[0]
        with self.assertRaises(FillError):
            fill_form(config, rows, url="https://example.com/form", wait_for_user=False)


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright extra not installed")
class TestInspectEndToEnd(unittest.TestCase):
    def inspect(self, route):
        from parking_report.inspect import inspect_form

        with FakeSite() as site:
            result = inspect_form(config_for(site.url(route)))
            return result, site.requests

    def test_http_block_is_reported_and_not_retried(self):
        result, requests = self.inspect("/blocked")
        self.assertEqual(result["http_status"], 403)
        self.assertEqual(result["result"], "blocked_or_http_error")
        self.assertEqual(requests, [("GET", "/blocked")])

    def test_captcha_wall_stops_without_touching_it(self):
        result, requests = self.inspect("/captcha")
        self.assertEqual(result["result"], "verification_present_stopped")
        self.assertEqual(requests, [("GET", "/captcha")])

    def test_open_form_reports_every_configured_field(self):
        result, requests = self.inspect("/form")
        self.assertEqual(result["result"], "inspected")
        self.assertEqual(result["not_found"], [])
        self.assertEqual(len(result["found"]), len(load_config("jerusalem")["fields"]))
        self.assertEqual([m for m, _ in requests if m != "GET"], [])

    def test_page_without_fields_is_reported_as_such(self):
        result, _ = self.inspect("/empty")
        self.assertEqual(result["result"], "no_fields_found")


if __name__ == "__main__":
    unittest.main()
