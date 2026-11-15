"""Synthetic unknown-result opt-in tests; no municipal requests."""

import copy
import hashlib
import json
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import test_ledger
from test_api_cli_main import ENV, make_folder, run

from parking_report import api_cli
from parking_report.api106 import ReviewNeeded, submit
from parking_report.ledger import GitLedger, LedgerError
from parking_report.unknown_retry import validate_unknown_retry


def manifest(digest="a" * 64):
    return {
        "parent_id": "original",
        "parent_digest": digest,
        "approval_reference": "approval-synthetic-336",
    }


class UnknownRetryTests(unittest.TestCase):
    setUp = test_ledger.LedgerTests.setUp
    git = test_ledger.LedgerTests.git
    clone = test_ledger.LedgerTests.clone

    def parent(self, ledger, status="creating"):
        ledger.reserve("original", "a" * 64, "b" * 64)
        ledger.checkpoint("original", {"version": 1, "status": status})

    def test_exact_manifest_validation(self):
        self.assertEqual(validate_unknown_retry(manifest()), manifest())
        for bad in (
            {},
            dict(manifest(), extra="x"),
            dict(manifest(), approval_reference=""),
            dict(manifest(), parent_digest="bad"),
        ):
            with self.assertRaises(ValueError):
                validate_unknown_retry(bad)
        with self.assertRaises(ValueError):
            validate_unknown_retry(manifest(), "original")

    def test_one_child_parent_and_photo_index_unchanged(self):
        with GitLedger(self.a).locked() as ledger:
            self.parent(ledger)
            before = copy.deepcopy(ledger.data)
            entry = ledger.reserve_unknown_retry(
                "retry", "c" * 64, "b" * 64, manifest()
            )
            key = hashlib.sha256(b"original").hexdigest()
            self.assertEqual(before["reports"][key], ledger.data["reports"][key])
            self.assertEqual(before["photos"], ledger.data["photos"])
            self.assertEqual(entry["unknown_retry"], manifest())
            self.assertEqual(
                entry,
                ledger.reserve_unknown_retry("retry", "c" * 64, "b" * 64, manifest()),
            )
            with self.assertRaises(LedgerError):
                ledger.reserve_unknown_retry("sibling", "d" * 64, "b" * 64, manifest())
            with self.assertRaises(LedgerError):
                ledger.reserve("sibling", "e" * 64, "b" * 64, supersedes=manifest())
            with self.assertRaises(LedgerError):
                ledger.reserve("retry", "c" * 64, "b" * 64)

    def test_only_creating_parent(self):
        for status in ("prepared", "created", "attaching", "complete"):
            with self.subTest(status=status), GitLedger(self.a).locked() as ledger:
                if not ledger.data["reports"]:
                    self.parent(ledger, status)
                else:
                    ledger.checkpoint("original", {"version": 1, "status": status})
                before = copy.deepcopy(ledger.data)
                with self.assertRaises(LedgerError):
                    ledger.reserve_unknown_retry(
                        "retry", "c" * 64, "b" * 64, manifest()
                    )
                self.assertEqual(before, ledger.data)

    def test_mismatched_inputs_or_receipt_rejected(self):
        with GitLedger(self.a).locked() as ledger:
            self.parent(ledger)
            for digest, photo, m in (
                ("a" * 64, "b" * 64, manifest()),
                ("c" * 64, "e" * 64, manifest()),
                ("c" * 64, "b" * 64, manifest("d" * 64)),
            ):
                with self.assertRaises(LedgerError):
                    ledger.reserve_unknown_retry("retry", digest, photo, m)
            ledger.checkpoint(
                "original", {"version": 1, "status": "creating", "case": {"id": "fake"}}
            )
            with self.assertRaises(LedgerError):
                ledger.reserve_unknown_retry("retry", "c" * 64, "b" * 64, manifest())

    def test_related_parent_and_existing_sibling_are_refused(self):
        with GitLedger(self.a).locked() as ledger:
            self.parent(ledger)
            key = hashlib.sha256(b"original").hexdigest()
            for field in (
                "unknown_retry",
                "followup",
                "supersedes",
                "shared_photo",
                "shared_issue",
                "extension",
                "superseded_by",
            ):
                ledger.data["reports"][key][field] = {}
                with self.assertRaises(LedgerError):
                    ledger.reserve_unknown_retry(
                        "retry", "c" * 64, "b" * 64, manifest()
                    )
                del ledger.data["reports"][key][field]
            for relation in ({"followup": manifest()}, {"extension": {"parent": key}}):
                ledger.data["reports"]["synthetic-sibling"] = relation
                with self.assertRaises(LedgerError):
                    ledger.reserve_unknown_retry(
                        "retry", "c" * 64, "b" * 64, manifest()
                    )
                del ledger.data["reports"]["synthetic-sibling"]

    def test_successful_child_is_returned_without_losing_parent_unknown(self):
        with GitLedger(self.a).locked() as ledger:
            self.parent(ledger)
            ledger.reserve_unknown_retry("retry", "c" * 64, "b" * 64, manifest())
            saved = {"version": 1, "status": "complete", "case": {"id": "synthetic"}}
            ledger.checkpoint("retry", saved)
        with GitLedger(self.a).locked() as ledger:
            entry = ledger.reserve_unknown_retry(
                "retry", "c" * 64, "b" * 64, manifest()
            )
            self.assertEqual(entry["state"], saved)
            key = hashlib.sha256(b"original").hexdigest()
            self.assertEqual(ledger.data["reports"][key]["state"]["status"], "creating")
            with self.assertRaises(LedgerError):
                ledger.reserve_unknown_retry("retry", "d" * 64, "b" * 64, manifest())

    def test_uncertain_child_never_creates_twice(self):
        api = MagicMock()
        api.create.side_effect = OSError("timeout")
        with GitLedger(self.a).locked() as ledger:
            self.parent(ledger)
            entry = ledger.reserve_unknown_retry(
                "retry", "c" * 64, "b" * 64, manifest()
            )
            with self.assertRaises(ReviewNeeded):
                submit(
                    api,
                    {},
                    {},
                    b"jpeg",
                    "c" * 64,
                    self.root / "state",
                    initial_state=entry["state"],
                    checkpoint=lambda s: ledger.checkpoint("retry", s),
                )
        with GitLedger(self.a).locked() as ledger:
            entry = ledger.reserve_unknown_retry(
                "retry", "c" * 64, "b" * 64, manifest()
            )
            with self.assertRaises(ReviewNeeded):
                submit(
                    api,
                    {},
                    {},
                    b"jpeg",
                    "c" * 64,
                    self.root / "fresh-state",
                    initial_state=entry["state"],
                )
        self.assertEqual(api.create.call_count, 1)


class UnknownRetryCliTests(unittest.TestCase):
    def test_prepare_preserves_base_and_rejects_changes_or_mixed_relations(self):
        with TemporaryDirectory() as tmp:
            folder, addresses = make_folder(tmp)
            reporter = {
                k.lower().removeprefix("parking_reporter_"): v for k, v in ENV.items()
            }
            digest = api_cli.prepare(folder, addresses, reporter)[3]
            record = json.loads((folder / "report.json").read_text())
            record["unknown_retry"] = manifest(digest)
            (folder / "report.json").write_text(json.dumps(record))
            retry_digest = api_cli.prepare(folder, addresses, reporter)[3]
            self.assertNotEqual(digest, retry_digest)
            for change in (
                {"approved_description": "changed"},
                {"supersedes": manifest()},
            ):
                (folder / "report.json").write_text(json.dumps(dict(record, **change)))
                with self.assertRaises(ValueError):
                    api_cli.prepare(folder, addresses, reporter)

    def test_live_flag_required_before_reservation_preview_reserves_nothing(self):
        with TemporaryDirectory() as tmp:
            folder, addresses = make_folder(tmp)
            reporter = {
                k.lower().removeprefix("parking_reporter_"): v for k, v in ENV.items()
            }
            digest = api_cli.prepare(folder, addresses, reporter)[3]
            record = json.loads((folder / "report.json").read_text())
            record["unknown_retry"] = manifest(digest)
            (folder / "report.json").write_text(json.dumps(record))
            args = [str(folder), "--addresses", str(addresses), "--ledger-dir", tmp]
            with patch.object(
                GitLedger, "locked", side_effect=AssertionError("reserved")
            ):
                self.assertEqual(run(args)[0], 0)
                self.assertEqual(run(args + ["--submit"])[0], 4)

    def test_exact_cli_opt_in_routes_to_retry_reservation(self):
        with TemporaryDirectory() as tmp:
            folder, addresses = make_folder(tmp)
            reporter = {
                k.lower().removeprefix("parking_reporter_"): v for k, v in ENV.items()
            }
            base = api_cli.prepare(folder, addresses, reporter)[3]
            record = json.loads((folder / "report.json").read_text())
            record["unknown_retry"] = manifest(base)
            (folder / "report.json").write_text(json.dumps(record))
            digest = api_cli.prepare(folder, addresses, reporter)[3]
            ledger = MagicMock()
            ledger.locked.return_value.__enter__.return_value = ledger
            entry = {"state": {"version": 1, "status": "prepared"}}
            ledger.reserve_unknown_retry.return_value = entry
            args = [
                str(folder),
                "--addresses",
                str(addresses),
                "--ledger-dir",
                tmp,
                "--submit",
                "--approved-sha256",
                digest,
            ]
            with (
                patch("parking_report.ledger.GitLedger", return_value=ledger),
                patch.object(api_cli, "execute", return_value=0) as execute,
            ):
                self.assertEqual(
                    run(args + ["--approved-unknown-retry-sha256", "bad"])[0], 4
                )
                ledger.reserve_unknown_retry.assert_not_called()
                self.assertEqual(
                    run(args + ["--approved-unknown-retry-sha256", digest])[0], 0
                )
                ledger.reserve_unknown_retry.assert_called_once()
                ledger.reserve.assert_not_called()
                self.assertEqual(execute.call_args.args[-2], entry)
