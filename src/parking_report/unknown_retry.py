"""Explicit owner-approved one-off duplicate-risk acceptance, never automatic."""

from __future__ import annotations

from typing import Any

from .supersedes import validate_supersedes


def validate_unknown_retry(value: Any, intake_id: str | None = None) -> dict[str, str]:
    """Exact private audit fields; caller must verify the original owner approval."""
    return validate_supersedes(value, intake_id)
