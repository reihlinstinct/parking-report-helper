"""Offline Hebrew monthly draft from the private ledger/reports.csv, never a sender.

Run: python -m parking_report.monthly PRIVATE_CSV --month YYYY-MM
Output can contain private references and must stay out of public logs/artifacts.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path

REQUIRED = {
    "folder_id",
    "filed_date",
    "street",
    "event_type",
    "municipal_ref",
    "ref_mapping",
}


def _cell(value: str) -> str:
    """Keep untrusted ledger text inside one Markdown table cell."""
    return (
        value.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _reject_control_chars(row: Mapping[str, str]) -> None:
    """Reject control and bidi-override characters in required ledger fields."""
    for key in REQUIRED:
        if any(
            ord(char) < 32
            or 127 <= ord(char) <= 159
            or char in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
            for char in row[key]
        ):
            raise ValueError("Control characters in ledger")


def _month_row(
    row: Mapping[str, str], month: str, seen: set[str], references: set[str]
) -> dict[str, str] | None:
    """Validate one ledger row; return it normalised, or None outside ``month``."""
    if not REQUIRED.issubset(row):
        raise ValueError("Missing ledger columns")
    if any(not isinstance(row[key], str) for key in REQUIRED):
        raise ValueError("Invalid ledger value")
    day = row["filed_date"]
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
        raise ValueError("Invalid filing date")
    date.fromisoformat(day)
    if day[:7] != month:
        return None
    _reject_control_chars(row)
    if not all(row[key].strip() for key in ("folder_id", "street", "event_type")):
        raise ValueError("Missing report identity or classification")
    if row["folder_id"] in seen:
        raise ValueError("Duplicate report identity")
    seen.add(row["folder_id"])
    ref = row["municipal_ref"].strip()
    # Preserve the complete reference. Do not infer a match from its prefix or order.
    if ref and not re.fullmatch(r"[0-9]+(?:-[0-9]+)?", ref):
        raise ValueError("Invalid municipal reference")
    if ref and ref in references:
        raise ValueError("Duplicate municipal reference; reconcile the ledger")
    if ref:
        references.add(ref)
    if row["ref_mapping"] == "verified" and not ref:
        raise ValueError("Verified mapping requires a reference")
    return dict(row, municipal_ref=ref)


def _select_rows(rows: Iterable[Mapping[str, str]], month: str) -> list[dict[str, str]]:
    """Return the month's validated ledger rows, sorted by date and ID."""
    seen: set[str] = set()
    references: set[str] = set()
    selected = []
    for row in rows:
        chosen = _month_row(row, month, seen, references)
        if chosen is not None:
            selected.append(chosen)
    selected.sort(key=lambda item: (item["filed_date"], item["folder_id"]))
    return selected


def _count_table(title: str, header: str, counts: Counter) -> list[str]:
    """Render one two-column markdown table, most frequent first."""
    lines = ["", title, "", header, "| --- | ---: |"]
    lines += [
        f"| {_cell(key)} | {count} |"
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return lines


def _reference_table(selected: list[dict[str, str]]) -> list[str]:
    """Render the per-report municipal reference table."""
    lines = [
        "",
        "## מספרי פנייה",
        "",
        "| תאריך | רחוב | סוג אירוע | מספר פנייה | שיוך |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in selected:
        status = "מאומת" if row["ref_mapping"] == "verified" else "לא מאומת"
        ref = row["municipal_ref"] or "חסר"
        lines.append(
            "| "
            + " | ".join(
                _cell(value)
                for value in (
                    row["filed_date"],
                    row["street"],
                    row["event_type"],
                    ref,
                    status,
                )
            )
            + " |"
        )
    return lines


def monthly_draft(rows: Iterable[Mapping[str, str]], month: str) -> str:
    """Validate before rendering. Count ledger events, not unique plates or confirmed cases."""
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", month):
        raise ValueError("Invalid month")
    date.fromisoformat(month + "-01")
    selected = _select_rows(rows, month)
    verified = sum(row["ref_mapping"] == "verified" for row in selected)
    lines = [
        f"# טיוטה: סיכום דיווחים לחודש {month}",
        "",
        "טיוטה לבדיקה בלבד. הנמענים והנוסח דורשים אישור לפני שליחה.",
        "",
        f"רשומות דיווח ביומן: {len(selected)}",
        f"שיוך מספר פנייה מאומת: {verified}",
        f"שיוך חסר או לא מאומת: {len(selected) - verified}",
        "",
        "הספירה היא של אירועי דיווח ביומן, לא של כלי רכב ייחודיים או תוצאות אכיפה.",
        "רחובות וסוגי אירוע נשענים על היומן; שיוך פנייה לא מאומת אינו מאשר את פרטי הפנייה בעירייה.",
    ]
    streets = Counter(row["street"].strip() for row in selected)
    lines += _count_table("## לפי רחוב", "| רחוב | דיווחים |", streets)
    events = Counter(row["event_type"].strip() for row in selected)
    lines += _count_table("## לפי סוג אירוע", "| סוג אירוע | דיווחים |", events)
    lines += _reference_table(selected)
    if not selected:
        lines += ["", "אין רשומות בחודש הנבחר ביומן שסופק."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--month", required=True)
    args = parser.parse_args(argv)
    try:
        with args.ledger.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not REQUIRED.issubset(reader.fieldnames or []):
                raise ValueError("Missing ledger columns")
            draft = monthly_draft(reader, args.month)
    except (OSError, UnicodeError, ValueError, csv.Error):
        print(
            "Monthly draft blocked: check the private ledger and month; no output was generated.",
            file=sys.stderr,
        )
        return 1
    print(draft, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
