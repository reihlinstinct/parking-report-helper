"""SVG chart and HTML report tests on synthetic aggregates (#210)."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from parking_report.stats_charts import (
    category_chart,
    closure_chart,
    horizontal_bars,
    monthly_chart,
    street_chart,
)
from parking_report.stats_html import build_report

MONTHS = {"2026-05": 4, "2026-06": 4, "2026-07": 4}
CATEGORIES = {"חניה אסורה - חניה על מדרכה": 9, "חניה אסורה- אדום לבן": 2}
STREETS = {"רחוב הדוגמה": 6, "(ללא רחוב)": 1}
BUCKETS = {"עד שעה": 3, "שעה עד 8 שעות": 2, "מעל שבוע": 2}


def _parse(svg: str) -> ET.Element:
    return ET.fromstring(svg)


class HorizontalBarsTest(unittest.TestCase):
    def test_valid_svg_with_all_labels(self):
        svg = horizontal_bars([("רחוב הדוגמה", 5), ("רחוב הסינתטי", 2)], title="בדיקה")
        root = _parse(svg)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertIn("רחוב הדוגמה", svg)
        self.assertIn("רחוב הסינתטי", svg)
        self.assertIn("בדיקה", svg)
        self.assertIn('dir="rtl"', svg)

    def test_html_injection_escaped(self):
        svg = horizontal_bars([("<script>alert(1)</script>", 1)], title="x")
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)

    def test_empty_series_renders_placeholder(self):
        svg = horizontal_bars([], title="ריק")
        self.assertIn("אין נתונים", svg)
        _parse(svg)

    def test_bar_lengths_proportional(self):
        svg = horizontal_bars([("א", 10), ("ב", 5)], title="x")
        self.assertIn('width="400"', svg)
        self.assertIn('width="200"', svg)


class ChartBuildersTest(unittest.TestCase):
    def test_each_builder_renders(self):
        for chart in (
            monthly_chart(MONTHS),
            category_chart(CATEGORIES),
            street_chart(STREETS),
            closure_chart(BUCKETS),
        ):
            _parse(chart)


class BuildReportTest(unittest.TestCase):
    def _summary(self):
        return {
            "total_incidents": 13,
            "duplicates_skipped": 1,
            "date_range": {"first": "2026-05-01", "last": "2026-07-04"},
            "by_month": MONTHS,
            "by_category": CATEGORIES,
            "by_street": STREETS,
            "by_status": {"סיום טיפול": 9, "בטיפול": 4},
            "closure": {
                "closed_count": 9,
                "median_days": 0.5,
                "p25_days": 0.1,
                "p75_days": 2.0,
                "max_days": 19.0,
                "buckets": BUCKETS,
                "median_days_by_category": {"חניה אסורה - חניה על מדרכה": 1.0},
            },
            "inputs": ["synthetic.json"],
        }

    def test_full_document(self):
        page = build_report(self._summary())
        self.assertIn('<html lang="he" dir="rtl">', page)
        self.assertIn("סטטיסטיקת דיווחי 106", page)
        self.assertEqual(page.count("<svg"), 4)
        self.assertIn("2026-05-01", page)
        self.assertIn("synthetic.json", page)

    def test_no_external_resources(self):
        page = build_report(self._summary())
        self.assertNotIn("http://", page.replace("http://www.w3.org/2000/svg", ""))
        self.assertNotIn("https://", page)


if __name__ == "__main__":
    unittest.main()
