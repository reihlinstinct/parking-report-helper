"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .municipality import (
    build_submission,
    format_submission,
    load_config,
    submission_dict,
)
from .report import Car, build_reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parking-report",
        description="Turn a JSON list of cars into Hebrew parking-violation report texts.",
    )
    parser.add_argument("input", help="JSON file with a list of cars")
    parser.add_argument("--city", default="", help="city appended to the street")
    parser.add_argument("--name", default="", help="reporter name for the sign-off")
    parser.add_argument("--no-photo", action="store_true", help="omit the photo line")
    parser.add_argument(
        "--municipality",
        metavar="NAME_OR_FILE",
        help="print copy-paste form field values for a municipality "
        "(bundled name such as 'jerusalem', or a config .json path)",
    )
    parser.add_argument(
        "--reporter",
        metavar="FILE",
        help="JSON file with reporter details for the form (keep it outside the repo)",
    )
    parser.add_argument(
        "--json", action="store_true", help="with --municipality, print JSON instead of text"
    )
    return parser


def _read_json(path: str) -> object:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cars = _read_json(args.input)
        if args.municipality:
            config = load_config(args.municipality)
            reporter = _read_json(args.reporter) if args.reporter else {}
            if not isinstance(reporter, dict):
                raise ValueError("reporter file must be a JSON object")
            if not isinstance(cars, list):
                raise ValueError("input must be a JSON list of cars")
            subs = []
            for index, car in enumerate(cars, start=1):
                try:
                    subs.append(
                        build_submission(
                            Car.from_mapping(car), config, reporter, not args.no_photo
                        )
                    )
                except ValueError as error:
                    raise ValueError(f"car {index}: {error}") from error
            if args.json:
                output = json.dumps(
                    [submission_dict(rows) for rows in subs], ensure_ascii=False, indent=2
                )
            else:
                url = config.get("channel", {}).get("url", "")
                blocks = [
                    f"# {i}/{len(subs)}  {url}\n{format_submission(rows)}"
                    for i, rows in enumerate(subs, start=1)
                ]
                output = "\n\n".join(blocks)
        else:
            reports = build_reports(
                cars, city=args.city, name=args.name, with_photo=not args.no_photo
            )
            output = "\n\n".join(reports)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
