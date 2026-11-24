import unittest

from app.infrastructure.security.device_metadata import parse_device_metadata


class DeviceMetadataTests(unittest.TestCase):
    def test_parses_mobile_device_metadata(self) -> None:
        metadata = parse_device_metadata(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Mobile/15E148 Safari/604.1"
        )

        self.assertEqual(
            metadata,
            ("iPhone", "mobile", "Mobile Safari", "iOS"),
        )

    def test_missing_or_unrecognized_user_agent_is_safe(self) -> None:
        self.assertEqual(parse_device_metadata(None), (None, None, None, None))
        self.assertEqual(parse_device_metadata(""), (None, None, None, None))

    def test_long_user_agent_is_bounded_and_values_fit_columns(self) -> None:
        metadata = parse_device_metadata("x" * 10000)

        self.assertEqual(len(metadata), 4)
        for value, limit in zip(metadata, (150, 50, 100, 100), strict=True):
            self.assertTrue(value is None or len(value) <= limit)
