"""Optional browser helper: fill a municipality web form, then stop.

Needs the optional extra: pip install ".[fill]" and "playwright install chromium".

Safety rules, enforced in code and covered by tests:
* It never clicks a submit button and never submits the form.
* It does not solve, detect-and-bypass or interact with captchas or other bot checks.
* It leaves the browser open so a person can review, pass any verification and press
  submit themselves.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

MISSING_MARK = "<חסר>"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class FillError(RuntimeError):
    """Raised for problems the user can fix (bad files, missing extra, wrong URL)."""


def check_url(url: str, config: Mapping[str, Any]) -> str:
    """Allow the municipality's own URL, or a local file/localhost page for testing."""
    official = config.get("channel", {}).get("url", "")
    parsed = urlparse(url)
    if url == official:
        return url
    if parsed.scheme == "file" or (
        parsed.scheme in ("http", "https") and parsed.hostname in _LOCAL_HOSTS
    ):
        return url
    raise FillError("form URL must be the configured municipality URL or a local test page")


def check_attachments(paths: Sequence[str], config: Mapping[str, Any]) -> list[str]:
    """Validate photo files against the config limits (count, type, size)."""
    limit = int(config.get("max_attachments", 0) or 0)
    allowed = {str(t).lower() for t in config.get("attachment_types", [])}
    max_bytes = int(config.get("attachment_max_mb", 0) or 0) * 1024 * 1024
    if limit and len(paths) > limit:
        raise FillError(f"at most {limit} attachments are allowed, got {len(paths)}")
    checked = []
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            raise FillError(f"attachment not found: {raw}")
        if allowed and path.suffix.lstrip(".").lower() not in allowed:
            raise FillError(f"attachment type not allowed: {path.name}")
        if max_bytes and path.stat().st_size > max_bytes:
            raise FillError(f"attachment too large: {path.name}")
        checked.append(str(path.resolve()))
    return checked


def fill_page(
    page: Any,
    config: Mapping[str, Any],
    rows: Sequence[tuple[str, str, str]],
    attachments: Sequence[str] = (),
) -> dict[str, list[str]]:
    """Fill every field on an open Playwright page. Returns what was filled/skipped.

    Fields are found by the config's optional "selector", otherwise by their visible
    label. Missing values (marked with MISSING_MARK) and empty values are left blank.
    Nothing is clicked except to focus fields; the form is never submitted.
    """
    fields = {f["key"]: f for f in config["fields"]}
    report: dict[str, list[str]] = {"filled": [], "skipped": [], "not_found": []}
    for key, label, value in rows:
        field = fields[key]
        if not value or value == MISSING_MARK:
            report["skipped"].append(key)
            continue
        selector = field.get("selector")
        locator = (
            page.locator(selector)
            if selector
            else page.get_by_label(re.compile(re.escape(label)))
        ).first
        if locator.count() == 0:
            report["not_found"].append(key)
            continue
        if field.get("choices"):
            locator.select_option(label=value)
        else:
            locator.fill(value)
        report["filled"].append(key)
    if attachments:
        file_selector = config.get("fill", {}).get("file_input", "input[type=file]")
        target = page.locator(file_selector).first
        if target.count() == 0:
            report["not_found"].append("attachments")
        else:
            target.set_input_files(list(attachments))
            report["filled"].append("attachments")
    return report


def fill_form(
    config: Mapping[str, Any],
    rows: Sequence[tuple[str, str, str]],
    attachments: Sequence[str] = (),
    url: str | None = None,
    headless: bool = False,
    wait_for_user: bool = True,
) -> dict[str, list[str]]:
    """Open the form, fill it, then wait for the person to finish by themselves.

    With wait_for_user, the call returns only when the browser window is closed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise FillError(
            'playwright is not installed. Run: pip install ".[fill]" && playwright install chromium'
        ) from None
    target = check_url(url or config.get("channel", {}).get("url", ""), config)
    files = check_attachments(attachments, config)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            page.goto(target)
            report = fill_page(page, config, rows, files)
            if wait_for_user:
                page.wait_for_event("close", timeout=0)
        finally:
            browser.close()
    return report
