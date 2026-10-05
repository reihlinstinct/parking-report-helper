"""Read-only official-form diagnostic using the optional browser helper."""
from typing import Any
from collections.abc import Mapping
import re
from .fill import check_url


def inspect_page(page: Any, config: Mapping[str, Any]) -> dict[str, list[str]]:
    """Read configured field presence only. Never fill, upload or submit anything."""
    report: dict[str, list[str]] = {"found": [], "not_found": []}
    for field in config["fields"]:
        selector = field.get("selector")
        target = (page.locator(selector) if selector else
                  page.get_by_label(re.compile(re.escape(field["label"]))))
        found = target.count() > 0 and target.first.is_visible()
        report["found" if found else "not_found"].append(field["label"])
    return report


def inspect_form(config: Mapping[str, Any]) -> dict[str, Any]:
    """Load the official page once, read field labels, and close. No retries.

    A normal Chromium context is used, without identity overrides or stealth.
    HTTP blocks and verification walls are results, not reasons to try again.
    Only the main frame is inspected; embedded forms may need manual inspection.
    """
    from playwright.sync_api import sync_playwright

    target = check_url(config["channel"]["url"], config)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            response = page.goto(target, wait_until="load", timeout=30000)
            status = response.status if response else None
            report: dict[str, Any] = {"url": page.url, "http_status": status}
            if status is None or status >= 400:
                report["result"] = "blocked_or_http_error"
                return report
            # Read only. Never interact with verification widgets.
            text = page.locator("body").inner_text(timeout=5000).lower()
            wall = any(word in text for word in (
                "verify you are human", "access denied", "just a moment",
                "checking your browser", "security check", "captcha",
                "אימות אנושי", "אינך רובוט", "גישה חסומה",
            ))
            widget = page.locator(
                'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], '
                '.g-recaptcha, .h-captcha, #challenge-form'
            ).count() > 0
            if wall or widget:
                report["result"] = "verification_present_stopped"
                return report
            report.update(inspect_page(page, config))
            report["result"] = "inspected" if report["found"] else "no_fields_found"
            return report
        finally:
            browser.close()
