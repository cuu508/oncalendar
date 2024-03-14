from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from oncalendar import OnCalendarError, TzIterator

NOW = datetime(2020, 1, 1, tzinfo=timezone.utc)


class TestTzIterator(unittest.TestCase):
    def test_it_works_as_iterator(self) -> None:
        hits = list(TzIterator("2020-01-01 8..9:0:0", NOW))
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0].isoformat(), "2020-01-01T08:00:00+00:00")
        self.assertEqual(hits[1].isoformat(), "2020-01-01T09:00:00+00:00")

    def test_it_handles_no_timezone(self) -> None:
        for sample in ("12:34", "*-*-* 12:34"):
            it = TzIterator(sample, NOW)
            self.assertEqual(next(it).isoformat(), "2020-01-01T12:34:00+00:00")
            self.assertEqual(next(it).isoformat(), "2020-01-02T12:34:00+00:00")

    def test_it_parses_timezone_from_schedule(self) -> None:
        it = TzIterator("12:34 Europe/Riga", NOW)
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
        with self.assertRaises(OnCalendarError):
            TzIterator("12:34 Europe/Surprise", NOW)
        with self.assertRaises(OnCalendarError):
            TzIterator("12:34 Europe/", NOW)

    def test_it_avoids_zoneinfo_inits(self) -> None:
        # Schedules where we can determine the last component is *not*
        # a timezone without calling ZoneInfo()
        samples = (
            "*-* *:*",  # no timezone contains ":"
            "Mon 1-10",  # no timezone starts with a digit
            "Mon *-10",  # no timezone starts with a star
        )
        for sample in samples:
            with patch("oncalendar.ZoneInfo", return_value=None) as mock:
                TzIterator(sample, NOW)
                self.assertFalse(mock.called)


class TestValidation(unittest.TestCase):
    def test_it_rejects_lone_timezone(self) -> None:
        for sample in ("Europe/Riga", " Europe/Riga", "Europe/Riga "):
            with self.assertRaisesRegex(OnCalendarError, "Bad day-of-week"):
                TzIterator(sample, NOW)


if __name__ == "__main__":
    unittest.main()
