"""Offline Beit Shemesh Bina request contract. Execution is disabled by design."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urlsplit

ACTIVE = False
API_ENDPOINT = "https://bshemesh.moked-binaa.co.il/api/insert_call.php"
MAX_IMAGES = 4


class BeitShemeshDisabled(RuntimeError):
    """The owner has not enabled this municipality."""


def _text(data: Mapping[str, Any], key: str, required: bool = False) -> str:
    value = data.get(key, "")
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"Invalid {key}")
    return value.strip()


@dataclass(frozen=True)
class PreparedCall:
    """Private request data. Never print, publish or put it in an audit log."""

    parameters: tuple[tuple[str, str], ...] = field(repr=False)

    def encoded_query(self) -> str:
        """Encode for offline contract inspection only; contains private values."""
        return urlencode(self.parameters)


def prepare_call(
    reporter: Mapping[str, Any], event: Mapping[str, Any], *, secret: str
) -> PreparedCall:
    """Validate and prepare the app contract without network access.

    No subject/category field exists in this protocol. Vehicle facts, if needed,
    belong in the separately approved description. An ID number is not needed.
    """
    if not isinstance(reporter, Mapping) or not isinstance(event, Mapping):
        raise ValueError("Reporter and event must be mappings")
    if not isinstance(secret, str) or not secret.strip():
        raise ValueError("An explicit configured credential is required")
    phone = _text(reporter, "cellphone", True)
    if not re.fullmatch(r"05[0-9]{8}", phone):
        raise ValueError("Invalid cellphone")
    if reporter.get("tz"):
        raise ValueError("National ID is not part of this integration")
    params = {
        "secret": secret.strip(),
        "fn": _text(reporter, "fn", True),
        "ln": _text(reporter, "ln", True),
        "cellphone": phone,
        "email": _text(reporter, "email"),
        "myHome": _text(reporter, "my_home"),
        "address": _text(reporter, "address"),
        "hash": _text(reporter, "hash"),
        "tz": "",
        "description": _text(event, "description", True),
        "street": _text(event, "street", True),
        "home": _text(event, "home", True),
    }
    params.update(_location(event))
    params.update(_images(event))
    return PreparedCall(tuple(params.items()))


def _location(event: Mapping[str, Any]) -> dict[str, str]:
    params = {}
    street_id = _text(event, "street_id")
    coordinates = "event_lat" in event or "event_lng" in event
    if street_id:
        if coordinates or not re.fullmatch(r"[0-9]+", street_id):
            raise ValueError("Use one unambiguous location branch")
        params["streetId"] = street_id
    else:
        for key, bound in (("event_lat", 90), ("event_lng", 180)):
            number = event.get(key)
            if (
                isinstance(number, bool)
                or not isinstance(number, (int, float))
                or not math.isfinite(number)
                or abs(number) > bound
            ):
                raise ValueError("Invalid event coordinates")
            params[key] = str(number)
    return params


def _images(event: Mapping[str, Any]) -> dict[str, str]:
    params = {}
    images = event.get("images", [])
    if not isinstance(images, list) or len(images) > MAX_IMAGES:
        raise ValueError("Supply at most four image URLs; images are never truncated")
    for image in images:
        if not isinstance(image, str):
            raise ValueError("Invalid image URL")
        try:
            parsed = urlsplit(image)
            valid = (
                parsed.scheme == "https"
                and parsed.hostname == "uploads.binaa.co.il"
                and parsed.port in (None, 443)
                and parsed.username is None
                and parsed.password is None
                and parsed.path.startswith("/app.betshemesh.muni.il/")
                and not parsed.query
                and not parsed.fragment
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("Image URL is outside the documented upload origin")
    for i in range(MAX_IMAGES):
        params[f"img{i + 1}"] = images[i] if i < len(images) else ""
    return params


def submit_call(*args: Any, **kwargs: Any) -> None:
    """Always refuse. No flag, environment variable or caller can enable this."""
    raise BeitShemeshDisabled("Beit Shemesh integration is included but not enabled")
