from __future__ import annotations

import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from oncalendar import OnCalendar, OnCalendarError


class TestTzIterator(unittest.TestCase):
    tz = ZoneInfo("Europe/Riga")

    def test_it_works(self) -> None:
        now = datetime(2020, 1, 1, tzinfo=timezone.utc)
        it = OnCalendar("00:00\n12:34", now)
        self.assertEqual(next(it).isoformat(), "2020-01-01T12:34:00+00:00")
        self.assertEqual(next(it).isoformat(), "2020-01-02T00:00:00+00:00")
        self.assertEqual(next(it).isoformat(), "2020-01-02T12:34:00+00:00")
        self.assertEqual(next(it).isoformat(), "2020-01-03T00:00:00+00:00")

    def test_it_requires_aware_datetime(self) -> None:
        now = datetime(2020, 1, 1)
        with self.assertRaises(OnCalendarError):
            OnCalendar("12:34", now)

    def test_it_handles_subiterator_stopiteration(self) -> None:
        now = datetime(2020, 1, 1, tzinfo=timezone.utc)
        it = OnCalendar("2020-01-02\n12:34", now)
        self.assertEqual(next(it).isoformat(), "2020-01-01T12:34:00+00:00")
        self.assertEqual(next(it).isoformat(), "2020-01-02T00:00:00+00:00")
        self.assertEqual(next(it).isoformat(), "2020-01-02T12:34:00+00:00")
        self.assertEqual(next(it).isoformat(), "2020-01-03T12:34:00+00:00")

    def test_it_handles_no_occurences(self) -> None:
        now = datetime(2020, 1, 1, tzinfo=timezone.utc)
        it = OnCalendar("2018-01-01\n2019-01-01", now)
        with self.assertRaises(StopIteration):
            print(next(it))


if __name__ == "__main__":
    unittest.main()
