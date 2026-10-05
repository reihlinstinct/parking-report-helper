"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .report import build_reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parking-report",
        description="Turn a JSON list of cars into Hebrew parking-violation report texts.",
    )
    parser.add_argument("input", help="JSON file with a list of cars")
    parser.add_argument("--city", default="", help="city appended to the street")
    parser.add_argument("--name", default="", help="reporter name for the sign-off")
    parser.add_argument("--no-photo", action="store_true", help="omit the photo line")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with open(args.input, encoding="utf-8") as handle:
            cars = json.load(handle)
        reports = build_reports(
            cars, city=args.city, name=args.name, with_photo=not args.no_photo
        )
    except (OSError, UnicodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print("\n\n".join(reports))
    return 0


if __name__ == "__main__":
    sys.exit(main())
