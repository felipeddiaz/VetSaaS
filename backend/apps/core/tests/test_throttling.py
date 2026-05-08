from django.test import SimpleTestCase

from apps.core.throttling import ExtendedRateThrottle


class _DummyThrottle(ExtendedRateThrottle):
    scope = "dummy"
    rate = "1/min"

    def get_cache_key(self, request, view):
        return "dummy"


class ExtendedRateThrottleTests(SimpleTestCase):
    def setUp(self):
        self.throttle = _DummyThrottle()

    def test_parse_rate_supports_drf_native_format(self):
        num, duration = self.throttle.parse_rate("5/min")
        self.assertEqual(num, 5)
        self.assertEqual(duration, 60)

    def test_parse_rate_supports_extended_window_minutes(self):
        num, duration = self.throttle.parse_rate("5/15min")
        self.assertEqual(num, 5)
        self.assertEqual(duration, 900)

    def test_parse_rate_supports_extended_window_hours_short_unit(self):
        num, duration = self.throttle.parse_rate("10/2h")
        self.assertEqual(num, 10)
        self.assertEqual(duration, 7200)

    def test_parse_rate_raises_for_invalid_extended_unit(self):
        with self.assertRaises(ValueError):
            self.throttle.parse_rate("5/10weeks")
