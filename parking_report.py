#!/usr/bin/env python3
"""Turn a JSON list of cars into Hebrew parking-violation report texts.

Usage:
    python3 parking_report.py sample.json
    python3 parking_report.py sample.json --city ירושלים --name "ישראל ישראלי"
"""
import argparse
import json
import sys
from datetime import datetime

REQUIRED = ("plate", "street", "datetime")


def format_datetime(value):
    """Accepts 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DDTHH:MM'; returns 'D.M.YYYY, HH:MM'."""
    text = str(value).strip().replace("T", " ")
    try:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError:
        raise ValueError("bad datetime %r, expected YYYY-MM-DD HH:MM" % value)
    return "%d.%d.%d, %02d:%02d" % (dt.day, dt.month, dt.year, dt.hour, dt.minute)


def build_report(car, city="", name="", with_photo=True):
    missing = [k for k in REQUIRED if not str(car.get(k, "")).strip()]
    if missing:
        raise ValueError("missing field(s): " + ", ".join(missing))
    street = car["street"].strip()
    place = "ברחוב %s" % street
    if city:
        place += ", %s" % city
    plate = car["plate"].strip()
    car_type = str(car.get("car_type", "")).strip()
    plate_text = "%s (%s)" % (plate, car_type) if car_type else plate
    notes = str(car.get("notes", "")).strip()
    parts = [
        "שלום, אני מדווח על רכב שחונה %s." % (notes if notes else "בחניה אסורה"),
        "מיקום: %s." % place,
        "תאריך ושעה: %s." % format_datetime(car["datetime"]),
        "מספר רכב: %s." % plate_text,
    ]
    if with_photo:
        parts.append("מצורפת תמונה.")
    parts.append("אבקש לשלוח פקח אכיפת חניה ולעדכן אותי במספר הפנייה.")
    parts.append("תודה" + (", %s" % name if name else ""))
    return " ".join(parts)


def build_reports(cars, **kwargs):
    if not isinstance(cars, list):
        raise ValueError("input must be a JSON list of cars")
    return [build_report(c, **kwargs) for c in cars]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("input", help="JSON file with a list of cars")
    p.add_argument("--city", default="", help="city appended to the street")
    p.add_argument("--name", default="", help="reporter name for the sign-off")
    p.add_argument("--no-photo", action="store_true", help="omit the photo line")
    args = p.parse_args(argv)
    with open(args.input, encoding="utf-8") as f:
        cars = json.load(f)
    try:
        reports = build_reports(cars, city=args.city, name=args.name,
                                with_photo=not args.no_photo)
    except ValueError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    print("\n\n".join(reports))
    return 0


if __name__ == "__main__":
    sys.exit(main())
