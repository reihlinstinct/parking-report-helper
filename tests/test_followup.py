"""Synthetic metadata validation and digest binding regressions."""

import json
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from test_api_cli_main import ENV, make_folder, run

from parking_report import api_cli
from parking_report.followup import validate_followup


def manifest():
    return {
        "parent_id": "original",
        "parent_digest": "a" * 64,
        "parent_case_number": "2601-1234567",
        "parent_closed_at": "2026-01-01T12:00:00+02:00",
        "approval_reference": "approval-synthetic-1",
    }


def response_manifest():
    value = manifest()
    value.pop("parent_closed_at", None)
    return dict(
        value,
        reply_received_at="2026-01-02T12:00:00+02:00",
        reply_reference="municipal-reply-synthetic-1",
        parent_status="unknown",
    )


class FollowupTests(unittest.TestCase):
    manifest = staticmethod(manifest)

    def test_exact_validated_manifest(self):
        self.assertEqual(validate_followup(self.manifest()), self.manifest())
        for bad in (
            None,
            {},
            dict(self.manifest(), extra="bad"),
            dict(self.manifest(), parent_digest="bad"),
            dict(self.manifest(), parent_id="../bad"),
            dict(self.manifest(), parent_closed_at="2026-01-01T12:00:00"),
            dict(self.manifest(), approval_reference=" "),
            dict(self.manifest(), parent_case_number="bad"),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_followup(bad)

    def test_response_variant_is_exact_and_preserves_unknown_status(self):
        value = response_manifest()
        self.assertEqual(validate_followup(value), value)
        for bad in (
            dict(value, parent_closed_at="2026-01-01T12:00:00+02:00"),
            dict(value, parent_status="closed"),
            dict(value, parent_status="open"),
            dict(value, reply_received_at="2026-01-02T12:00:00"),
            dict(value, reply_reference=" "),
            dict(value, reply_reference="bad reference"),
            {k: v for k, v in value.items() if k != "reply_reference"},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_followup(bad)

    def test_every_response_field_is_digest_bound(self):
        with TemporaryDirectory() as tmp:
            folder, addresses = make_folder(tmp)
            record = json.loads((folder / "report.json").read_text())
            variants = [response_manifest()]
            for key, value in (
                ("reply_reference", "municipal-reply-synthetic-2"),
                ("reply_received_at", "2026-01-02T12:01:00+02:00"),
                ("approval_reference", "approval-synthetic-2"),
            ):
                variants.append(dict(response_manifest(), **{key: value}))
            digests = []
            for value in variants:
                record["followup"] = value
                (folder / "report.json").write_text(json.dumps(record))
                code, output = run([str(folder), "--addresses", str(addresses)])
                self.assertEqual(code, 0)
                digests.append(json.loads(output)["sha256"])
            self.assertEqual(len(set(digests)), len(variants))

    def test_manifest_bound_into_digest_and_missing_approval_no_reservation(self):
        with TemporaryDirectory() as tmp:
            folder, addresses = make_folder(tmp)
            before = api_cli.prepare(
                folder,
                addresses,
                {
                    key: ENV["PARKING_REPORTER_" + key.upper()]
                    for key in (
                        "first_name",
                        "last_name",
                        "phone",
                        "id_number",
                        "email",
                    )
                },
            )[3]
            record = json.loads((folder / "report.json").read_text())
            record["followup"] = self.manifest()
            (folder / "report.json").write_text(json.dumps(record))
            code, output = run([str(folder), "--addresses", str(addresses)])
            digest = json.loads(output)["sha256"]
            self.assertEqual(code, 0)
            self.assertNotEqual(before, digest)
            with patch("parking_report.ledger.GitLedger.reserve") as reserve:
                code, _ = run(
                    [
                        str(folder),
                        "--addresses",
                        str(addresses),
                        "--ledger-dir",
                        tmp,
                        "--submit",
                        "--approved-sha256",
                        digest,
                    ],
                    dict(ENV, PARKING_106_ENABLE_LIVE="true"),
                )
                self.assertEqual(code, 4)
                reserve.assert_not_called()

    def test_explicit_gate_passes_manifest_to_ledger(self):
        from unittest.mock import MagicMock

        with TemporaryDirectory() as tmp:
            folder, addresses = make_folder(tmp)
            record = json.loads((folder / "report.json").read_text())
            record["followup"] = self.manifest()
            (folder / "report.json").write_text(json.dumps(record))
            _, output = run([str(folder), "--addresses", str(addresses)])
            digest = json.loads(output)["sha256"]
            ledger = MagicMock()
            ledger.locked.return_value.__enter__.return_value = ledger
            with (
                patch("parking_report.ledger.GitLedger", return_value=ledger),
                patch.object(api_cli, "execute", return_value=0) as execute,
            ):
                code, _ = run(
                    [
                        str(folder),
                        "--addresses",
                        str(addresses),
                        "--ledger-dir",
                        tmp,
                        "--submit",
                        "--approved-sha256",
                        digest,
                        "--approved-followup-sha256",
                        digest,
                    ],
                    dict(ENV, PARKING_106_ENABLE_LIVE="true"),
                )
                self.assertEqual(code, 0)
                self.assertEqual(
                    ledger.reserve.call_args.kwargs["followup"], self.manifest()
                )
                execute.assert_called_once()

    def test_changed_approval_changes_digest(self):
        with TemporaryDirectory() as tmp:
            folder, addresses = make_folder(tmp)
            record = json.loads((folder / "report.json").read_text())
            digests = []
            for evidence in ("approval-1", "approval-2"):
                record["followup"] = dict(self.manifest(), approval_reference=evidence)
                (folder / "report.json").write_text(json.dumps(record))
                _, output = run([str(folder), "--addresses", str(addresses)])
                digests.append(json.loads(output)["sha256"])
            self.assertNotEqual(*digests)

    def test_every_approval_clause_blocks_before_reservation(self):
        with TemporaryDirectory() as tmp:
            folder, addresses = make_folder(tmp)
            record = json.loads((folder / "report.json").read_text())
            record["followup"] = self.manifest()
            (folder / "report.json").write_text(json.dumps(record))
            _, output = run([str(folder), "--addresses", str(addresses)])
            digest = json.loads(output)["sha256"]
            for normal, followup, enabled, has_manifest in (
                (digest, "wrong", "true", True),
                ("wrong", digest, "true", True),
                (digest, digest, "false", True),
                (digest, digest, "true", False),
            ):
                if not has_manifest:
                    record.pop("followup")
                    (folder / "report.json").write_text(json.dumps(record))
                ledger = MagicMock()
                ledger.locked.return_value.__enter__.return_value = ledger
                with (
                    self.subTest(normal=normal, followup=followup, enabled=enabled),
                    patch("parking_report.ledger.GitLedger", return_value=ledger),
                    patch.object(api_cli, "execute", return_value=0),
                ):
                    code, _ = run(
                        [
                            str(folder),
                            "--addresses",
                            str(addresses),
                            "--ledger-dir",
                            tmp,
                            "--submit",
                            "--approved-sha256",
                            normal,
                            "--approved-followup-sha256",
                            followup,
                        ],
                        dict(ENV, PARKING_106_ENABLE_LIVE=enabled),
                    )
                    self.assertEqual(code, 4)
                    ledger.reserve.assert_not_called()


class ResponseFollowupGateTests(FollowupTests):
    """Apply every normal preview and approval test to the response variant."""

    manifest = staticmethod(response_manifest)
