"""Read-only presence checks. No real municipality traffic in automated tests."""
import unittest
from unittest.mock import MagicMock
from parking_report.inspect import inspect_page


class TestInspect(unittest.TestCase):
    def test_presence_and_selector(self):
        page = MagicMock()
        page.get_by_label.return_value.count.return_value = 1
        page.get_by_label.return_value.first.is_visible.return_value = True
        page.locator.return_value.count.return_value = 0
        config = {"fields": [
            {"label": "Name"}, {"label": "Absent", "selector": "#absent"}
        ]}
        self.assertEqual(inspect_page(page, config),
                         {"found": ["Name"], "not_found": ["Absent"]})
        page.get_by_label.return_value.fill.assert_not_called()
        page.locator.return_value.set_input_files.assert_not_called()

    def test_hidden_field_is_not_found(self):
        page = MagicMock()
        page.get_by_label.return_value.count.return_value = 1
        page.get_by_label.return_value.first.is_visible.return_value = False
        self.assertEqual(inspect_page(page, {"fields": [{"label": "Hidden"}]}),
                         {"found": [], "not_found": ["Hidden"]})
