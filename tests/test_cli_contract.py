"""docs/CLI-CONTRACT.md matches the real entry points (#73).

The machine-readable block in the doc is compared with the argparse parsers
(introspected, not parsed from --help text) and with the exit paths, so a
flag, default or exit-code change without a doc update fails here. Offline:
no network, no secrets; the HTTP service never binds a port.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib import metadata
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from parking_report import api_cli, cli, http_service

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "CLI-CONTRACT.md"


def load_contract(text: str | None = None) -> dict:
    text = DOC.read_text(encoding="utf-8") if text is None else text
    match = re.search(
        r"<!-- cli-contract:begin -->\s*```json\n(.*?)\n```\s*<!-- cli-contract:end -->",
        text,
        re.DOTALL,
    )
    if not match:
        raise AssertionError(
            "cli-contract JSON block missing from docs/CLI-CONTRACT.md"
        )
    return json.loads(match.group(1))


class _Captured(Exception):
    def __init__(self, parser: argparse.ArgumentParser) -> None:
        self.parser = parser


def api_cli_parser() -> argparse.ArgumentParser:
    """api_cli builds its parser inside main(); capture it before parsing."""

    def capture(self, *_args, **_kwargs):
        raise _Captured(self)

    with patch.object(argparse.ArgumentParser, "parse_args", capture):
        try:
            api_cli.main([])
        except _Captured as captured:
            return captured.parser
    raise AssertionError("api_cli.main did not build a parser")


def describe(parser: argparse.ArgumentParser) -> tuple[list[str], dict]:
    positionals, options = [], {}
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        if not action.option_strings:
            positionals.append(action.dest)
            continue
        entry: dict = {"default": action.default}
        if isinstance(action, argparse._StoreTrueAction):
            entry["flag"] = True
        if action.required:
            entry["required"] = True
        if action.choices:
            entry["choices"] = list(action.choices)
        if action.help == argparse.SUPPRESS:
            entry["hidden"] = True
        default = entry["default"]
        if isinstance(default, Path):
            entry["default"] = str(default)
        options[action.option_strings[0]] = entry
    return positionals, options


def documented(command: dict) -> tuple[list[str], dict]:
    options = {
        name: {k: v for k, v in spec.items() if k != "deprecated"}
        for name, spec in command["options"].items()
    }
    return command["positionals"], options


def run(func, argv):
    out, err = io.StringIO(), io.StringIO()
    out.reconfigure = lambda **_k: None  # type: ignore[attr-defined]
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = func(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class ContractDocTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_contract()

    def test_entry_points_and_version_match_package(self) -> None:
        # Source checkout: pyproject.toml. Docker test stage (no pyproject in
        # /app): the installed distribution's metadata, built from that file.
        pyproject = ROOT / "pyproject.toml"
        if pyproject.exists():
            project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
            version, scripts = project["version"], project["scripts"]
        else:
            version = metadata.version("parking-report-helper")
            scripts = {
                ep.name: ep.value
                for ep in metadata.distribution("parking-report-helper").entry_points
                if ep.group == "console_scripts"
            }
        self.assertEqual(self.contract["package_version"], version)
        modules = {
            name: spec["module"] for name, spec in self.contract["commands"].items()
        }
        self.assertEqual(modules, scripts)

    def test_parking_report_options_match_parser(self) -> None:
        self.assertEqual(
            describe(cli.build_parser()),
            documented(self.contract["commands"]["parking-report"]),
        )

    def test_parking_report_106_options_match_parser(self) -> None:
        self.assertEqual(
            describe(api_cli_parser()),
            documented(self.contract["commands"]["parking-report-106"]),
        )

    def test_planted_doc_drift_is_detected(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        for old, new in (
            ('"--city": {"default": ""}', '"--city": {"default": "x"}'),
            (
                '"--state-dir": {"default": ".106-state"}',
                '"--state-dir": {"default": "state"}',
            ),
            (
                '        "--json": {"default": false, "flag": true}\n',
                '        "--json": {"default": false}\n',
            ),
        ):
            self.assertIn(old, text)
            drifted = load_contract(text.replace(old, new, 1))
            self.assertNotEqual(
                (describe(cli.build_parser()), describe(api_cli_parser())),
                (
                    documented(drifted["commands"]["parking-report"]),
                    documented(drifted["commands"]["parking-report-106"]),
                ),
            )
        with self.assertRaises(AssertionError):
            load_contract(text.replace("<!-- cli-contract:end -->", ""))


class ExitCodeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_contract()["commands"]

    def test_parking_report_exit_codes(self) -> None:
        documented_codes = set(self.contract["parking-report"]["exit_codes"])
        self.assertEqual(documented_codes, {"0", "1", "2"})
        with TemporaryDirectory() as tmp:
            cars = Path(tmp) / "cars.json"
            cars.write_text("[]", encoding="utf-8")
            self.assertEqual(run(cli.main, [str(cars)])[0], 0)
            self.assertEqual(run(cli.main, [str(Path(tmp) / "missing.json")])[0], 1)
        self.assertEqual(run(cli.main, [])[0], 2)
        self.assertEqual(run(cli.main, ["cars.json", "--json"])[0], 2)
        self.assertEqual(run(cli.main, ["--no-such-flag"])[0], 2)

    def test_parking_report_106_exit_codes_and_fixed_blocked_line(self) -> None:
        spec = self.contract["parking-report-106"]
        self.assertEqual(set(spec["exit_codes"]), {"0", "2", "4"})
        self.assertEqual(run(api_cli.main, [])[0], 2)
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {}, clear=True):
            code, out, err = run(
                api_cli.main, [tmp, "--addresses", str(Path(tmp) / "a.json")]
            )
        self.assertEqual(code, 4)
        line = json.loads(out)
        self.assertEqual(sorted(line), sorted(spec["stdout_keys"]["blocked"]))
        self.assertEqual(line["status"], "blocked")
        self.assertEqual(err, "")

    def test_parking_report_http_invalid_config_exits_with_fixed_message(self) -> None:
        spec = self.contract["parking-report-http"]
        self.assertEqual(set(spec["exit_codes"]), {"1"})
        cases = ({}, {"PARKING_HTTP_TOKEN": "x" * 32, "PORT": "70000"})
        for env in cases:
            with (
                self.subTest(env=sorted(env)),
                patch.dict("os.environ", env, clear=True),
                patch.object(http_service, "make_server") as server,
                self.assertRaises(SystemExit) as raised,
            ):
                http_service.main()
            server.assert_not_called()
            message = str(raised.exception.code)
            self.assertIsInstance(
                raised.exception.code, str
            )  # str code -> exit status 1
            self.assertNotIn("x" * 32, message)
            self.assertNotIn("70000", message)


if __name__ == "__main__":
    unittest.main()
