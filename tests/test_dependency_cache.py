"""Offline regression for dependency cache inputs, not a cache-hit qualification."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DependencyCacheTests(unittest.TestCase):
    def test_all_test_caches_cover_installed_locks(self):
        text = (ROOT / ".github/workflows/tests.yml").read_text()
        self.assertEqual(text.count("cache: pip"), 6)
        self.assertEqual(text.count("cache-dependency-path: requirements/*.txt"), 6)
        self.assertNotIn("cache-dependency-path: pyproject.toml", text)
        self.assertIn(
            "--require-hashes -r requirements/build.txt -r requirements/api.txt", text
        )
        self.assertIn("-r requirements/ci.txt", text)
        self.assertNotIn("cache-hit", text)
        self.assertNotIn("restore-keys:", text)

    def test_api_cache_is_scoped_to_helper_downloads_and_locks(self):
        text = (ROOT / ".github/workflows/api106.yml").read_text()
        self.assertIn("helper/requirements/build.txt", text)
        self.assertIn("helper/requirements/api.txt", text)
        self.assertIn("--require-hashes", text)

    def test_pinned_action_owns_compatible_runtime_fallback(self):
        for name in ("tests.yml", "api106.yml"):
            text = (ROOT / ".github/workflows" / name).read_text()
            self.assertIn(
                "actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0", text
            )


if __name__ == "__main__":
    unittest.main()
