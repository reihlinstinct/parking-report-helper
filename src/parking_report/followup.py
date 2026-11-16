"""Validate private follow-up audit metadata; never infer owner permission."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

_COMMON_FIELDS = {
    "parent_id",
    "parent_digest",
    "parent_case_number",
    "approval_reference",
}

_CLOSED_FIELDS = _COMMON_FIELDS | {"parent_closed_at"}
_RESPONSE_FIELDS = _COMMON_FIELDS | {
    "reply_received_at",
    "reply_reference",
    "parent_status",
}


def validate_followup(value: Any) -> dict[str, str]:
    """Return exact validated metadata; reject partial or unknown fields."""
    if not isinstance(value, dict) or set(value) not in (
        _CLOSED_FIELDS,
        _RESPONSE_FIELDS,
    ):
        raise ValueError("Follow-up manifest must contain the exact required fields")
    if not all(isinstance(v, str) and v and v == v.strip() for v in value.values()):
        raise ValueError("Invalid follow-up metadata")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", value["parent_id"]):
        raise ValueError("Invalid follow-up parent ID")
    if not re.fullmatch(r"[0-9a-f]{64}", value["parent_digest"]):
        raise ValueError("Invalid follow-up parent digest")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{1,20}", value["parent_case_number"]):
        raise ValueError("Invalid follow-up parent reference")
    if set(value) == _CLOSED_FIELDS:
        timestamp = value["parent_closed_at"]
    else:
        if value["parent_status"] != "unknown":
            raise ValueError("Response follow-up must preserve unknown parent status")
        if not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_:/.-]{0,199}", value["reply_reference"]
        ):
            raise ValueError("Invalid municipal reply evidence reference")
        timestamp = value["reply_received_at"]
    observed = datetime.fromisoformat(timestamp)
    if observed.tzinfo is None:
        raise ValueError("Follow-up observation needs a timezone")
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_:/.-]{0,199}", value["approval_reference"]
    ):
        raise ValueError("Invalid approval evidence reference")
    return dict(value)
