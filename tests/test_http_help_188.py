"""parking-report-http -h/--help (#188): help before configuration or a socket.

Offline. make_server and Service are patched so nothing can listen; the one
subprocess check runs with no token, so neither old nor new code can bind.
"""

import contextlib
import io
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from parking_report import http_service

VALID_ENV = {"PARKING_HTTP_TOKEN": "t" * 32, "PORT": "10002"}


def run_main(argv):
    out = io.StringIO()
    with (
        patch.dict("os.environ", VALID_ENV, clear=True),
        patch.object(http_service, "make_server") as server,
        patch.object(http_service, "Service") as service,
        contextlib.redirect_stdout(out),
        unittest.TestCase().assertRaises(SystemExit) as raised,
    ):
        http_service.main(argv)
    return raised.exception.code, out.getvalue(), server, service


class TestHelp(unittest.TestCase):
    def test_help_exits_0_without_config_or_socket(self):
        for argv in (["--help"], ["-h"], ["extra", "--help"]):
            with self.subTest(argv=argv):
                code, out, server, service = run_main(argv)
                self.assertEqual(code, 0)
                self.assertTrue(out.startswith("usage: parking-report-http"))
                for word in ("PARKING_HTTP_TOKEN", "PORT", "10000"):
                    self.assertIn(word, out)
                server.assert_not_called()
                service.assert_not_called()

    def test_help_from_sys_argv(self):
        out = io.StringIO()
        with (
            patch("sys.argv", ["parking-report-http", "--help"]),
            patch.dict("os.environ", VALID_ENV, clear=True),
            patch.object(http_service, "make_server") as server,
            contextlib.redirect_stdout(out),
            self.assertRaises(SystemExit) as raised,
        ):
            http_service.main()
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("usage: parking-report-http", out.getvalue())
        server.assert_not_called()

    def test_help_ignores_missing_config_in_a_real_process(self):
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("PARKING_HTTP_TOKEN", "PORT")
        }
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from parking_report.http_service import main; main()",
                "--help",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("usage: parking-report-http"))
        self.assertEqual(result.stderr, "")


class TestNormalStartupUnchanged(unittest.TestCase):
    def test_no_arguments_still_serves(self):
        with (
            patch.dict("os.environ", VALID_ENV, clear=True),
            patch.object(http_service, "make_server") as server,
        ):
            http_service.main([])
        server.assert_called_once()
        self.assertEqual(server.call_args.args[:2], ("0.0.0.0", 10002))
        server.return_value.__enter__.return_value.serve_forever.assert_called_once()

    def test_help_like_words_are_not_help(self):
        with (
            patch.dict("os.environ", VALID_ENV, clear=True),
            patch.object(http_service, "make_server") as server,
        ):
            http_service.main(["--he", "help", "-H"])
        server.assert_called_once()


if __name__ == "__main__":
    unittest.main()
