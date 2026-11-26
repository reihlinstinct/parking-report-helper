"""Synthetic offline controls for the disabled Beit Shemesh backend."""

import os
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch
from urllib.parse import parse_qs

from parking_report import beit_shemesh as bs

REPORTER = {"fn": "בדיקה", "ln": "סינתטית", "cellphone": "0500000000"}
EVENT = {
    "description": "ניסיון סינתטי בלבד",
    "street": "רחוב בדיקה",
    "home": "1",
    "street_id": "42",
}


class BeitShemeshContractTest(unittest.TestCase):
    def setUp(self):
        self.network = patch(
            "urllib.request.urlopen", side_effect=AssertionError("Network forbidden")
        )
        self.network.start()
        self.addCleanup(self.network.stop)

    def prepare(self, reporter=None, event=None, secret="synthetic-only"):
        return bs.prepare_call(
            REPORTER if reporter is None else reporter,
            EVENT if event is None else event,
            secret=secret,
        )

    def test_street_contract_and_hebrew_encoding(self):
        call = self.prepare()
        params = parse_qs(call.encoded_query(), keep_blank_values=True)
        self.assertEqual(params["description"], [EVENT["description"]])
        self.assertEqual(params["streetId"], ["42"])
        self.assertEqual(params["tz"], [""])
        self.assertNotIn("event_lat", params)
        self.assertEqual(params["img4"], [""])
        self.assertEqual(params["hash"], [""])

    def test_gps_contract(self):
        event = dict(EVENT, event_lat=31.74, event_lng=34.99)
        del event["street_id"]
        params = dict(self.prepare(event=event).parameters)
        self.assertNotIn("streetId", params)
        self.assertEqual(params["event_lat"], "31.74")

    def test_required_fields(self):
        for key in ("fn", "ln", "cellphone"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.prepare(reporter=dict(REPORTER, **{key: ""}))
        for key in ("description", "street", "home"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.prepare(event=dict(EVENT, **{key: ""}))
        for secret in ("", " ", None):
            with self.subTest(secret=secret), self.assertRaises(ValueError):
                self.prepare(secret=secret)

    def test_invalid_phone_and_id_refused(self):
        for reporter in (
            dict(REPORTER, cellphone="not-a-phone"),
            dict(REPORTER, tz="synthetic-id"),
        ):
            with self.assertRaises(ValueError):
                self.prepare(reporter=reporter)

    def test_ambiguous_missing_invalid_coordinates_refused(self):
        with self.assertRaises(ValueError):
            self.prepare(event=dict(EVENT, event_lat=31, event_lng=34))
        for lat, lon in (
            (True, 34),
            (float("nan"), 34),
            (91, 34),
            (31, 181),
            (31, None),
        ):
            event = dict(EVENT, event_lat=lat, event_lng=lon)
            del event["street_id"]
            with self.subTest(lat=lat, lon=lon), self.assertRaises(ValueError):
                self.prepare(event=event)
        event = dict(EVENT)
        del event["street_id"]
        with self.assertRaises(ValueError):
            self.prepare(event=event)

    def test_images_never_truncated_and_other_origins_refused(self):
        url = "https://uploads.binaa.co.il/app.betshemesh.muni.il/2026/11/synthetic.png"
        self.assertEqual(
            dict(self.prepare(event=dict(EVENT, images=[url] * 4)).parameters)["img4"],
            url,
        )
        for images in (
            [url] * 5,
            "not-a-list",
            [None],
            ["http://uploads.binaa.co.il/x"],
            ["https://other.invalid/x"],
            [url + "?token=synthetic"],
            ["https://uploads.binaa.co.il:bad/app.betshemesh.muni.il/x"],
        ):
            with self.subTest(images=images), self.assertRaises(ValueError):
                self.prepare(event=dict(EVENT, images=images))

    def test_private_values_excluded_from_repr_and_immutable(self):
        call = self.prepare()
        self.assertNotIn("synthetic-only", repr(call))
        self.assertNotIn(REPORTER["cellphone"], repr(call))
        with self.assertRaises(FrozenInstanceError):
            call.parameters = ()

    def test_execution_always_disabled_despite_legacy_flags(self):
        self.assertIs(bs.ACTIVE, False)
        with patch.dict(
            os.environ,
            {"BSMOKED_LIVE": "1", "BSMOKED_SECRET": "synthetic-only", "LIVE": "1"},
        ):
            for call in (
                lambda: bs.submit_call(self.prepare(), live=True),
                lambda: bs.submit_call(),
                lambda: bs.submit_call(REPORTER, EVENT, enabled=True),
            ):
                with self.assertRaises(bs.BeitShemeshDisabled):
                    call()


if __name__ == "__main__":
    unittest.main()
