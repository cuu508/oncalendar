from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time
from datetime import timedelta as td
from datetime import timezone
from enum import IntEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc

MAX_YEAR = 2200
RANGES = [
    range(0, 7),
    range(1970, MAX_YEAR),
    range(1, 13),
    range(1, 32),
    range(0, 24),
    range(0, 60),
    range(0, 60),
]
SYMBOLIC_DAYS = "MONDAY TUESDAY WEDNESDAY THURSDAY FRIDAY SATURDAY SUNDAY".split()
SYMBOLIC_DAYS_SHORT = [s[:3] for s in SYMBOLIC_DAYS]
DAYS_IN_MONTH = [-1, 31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
FIELD_NAMES = [
    "day-of-week",
    "year",
    "month",
    "day-of-month",
    "hour",
    "minute",
    "second",
]
SPECIALS = {
    "minutely": "*-*-* *:*:00",
    "hourly": "*-*-* *:00:00",
    "daily": "*-*-* 00:00:00",
    "monthly": "*-*-01 00:00:00",
    "weekly": "Mon *-*-* 00:00:00",
    "yearly": "*-01-01 00:00:00",
    "annually": "*-01-01 00:00:00",
    "quarterly": "*-01,04,07,10-01 00:00:00",
    "semiannually": "*-01,07-01 00:00:00",
}
SECOND = td(seconds=1)
MINUTE = td(minutes=1)
HOUR = td(hours=1)


class OnCalendarError(Exception):
    pass


class Field(IntEnum):
    DOW = 0
    YEAR = 1
    MONTH = 2
    DAY = 3
    HOUR = 4
    MINUTE = 5
    SECOND = 6

    def msg(self) -> str:
        return "Bad %s" % FIELD_NAMES[self]

    def _int(self, value: str) -> int:
        if value == "":
            raise OnCalendarError(self.msg())
        for ch in value:
            if ch not in "0123456789":
                raise OnCalendarError(self.msg())

        return int(value)

    def int(self, s: str) -> int:
        if self == Field.DOW:
            s = s.upper()
            if s in SYMBOLIC_DAYS:
                # Monday -> 0, ..., Sunday -> 6
                return SYMBOLIC_DAYS.index(s)
            if s in SYMBOLIC_DAYS_SHORT:
                # Mon -> 0, ..., Sun -> 6
                return SYMBOLIC_DAYS_SHORT.index(s)
            raise OnCalendarError(self.msg())

        v = self._int(s)
        if self == Field.YEAR and v < 70:
            # Interpret 0-69 as 2000-2069
            v += 2000
        if self == Field.YEAR and v < 100:
            # Interpret 70-99 as 1970-1999
            v += 1900

        if v not in RANGES[self]:
            raise OnCalendarError(self.msg())

        return v

    def parse(self, s: str, reverse: bool = False) -> set[int]:
        if s == "*" and self != Field.DOW:
            return set(RANGES[self])

        if self == Field.DOW and s.endswith(","):
            # Ignore trailing comma
            return self.parse(s[:-1])

        if self == Field.DAY and s.startswith("~"):
            # Chop leading "~" and set the reverse flag
            return self.parse(s[1:], reverse=True)

        if "," in s:
            result = set()
            for term in s.split(","):
                result.update(self.parse(term, reverse=reverse))
            return result

        if "/" in s and self != Field.DOW:
            term, step_str = s.split("/", maxsplit=1)
            step = self._int(step_str)
            if step == 0:
                raise OnCalendarError(self.msg())

            items = self.parse(term, reverse=reverse)

            if len(items) == 1:
                start = items.pop()
                assert isinstance(start, int)
                end = 0 if reverse else max(RANGES[self])
                tail = range(start, end + 1)
                return set(tail[::step])

            # items is an unordered set, so sort it before taking
            # every step-th item. Then convert it back to set.
            return set(sorted(items)[::step])

        if ".." in s:
            start_str, end_str = s.split("..", maxsplit=1)
            start = self.int(start_str)
            end = self.int(end_str)

            if end < start:
                raise OnCalendarError(self.msg())

            if reverse:
                start, end = -end, -start

            return set(range(start, end + 1))

        v = self.int(s)
        if reverse:
            # When using <month>~<day> syntax, systemd rejects day values above 28
            if v > 28:
                raise OnCalendarError(self.msg())
            v = -v

        return {v}


def is_imaginary(dt: datetime) -> bool:
    return dt != dt.astimezone(UTC).astimezone(dt.tzinfo)


class OnCalendar(object):
    def __init__(self, expr: str, dt: datetime):
        self.dt = dt.replace(microsecond=0)

        if expr in SPECIALS:
            expr = SPECIALS[expr]

        # FIXME disallow "-~" in input
        expr = expr.replace("~", "-~")
        parts = expr.split()
        # If weekday is missing, use default
        if "-" in parts[0] or ":" in parts[0]:
            parts.insert(0, "Mon..Sun")

        # If date is missing, use default
        if len(parts) == 1 or "-" not in parts[1]:
            parts.insert(1, "*-*-*")

        # If time is missing, use default
        if len(parts) == 2 or ":" not in parts[2]:
            parts.insert(2, "0:0:0")

        if len(parts) != 3:
            raise OnCalendarError("Wrong number of fields")

        self.weekdays = Field.DOW.parse(parts[0])

        date_parts = parts[1].split("-")
        # If year is missing, use default
        if len(date_parts) == 2:
            date_parts.insert(0, "*")
        if len(date_parts) != 3:
            raise OnCalendarError("Bad date")
        self.years = Field.YEAR.parse(date_parts[0])
        self.months = Field.MONTH.parse(date_parts[1])
        self.days = Field.DAY.parse(date_parts[2])

        time_parts = parts[2].split(":")
        # If seconds is missing, use default
        if len(time_parts) == 2:
            time_parts.append("0")
        if len(time_parts) != 3:
            raise OnCalendarError("Bad time")
        self.hours = Field.HOUR.parse(time_parts[0])
        self.minutes = Field.MINUTE.parse(time_parts[1])
        self.seconds = Field.SECOND.parse(time_parts[2])

        self.fixup_tz = None
        if self.dt.tzinfo in (None, UTC):
            # No special DST handling for UTC
            pass
        else:
            self.fixup_tz = self.dt.tzinfo
            self.dt = self.dt.replace(tzinfo=None)

        self.any_reverse_day = any(d < 0 for d in self.days)

    def advance_second(self) -> bool:
        """Roll forward the second component until it satisfies the constraints.

        Return False if the second meets contraints without modification.
        Return True if self.dt was rolled forward.

        """

        if self.dt.second in self.seconds:
            return False

        if len(self.seconds) == 1:
            # An optimization for the special case where self.seconds has exactly
            # one element. Instead of advancing one second per iteration,
            # make a jump from the current second to the target second.
            delta = (next(iter(self.seconds)) - self.dt.second) % 60
            self.dt += td(seconds=delta)

        while self.dt.second not in self.seconds:
            self.dt += SECOND
            if self.dt.second == 0:
                # Break out to re-check year, month, day, hour, and minute
                break

        return True

    def advance_minute(self) -> bool:
        """Roll forward the minute component until it satisfies the constraints.

        Return False if the minute meets contraints without modification.
        Return True if self.dt was rolled forward.

        """

        if self.dt.minute in self.minutes:
            return False

        self.dt = self.dt.replace(second=0)
        while self.dt.minute not in self.minutes:
            self.dt += MINUTE
            if self.dt.minute == 0:
                # Break out to re-check year, month, day and hour
                break

        return True

    def advance_hour(self) -> bool:
        """Roll forward the hour component until it satisfies the constraints.

        Return False if the hour meets contraints without modification.
        Return True if self.dt was rolled forward.

        """

        if self.dt.hour in self.hours:
            return False

        self.dt = self.dt.replace(minute=0)
        while self.dt.hour not in self.hours:
            self.dt += HOUR
            if self.dt.hour == 0:
                # break out to re-check year, month and day
                break

        return True

    def match_dom(self, d: date) -> bool:
        """Return True is day-of-month matches."""
        if d.day in self.days:
            return True

        if self.any_reverse_day:
            _, last = monthrange(d.year, d.month)
            if d.day - last - 1 in self.days:
                return True

        return False

    def match_dow(self, d: date) -> bool:
        """Return True is day-of-week matches."""

        return d.weekday() in self.weekdays

    def advance_day(self) -> bool:
        """Roll forward the day component until it satisfies the constraints.

        This method advances the date until it matches the
        day-of-week and the day-of-month constraints.

        Return False if the day meets contraints without modification.
        Return True if self.dt was rolled forward.

        """

        needle = self.dt.date()
        if self.match_dow(needle) and self.match_dom(needle):
            return False

        while not self.match_dow(needle) or not self.match_dom(needle):
            needle += td(days=1)
            if needle.day == 1:
                # We're in a different month now, break out to re-check year and month
                # This significantly speeds up the "0 0 * 2 MON#5" case
                break

        self.dt = datetime.combine(needle, time(), tzinfo=self.dt.tzinfo)
        return True

    def advance_month(self) -> bool:
        """Roll forward the month component until it satisfies the constraints.

        Return False if the month meets contraints without modification.
        Return True if self.dt was rolled forward.

        """

        if self.dt.month in self.months:
            return False

        needle = self.dt.date()
        while needle.month not in self.months:
            needle = (needle.replace(day=1) + td(days=32)).replace(day=1)

        self.dt = datetime.combine(needle, time(), tzinfo=self.dt.tzinfo)
        return True

    def advance_year(self) -> None:
        if self.dt.year in self.years:
            return

        needle = self.dt.date()
        while needle.year not in self.years and needle.year < MAX_YEAR:
            needle = needle.replace(year=needle.year + 1, month=1, day=1)

        self.dt = datetime.combine(needle, time(), tzinfo=self.dt.tzinfo)

    def __iter__(self) -> "OnCalendar":
        return self

    def __next__(self) -> datetime:
        self.dt += SECOND

        while True:
            # systemd seems to generate dates up to 2200, so we do the same
            if self.dt.year >= MAX_YEAR:
                raise StopIteration

            # print(f"{self.dt.isoformat()=}")
            self.advance_year()

            if self.advance_month():
                continue

            if self.advance_day():
                continue

            if self.advance_hour():
                continue

            if self.advance_minute():
                continue

            if self.advance_second():
                continue

            if self.fixup_tz:
                result = self.dt.replace(tzinfo=self.fixup_tz, fold=0)
                if is_imaginary(result):
                    # If we hit an imaginary datetime then look for the next
                    # occurence
                    self.dt += SECOND
                    continue
                return result

            return self.dt


def parse_tz(value) -> ZoneInfo | None:
    # Optimization: there are no timezones that start with a digit or star
    if value[0] in "0123456789*":
        return None

    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return None


class OnCalendarTz(object):
    def __init__(self, expr: str, dt: datetime):
        if not dt.tzinfo:
            raise OnCalendarError("Argument 'dt' must be timezone-aware")

        self.local_tz = dt.tzinfo
        if " " in expr:
            head, maybe_tz = expr.rsplit(maxsplit=1)
            if tz := parse_tz(maybe_tz):
                expr, dt = head, dt.astimezone(tz)

        self.iterator = OnCalendar(expr, dt)

    def __next__(self) -> datetime:
        return next(self.iterator).astimezone(self.local_tz)
