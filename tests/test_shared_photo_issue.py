"""Explicit shared-photo issue pair: two distinct non-vehicle issues, one photo.

Synthetic fixtures only: generated images, fake receipts and temporary local
Git ledgers. No network.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

from PIL import Image
from synthetic_contact import SYNTHETIC_ID, SYNTHETIC_PHONE

from parking_report import api_cli
from parking_report.shared_issue import (
    GROUP_SIZE,
    canonical_manifest,
    check_sibling,
    group_fingerprint,
    sibling_record_path,
    validate_issue_pair,
)

ENV = {
    "PARKING_REPORTER_FIRST_NAME": "דנה",
    "PARKING_REPORTER_LAST_NAME": "לוי",
    "PARKING_REPORTER_PHONE": SYNTHETIC_PHONE,
    "PARKING_REPORTER_ID_NUMBER": SYNTHETIC_ID,
    "PARKING_REPORTER_EMAIL": "dana@example.com",
}
LIVE = dict(ENV, PARKING_106_ENABLE_LIVE="true")
SIGN, BOLLARD, LIGHT = "sign_request", "bollard_request", "lighting_request"
REFERENCE = "approval-synthetic-issue"
PATHS = {
    SIGN: ["שילוט ותמרורים", "אחר"],
    BOLLARD: ["גדרות, מעקות, עמודים", "אחר"],
    LIGHT: ["תאורה", "אחר"],
}


class Out(io.StringIO):
    def reconfigure(self, encoding=None):
        pass


class FakeMunicipality:
    created: ClassVar[list[str]] = []

    def __init__(self, credentials):
        pass

    def login(self):
        return "fake-token"

    def contact(self, token, reporter):
        return {}

    def create(self, token, contact, report):
        self.created.append(report["CaseDescription"])
        number = len(self.created)
        return {
            "CaseIdInCRM": f"fake-case-{number}",
            "WebCaseIdInCRM": f"fake-web-{number}",
            "CaseNumberInCRM": f"2601-{number:07d}",
        }

    def attach(self, token, case, jpeg, name):
        pass


def git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout


class SharedIssueBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.intakes = self.root / "intakes"
        self.intakes.mkdir()
        self.addresses = self.root / "addresses.json"
        self.addresses.write_text(
            json.dumps(
                {
                    "version": 1,
                    "streets": [{"StreetCode": "fake", "StreetName": "רחוב לדוגמה"}],
                    "addresses": [[31.77, 35.21, "1", "רחוב לדוגמה"]],
                }
            ),
            encoding="utf-8",
        )
        self.ledger_dir = self.make_ledger()
        self.outputs: list[str] = []
        FakeMunicipality.created = []

    def make_ledger(self):
        remote = self.root / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], capture_output=True)
        clone = self.root / "ledger"
        subprocess.run(["git", "clone", str(remote), str(clone)], capture_output=True)
        git(clone, "config", "user.name", "Test")
        git(clone, "config", "user.email", "test@example.invalid")
        git(clone, "checkout", "--orphan", "106-ledger")
        (clone / "ledger.json").write_text(
            json.dumps({"version": 1, "reports": {}, "photos": {}})
        )
        git(clone, "add", ".")
        git(clone, "commit", "-m", "Initialize")
        git(clone, "push", "origin", "HEAD:106-ledger")
        return clone

    def ledger_data(self):
        return json.loads((self.ledger_dir / "ledger.json").read_text(encoding="utf-8"))

    def issue(self, intake_id, event_type, color="white", description=None):
        folder = self.intakes / intake_id
        folder.mkdir()
        Image.new("RGB", (10, 10), color).save(folder / "photo.jpg")
        record = {
            "schema_version": 1,
            "status": "ready",
            "photo": "photo.jpg",
            "captured_at": "2026-01-01 12:00",
            "address": {"street": "רחוב לדוגמה", "house_number": "1"},
            "violation": {
                "category": event_type,
                "description": "נושא לדוגמה",
            },
            "municipal_subject": {
                "code": "5164",
                "owner_choice": True,
                "event_type": event_type,
                "path": PATHS[event_type],
            },
            "approved_description": description or f"טקסט מאושר {event_type}",
        }
        self.write(folder, record)
        return folder

    @staticmethod
    def write(folder, record):
        (folder / "report.json").write_text(json.dumps(record), encoding="utf-8")

    @staticmethod
    def record(folder):
        return json.loads((folder / "report.json").read_text(encoding="utf-8"))

    @staticmethod
    def photo_hash(folder):
        return hashlib.sha256((folder / "photo.jpg").read_bytes()).hexdigest()

    def manifest(self, photo_hash, ids=("issue-a", "issue-b"), issues=(SIGN, BOLLARD)):
        return {
            "intake_ids": list(ids),
            "issues": list(issues),
            "photo_sha256": photo_hash,
            "authority_reference": REFERENCE,
        }

    def attach(self, folder, manifest):
        record = self.record(folder)
        record["shared_photo_issue"] = manifest
        self.write(folder, record)

    def pair(self, same_photo=True):
        a = self.issue("issue-a", SIGN)
        b = self.issue("issue-b", BOLLARD, color="white" if same_photo else "black")
        manifest = self.manifest(self.photo_hash(a))
        self.attach(a, manifest)
        self.attach(b, manifest)
        return a, b, manifest

    def run_cli(self, argv, env=ENV):
        out, err = Out(), Out()
        with (
            patch.object(sys, "stdout", out),
            patch.object(sys, "stderr", err),
            patch.dict("os.environ", env, clear=False),
        ):
            code = api_cli.main([str(a) for a in argv])
        self.outputs += [out.getvalue(), err.getvalue()]
        return code, out.getvalue()

    def preview(self, folder, *extra):
        code, out = self.run_cli([folder, "--addresses", self.addresses, *extra])
        self.assertEqual(code, 0, out)
        return json.loads(out)["sha256"]

    def submit(self, folder, approval=None, *, digest=None, env=LIVE):
        digest = digest or self.preview(folder)
        argv = [
            folder,
            "--addresses",
            self.addresses,
            "--ledger-dir",
            self.ledger_dir,
            "--state-dir",
            self.root / "state",
            "--submit",
            "--approved-sha256",
            digest,
        ]
        if approval is not False:
            argv += ["--approved-shared-issue-sha256", approval or digest]
        with (
            patch("parking_report.api106.Municipality", FakeMunicipality),
            patch.object(api_cli, "post_submit_duplicate_check", return_value=[]),
        ):
            code, out = self.run_cli(argv, env)
        return code, json.loads(out)

    @staticmethod
    def key(intake_id):
        return hashlib.sha256(intake_id.encode()).hexdigest()


class ManifestValidationTests(SharedIssueBase):
    def test_exact_manifest_and_every_rejection(self):
        good = self.manifest("b" * 64)
        self.assertEqual(validate_issue_pair(good), good)
        for name, bad in (
            ("not an object", None),
            ("missing field", {k: v for k, v in good.items() if k != "issues"}),
            ("extra field", dict(good, extra="x")),
            ("repeated intake ID", dict(good, intake_ids=["issue-a", "issue-a"])),
            ("unsorted intake IDs", dict(good, intake_ids=["issue-b", "issue-a"])),
            ("unsafe intake ID", dict(good, intake_ids=["../a", "issue-b"])),
            ("same issue twice", dict(good, issues=[SIGN, SIGN])),
            ("unsafe issue", dict(good, issues=[SIGN, "x y"])),
            ("issue not text", dict(good, issues=[SIGN, 1])),
            ("issues not a list", dict(good, issues=SIGN)),
            ("bad photo hash", dict(good, photo_sha256="B" * 64)),
            ("blank authority", dict(good, authority_reference=" ")),
            ("authority not text", dict(good, authority_reference=1)),
        ):
            with self.subTest(name), self.assertRaises(ValueError):
                validate_issue_pair(bad)

    def test_group_is_bounded_to_exactly_two(self):
        self.assertEqual(GROUP_SIZE, 2)
        three = self.manifest("b" * 64, ids=["a", "b", "c"], issues=[SIGN, BOLLARD, LIGHT])
        with self.assertRaises(ValueError):
            validate_issue_pair(three)

    def test_sibling_path_names_the_other_member(self):
        a, b, manifest = self.pair()
        self.assertEqual(
            sibling_record_path(a, validate_issue_pair(manifest)),
            b / "report.json",
        )


class DigestBindingTests(SharedIssueBase):
    def test_manifest_binds_each_member_digest(self):
        a, b, manifest = self.pair()
        digest_a, digest_b = self.preview(a), self.preview(b)
        self.assertNotEqual(digest_a, digest_b)
        plain = self.issue("issue-c", LIGHT)
        self.assertNotEqual(self.preview(plain), digest_a)
        changed = dict(manifest, authority_reference="other-approval")
        self.attach(b, changed)
        self.attach(a, changed)
        self.assertNotEqual(self.preview(b), digest_b)

    def test_preview_reserves_nothing(self):
        a, b, manifest = self.pair()
        self.preview(a)
        self.assertEqual(self.ledger_data()["reports"], {})


class SubmissionTests(SharedIssueBase):
    def test_two_issues_one_photo_file_with_distinct_receipts(self):
        a, b, manifest = self.pair()
        code_a, out_a = self.submit(a)
        code_b, out_b = self.submit(b)
        self.assertEqual((code_a, code_b), (0, 0), self.outputs)
        data = self.ledger_data()
        origin = data["photos"][self.photo_hash(a)]
        self.assertEqual(origin, self.key("issue-a"))
        group = data["shared_photos"][self.photo_hash(a)]
        self.assertEqual(group["kind"], "issue")
        self.assertEqual(group["group"], group_fingerprint(validate_issue_pair(manifest)))
        self.assertEqual(
            data["reports"][self.key("issue-b")]["shared_issue"], group["group"]
        )
        self.assertNotEqual(out_a["sha256"], out_b["sha256"])

    def test_late_join_after_completed_ordinary_origin(self):
        a = self.issue("issue-a", SIGN)
        code, _ = self.submit(a, approval=False)
        self.assertEqual(code, 0, self.outputs)
        before = self.ledger_data()["reports"][self.key("issue-a")]
        b = self.issue("issue-b", BOLLARD)
        # Same original photo bytes for the second issue.
        b.joinpath("photo.jpg").write_bytes(a.joinpath("photo.jpg").read_bytes())
        manifest = self.manifest(self.photo_hash(a))
        self.attach(a, manifest)
        self.attach(b, manifest)
        code, out = self.submit(b)
        self.assertEqual(code, 0, self.outputs)
        data = self.ledger_data()
        self.assertEqual(data["reports"][self.key("issue-a")], before)
        self.assertEqual(data["photos"][self.photo_hash(a)], self.key("issue-a"))
        self.assertIn("shared_issue", data["reports"][self.key("issue-b")])

    def test_late_join_refused_when_origin_not_complete(self):
        a, b, manifest = self.pair()
        # Reserve the origin without submitting: preview with a ledger is still
        # reservation-free for members, so reserve by starting a submission
        # that fails before creation.
        digest = self.preview(a)
        argv = [
            a,
            "--addresses",
            self.addresses,
            "--ledger-dir",
            self.ledger_dir,
            "--state-dir",
            self.root / "state",
            "--submit",
            "--approved-sha256",
            digest,
            "--approved-shared-issue-sha256",
            digest,
        ]
        with patch("parking_report.api106.Municipality", side_effect=OSError):
            code, _ = self.run_cli(argv, LIVE)
        self.assertEqual(code, 4)
        data = self.ledger_data()
        self.assertEqual(
            data["reports"][self.key("issue-a")]["state"]["status"], "prepared"
        )
        # The origin is now a group member, not an ordinary intake; a second
        # member still joins because the group was locked by the origin.
        code, out = self.submit(b)
        self.assertEqual(code, 0, self.outputs)

    def test_second_member_refused_without_identical_sibling_manifest(self):
        a, b, manifest = self.pair()
        other = dict(manifest, authority_reference="different-approval")
        self.attach(b, other)
        code, out = self.submit(b)
        self.assertEqual(code, 4)
        self.assertEqual(out["status"], "blocked")

    def test_photo_belonging_to_another_intake_is_refused(self):
        a, b, manifest = self.pair()
        stranger = self.issue("issue-c", LIGHT)
        code, out = self.run_cli(
            [stranger, "--addresses", self.addresses, "--ledger-dir", self.ledger_dir]
        )
        self.assertEqual(code, 0)  # different photo: an ordinary new intake
        stranger2 = self.intakes / "issue-d"
        stranger2.mkdir()
        Image.new("RGB", (10, 10), "white").save(stranger2 / "photo.jpg")
        record = self.record(a)
        del record["shared_photo_issue"]
        self.write(stranger2, record)
        code, out = self.run_cli(
            [stranger2, "--addresses", self.addresses, "--ledger-dir", self.ledger_dir]
        )
        self.assertEqual(code, 4)
        self.assertIn("blocked", out)

    def test_live_member_requires_exact_issue_approval(self):
        a, b, manifest = self.pair()
        digest = self.preview(a)
        code, out = self.submit(a, approval="0" * 64, digest=digest)
        self.assertEqual(code, 4)
        self.assertEqual(out["status"], "blocked")
        self.assertEqual(FakeMunicipality.created, [])

    def test_vehicle_record_cannot_pair_as_issue(self):
        a, b, manifest = self.pair()
        record = self.record(a)
        record["plate"] = "10-000-01"
        self.write(a, record)
        code, out = self.run_cli([a, "--addresses", self.addresses])
        self.assertEqual(code, 4)
        self.assertIn("blocked", out)

    def test_sibling_check_rejects_unreadable_sibling(self):
        a, b, manifest = self.pair()
        b.joinpath("report.json").unlink()
        with self.assertRaises(ValueError):
            check_sibling(a, manifest)


if __name__ == "__main__":
    unittest.main()
