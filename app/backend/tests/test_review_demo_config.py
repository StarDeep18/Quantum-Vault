"""Review demo mode is an explicit opt-in and defaults OFF."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from qlab.config import review_demo_enabled


class ReviewDemoConfigTests(unittest.TestCase):
    def test_review_demo_defaults_off(self) -> None:
        with patch("qlab.config.get_setting", return_value=None):
            self.assertFalse(review_demo_enabled())
        with patch("qlab.config.get_setting", return_value="false"):
            self.assertFalse(review_demo_enabled())

    def test_review_demo_requires_explicit_truthy_setting(self) -> None:
        for value in ("true", "TRUE", "1", "yes", "on"):
            with self.subTest(value=value), patch("qlab.config.get_setting", return_value=value):
                self.assertTrue(review_demo_enabled())


if __name__ == "__main__":
    unittest.main()
