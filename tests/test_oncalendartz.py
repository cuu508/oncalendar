from __future__ import annotations

import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from oncalendar import OnCalendarError, OnCalendarTz


class TestOnCalendarTz(unittest.TestCase):
    tz = ZoneInfo("Europe/Riga")

    def test_it_handles_no_timezone(self) -> None:
        now = datetime(2020, 1, 1, tzinfo=timezone.utc)
        for sample in ("12:34", "*-*-* 12:34"):
            it = OnCalendarTz(sample, now)
            self.assertEqual(next(it).isoformat(), "2020-01-01T12:34:00+00:00")
            self.assertEqual(next(it).isoformat(), "2020-01-02T12:34:00+00:00")

    def test_it_parses_timezone_from_schedule(self) -> None:
        now = datetime(2020, 1, 1, tzinfo=timezone.utc)
        it = OnCalendarTz("12:34 Europe/Riga", now)
        self.assertEqual(next(it).isoformat(), "2020-01-01T10:34:00+00:00")
        self.assertEqual(next(it).isoformat(), "2020-01-02T10:34:00+00:00")

    def test_it_preserves_local_timezone(self) -> None:
        now = datetime(2020, 1, 1, tzinfo=ZoneInfo("Europe/Berlin"))
        it = OnCalendarTz("12:34 Europe/Riga", now)
        self.assertEqual(next(it).isoformat(), "2020-01-01T11:34:00+01:00")
        self.assertEqual(next(it).isoformat(), "2020-01-02T11:34:00+01:00")

    def test_it_requires_aware_datetime(self) -> None:
        now = datetime(2020, 1, 1)
        with self.assertRaises(OnCalendarError):
            OnCalendarTz("12:34", now)

    def test_it_handles_bad_timezone(self) -> None:
        now = datetime(2020, 1, 1, tzinfo=timezone.utc)
        with self.assertRaises(OnCalendarError):
            OnCalendarTz("12:34 Europe/Surprise", now)


if __name__ == "__main__":
    unittest.main()
