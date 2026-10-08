"""Offline preview by default; one exact reviewed input may be submitted explicitly."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any

from .intake import record_to_car
from .report import build_report


def private_values(env: Mapping[str, str]) -> dict[str, str]:
    """Read reporter variables without printing sensitive values."""
    keys = ("first_name", "last_name", "phone", "id_number", "email")
    values = {k: env.get("PARKING_REPORTER_" + k.upper(), "") for k in keys}
    if not all(values.values()):
        raise ValueError("Set all PARKING_REPORTER_* values in private secrets/environment.")
    return values


def prepare(folder: Path, addresses: Path, reporter: Mapping[str, str]) -> tuple[dict[str, Any], dict[str, Any], bytes, str]:
    """Validate the original private record and prepare the same payload for both modes."""
    from .api106 import Addresses, make_contact, read_picture, check_text
    record = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    car = record_to_car(record)
    name = record.get("photo", "")
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise ValueError("report.json must name one local photo, without path traversal")
    photo = folder / name
    if photo.is_symlink():
        raise ValueError("Photo symlinks are not allowed")
    photo_hash, gps, jpeg = read_picture(photo)
    contact = make_contact(argparse.Namespace(first_name=reporter["first_name"],
        last_name=reporter["last_name"], phone=reporter["phone"],
        national_id=reporter["id_number"], email=reporter["email"]))
    address = record["address"]
    resolved = Addresses(addresses).resolve(check_text(address["street"], "Street"),
                                          str(address["house_number"]), gps)
    report = {"CaseDescription": build_report(car), "CaseSubjectCode": "1145",
        "CaseStreetCode": resolved["street_code"], "CaseStreetName": resolved["street_name"],
        "CaseHouseNumber": resolved["house"],
        "CaseAddressText": resolved["street_name"] + " " + resolved["house"],
        "CoordinateX": resolved["x"], "CoordinateY": resolved["y"],
        "Language": 1, "ApplicationCaseNumber": "ApplicationCaseNumber_VAL"}
    canonical = json.dumps({"reporter": contact, "report": report, "picture": photo_hash},
                           ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return contact, report, jpeg, digest


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder", type=Path)
    p.add_argument("--addresses", type=Path, required=True)
    p.add_argument("--state-dir", type=Path, default=Path(".106-state"))
    p.add_argument("--submit", action="store_true")
    p.add_argument("--approved-sha256", default="")
    p.add_argument("--retry-photo", action="store_true")
    args = p.parse_args(argv)
    try:
        from .api106 import Municipality, submit
        contact, report, jpeg, digest = prepare(args.folder, args.addresses, private_values(os.environ))
        if not args.submit:
            if args.retry_photo:
                raise ValueError("--retry-photo requires explicit submission approval")
            # Logs contain no reporter, plate, address, description, or photo metadata.
            print(json.dumps({"status": "dry_run", "sha256": digest,
                              "photo_upload_bytes": len(jpeg), "network_requests": 0}))
            return 0
        if os.environ.get("PARKING_106_ENABLE_LIVE") != "true" or args.approved_sha256 != digest:
            raise ValueError("Live submission needs private enablement and the exact reviewed digest")
        credentials = {"subscription_key": os.environ.get("PARKING_106_SUBSCRIPTION_KEY", ""),
            "login": {"UserName": os.environ.get("PARKING_106_USERNAME", ""),
                      "Password": os.environ.get("PARKING_106_PASSWORD", "")}}
        result = submit(Municipality(credentials), contact, report, jpeg, digest,
                        args.state_dir, args.retry_photo)
        # Case receipts remain in the private state ledger, not action logs.
        print(json.dumps({"status": result["status"], "sha256": digest,
                          "photo_attached": result["photo_attached"]}))
        return 0
    except Exception:
        # Do not log arbitrary validation, file, API, or subprocess details.
        print('{"status":"blocked","note":"Check private input and ledger; no automatic retry."}')
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
