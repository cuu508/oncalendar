from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from oncalendar import OnCalendarError, TzIterator


class TestTzIterator(unittest.TestCase):
    def test_it_handles_no_timezone(self) -> None:
        now = datetime(2020, 1, 1, tzinfo=timezone.utc)
        for sample in ("12:34", "*-*-* 12:34"):
            it = TzIterator(sample, now)
            self.assertEqual(next(it).isoformat(), "2020-01-01T12:34:00+00:00")
            self.assertEqual(next(it).isoformat(), "2020-01-02T12:34:00+00:00")

    def test_it_parses_timezone_from_schedule(self) -> None:
        now = datetime(2020, 1, 1, tzinfo=timezone.utc)
        it = TzIterator("12:34 Europe/Riga", now)
        self.assertEqual(next(it).isoformat(), "2020-01-01T10:34:00+00:00")
        self.assertEqual(next(it).isoformat(), "2020-01-02T10:34:00+00:00")

    def test_it_preserves_local_timezone(self) -> None:
        now = datetime(2020, 1, 1, tzinfo=ZoneInfo("Europe/Berlin"))
        it = TzIterator("12:34 Europe/Riga", now)
        self.assertEqual(next(it).isoformat(), "2020-01-01T11:34:00+01:00")
        self.assertEqual(next(it).isoformat(), "2020-01-02T11:34:00+01:00")

    def test_it_requires_aware_datetime(self) -> None:
        now = datetime(2020, 1, 1)
        with self.assertRaises(OnCalendarError):
            TzIterator("12:34", now)

    def test_it_handles_bad_timezone(self) -> None:
        now = datetime(2020, 1, 1, tzinfo=timezone.utc)
        with self.assertRaises(OnCalendarError):
            TzIterator("12:34 Europe/Surprise", now)
        with self.assertRaises(OnCalendarError):
            TzIterator("12:34 Europe/", now)

    def test_it_avoids_zoneinfo_inits(self) -> None:
        now = datetime(2020, 1, 1, tzinfo=timezone.utc)
        # Schedules where we can determine the last component is *not*
        # a timezone without calling ZoneInfo()
        samples = (
            "*-* *:*",  # no timezone contains ":"
            "Mon 1-10",  # no timezone starts with a digit
            "Mon *-10",  # no timezone starts with a star
        )
        for sample in samples:
            with patch("oncalendar.ZoneInfo", return_value=None) as mock:
                TzIterator(sample, now)
                self.assertFalse(mock.called)


if __name__ == "__main__":
    unittest.main()
