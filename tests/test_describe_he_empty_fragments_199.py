"""describe_he omits colour / tag-kind fragments that strip to empty (#199).

Synthetic lookup() results only; exact whole-text output. Meaningful padded
values and numeric tag kind 0 are kept; everything else is unchanged.
"""

import unittest

from parking_report.registry import describe_he

HEAD = "בדיקה במאגרי משרד התחבורה (נכון ל-27.10.2026):"


def result(**changes):
    """Same synthetic shape as tests/test_describe_he_split_195.py."""
    return {
        "plate": "1234567",
        "checked_on": "2026-10-27",
        "vehicle_lookup": "matched",
        "licence_status": "valid_on_check_date",
        "vehicle": {
            "tozeret_nm": " טויוטה ",
            "degem_nm": "קורולה",
            "kinuy_mishari": " היבריד ",
            "tzeva_rechev": "לבן",
            "tokef_dt": "2027-01-05T00:00:00",
            "mivchan_acharon_dt": "2026-01-04",
        },
        "disability_lookup": "matched",
        "disability": {"SUG TAV": 0, "TAARICH HAFAKAT TAG": "20250101"},
    } | changes


VEHICLE = " רכב מסוג טויוטה קורולה (היבריד)"
LICENCE = " תוקף רישיון הרכב עד 5.1.2027 (בתוקף). מבחן רישוי אחרון: 4.1.2026."
TAG = " לרכב רשום תג נכה במאגר תגי הנכים"
ISSUED = ", הונפק ב-1.1.2025."


def text_for(colour=..., kind=...):
    vehicle = dict(result()["vehicle"])
    if colour is ...:
        vehicle.pop("tzeva_rechev")
    else:
        vehicle["tzeva_rechev"] = colour
    disability = {"TAARICH HAFAKAT TAG": "20250101"}
    if kind is not ...:
        disability["SUG TAV"] = kind
    return describe_he(result(vehicle=vehicle, disability=disability))


class TestColour(unittest.TestCase):
    def test_empty_after_strip_is_omitted(self):
        for colour in (" ", "   ", "\t", "\n", " \t\n ", "", None, ...):
            with self.subTest(colour=colour):
                self.assertEqual(
                    text_for(colour=colour),
                    HEAD + VEHICLE + "." + LICENCE + TAG + ISSUED,
                )

    def test_padded_colour_is_kept_stripped(self):
        for colour in ("לבן", "  לבן  ", "\tלבן\n"):
            with self.subTest(colour=colour):
                self.assertEqual(
                    text_for(colour=colour),
                    HEAD + VEHICLE + ", צבע לבן." + LICENCE + TAG + ISSUED,
                )


class TestTagKind(unittest.TestCase):
    def test_empty_after_strip_is_omitted(self):
        for kind in (" ", "   ", "\t", "\n", " \t\n ", "", None, ...):
            with self.subTest(kind=kind):
                self.assertEqual(
                    text_for(kind=kind), HEAD + VEHICLE + "." + LICENCE + TAG + ISSUED
                )

    def test_meaningful_kinds_are_kept(self):
        for kind, shown in (
            (0, "0"),
            ("0", "0"),
            (3, "3"),
            ("  3  ", "3"),
            ("\t7\n", "7"),
        ):
            with self.subTest(kind=kind):
                self.assertEqual(
                    text_for(kind=kind),
                    HEAD
                    + VEHICLE
                    + "."
                    + LICENCE
                    + TAG
                    + f" (קוד סוג תג: {shown})"
                    + ISSUED,
                )


if __name__ == "__main__":
    unittest.main()
