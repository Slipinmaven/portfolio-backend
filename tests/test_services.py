import unittest

from app.application.auth.service import normalize_email


class AuthServiceTests(unittest.TestCase):
    def test_normalize_email_trims_whitespace_and_lowercases(self) -> None:
        self.assertEqual(
            normalize_email(" User@Example.COM "),
            "user@example.com",
        )
