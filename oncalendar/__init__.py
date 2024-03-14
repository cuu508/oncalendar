from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time
from datetime import timedelta as td
from datetime import timezone
from enum import IntEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc

# systemd seems to stop iteration when it reaches year 2200. We do the same.
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
# timedelta initialization is not cheap so we prepare a few constants
# that we will need often:
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
        # Make sure the value contains digits and nothing else
        # (for example, we reject integer literals with underscores)
        for ch in value:
            if ch not in "0123456789":
                raise OnCalendarError(self.msg())

        return int(value)

    def int(self, s: str) -> int:
        """Convert the supplied sting to an integer.

        This function handles a few special cases:
        * It converts weekdays "Mon", "Tue", ..., "Sun" to 0, 1, ..., 6
        * It converts years 70 .. 99 to 1970 - 1999
        * It converts years 0 .. 69 to 2000 - 2069

        It also checks if the resulting integer is within the range
        of valid values for the given field, and raises `OnCalendarError`
        if it is not.
        """
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

    def parse(self, s: str, reverse: bool = False) -> set[__builtins__.int]:
        """Parse a single component of an expression into a set of integers.

        To handle lists, intervals, and intervals with a step, this function
        recursively calls itself.
        """
        if self == Field.DAY and s.startswith("~"):
            # Chop leading "~" and set the reverse flag
            return self.parse(s[1:], reverse=True)

        if self != Field.DOW and s == "*":
            return set(RANGES[self])

        if "*" in s:
            # systemd's OnCalendar syntax does not allow '*' to appear in
            # comma-delimited lists, in intervals, or in intervals with step.
            raise OnCalendarError(self.msg())

        if self == Field.DOW and s.endswith(","):
            # systemd allows both "Mon 1-1" and "Mon, 1-1". forms, and normalizes
            # to the form without trailing comma. We do the same.
            return self.parse(s[:-1])

        if self == Field.DOW and "-" in s:
            # For the weekday component, systemd allows both the "Mon..Fri" and
            # the "Mon-Fri" forms. It normalizes "-" to ".." and we do the same.
            return self.parse(s.replace("-", ".."))

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
    """Return True if dt gets skipped over during DST transition."""
    return dt != dt.astimezone(UTC).astimezone(dt.tzinfo)


class BaseIterator(object):
    """OnCalendar expression parser and iterator.

    This iterator supports most syntax features supported by systemd. It however
    does *not* support:

    * Timezone specified within the expression (use `TzIterator` instead).
    * Seconds fields with decimal values.

    This iterator works with both naive and timezone-aware datetimes. In case
    of timezone-aware datetimes, it mimics systemd behaviour during DST transitions:

    * It skips over datetimes that fall in the skipped hour during the spring DST
      transition.
    * It repeats the datetimes that fall in the repeated hour during the fall DST
      transition. It returns a datetime with the pre-transition timezone,
      then the same datetime but with the post-transition timezone.
    """

    def __init__(self, expression: str, start: datetime):
        """Initialize the iterator with an OnCalendar expression and the start time.

        `expression` should contain a single OnCalendar expression without a timezone,
        for example: `Mon 01-01 12:00:00`.

        `start` is the datetime to start iteration from. The first result
        returned by the iterator will be greater than `start`. The supplied
        datetime can be either naive or timezone-aware. If `start` is naive,
        the iterator will also return naive datetimes. If `start` is timezone-aware,
        the iterator will return timezone-aware datetimes using the same timezone
        as `start`.
        """
        self.dt = start.replace(microsecond=0)

        if expression.lower() in SPECIALS:
            expression = SPECIALS[expression.lower()]

        parts = expression.replace("~", "-~").split()
        if not parts:
            raise OnCalendarError("Wrong number of fields")

        if ":" in parts[-1]:
            time_parts = parts.pop().split(":")
            if len(time_parts) not in (2, 3):
                raise OnCalendarError("Bad time")
            if len(time_parts) == 2:
                # If seconds is missing, use default
                time_parts.append("0")
            self.hours = Field.HOUR.parse(time_parts[0])
            self.minutes = Field.MINUTE.parse(time_parts[1])
            self.seconds = Field.SECOND.parse(time_parts[2])
        else:
            # Default: 00:00:00
            self.hours, self.minutes, self.seconds = {0}, {0}, {0}

        if parts and "-" in parts[-1] and parts[-1][0] in "0123456789*":
            date_parts = parts.pop().split("-")
            if len(date_parts) not in (2, 3):
                raise OnCalendarError("Bad date")
            if len(date_parts) == 2:
                # If year is missing, use default
                date_parts.insert(0, "*")
            self.years = Field.YEAR.parse(date_parts[0])
            self.months = Field.MONTH.parse(date_parts[1])
            self.days = Field.DAY.parse(date_parts[2])
        else:
            # Default: *-*-*
            self.years = set(RANGES[Field.YEAR])
            self.months = set(RANGES[Field.MONTH])
            self.days = set(RANGES[Field.DAY])

        if parts:
            self.weekdays = Field.DOW.parse(parts.pop(0))
        else:
            # Default: Mon..Sun
            self.weekdays = set(RANGES[Field.DOW])

        # There should be no parts left over
        if parts:
            raise OnCalendarError("Wrong number of fields")

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

        self.dt = self.dt.replace(minute=0, second=0)
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
        """Roll forward the year component until it satisfies the constraints.

        Return False if the year meets contraints without modification.
        Return True if self.dt was rolled forward.

        """

        if self.dt.year in self.years:
            return

        needle = self.dt.date()
        while needle.year not in self.years and needle.year < MAX_YEAR:
            needle = needle.replace(year=needle.year + 1, month=1, day=1)

        self.dt = datetime.combine(needle, time(), tzinfo=self.dt.tzinfo)

    def __iter__(self) -> "BaseIterator":
        return self

    def __next__(self) -> datetime:
        self.dt += SECOND

        while True:
            # print(f"{self.dt.isoformat()=}")
            self.advance_year()

            # systemd seems to generate dates up to 2200, so we do the same
            if self.dt.year >= MAX_YEAR:
                raise StopIteration

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


def parse_tz(value: str) -> ZoneInfo | None:
    """Return ZoneInfo object or None if value fails to parse."""
    # Optimization: there are no timezones that start with a digit or star
    if value[0] in "0123456789*":
        return None

    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return None


class TzIterator(object):
    """OnCalendar expression parser and iterator (with timezone support).

    This iterator wraps `BaseIterator` and adds support for timezones within
    the expression. This iterator requires the starting datetime to be
    timezone-aware.
    """

    def __init__(self, expression: str, start: datetime):
        """Initialize the iterator with an OnCalendar expression and the start time.

        `expression` should contain a single OnCalendar expression with or without a
        timezone, for example: `Mon 01-01 12:00:00 Europe/Riga`.

        `start` is the timezone-aware datetime to start iteration from. The iterator
        will return datetimes using the same timezone as `start`.
        """
        if not start.tzinfo:
            raise OnCalendarError("Argument 'dt' must be timezone-aware")

        self.local_tz = start.tzinfo
        expression = expression.strip()
        if " " in expression:
            head, maybe_tz = expression.rsplit(maxsplit=1)
            if tz := parse_tz(maybe_tz):
                expression, start = head, start.astimezone(tz)

        self.iterator = BaseIterator(expression, start)

    def __iter__(self) -> "TzIterator":
        return self

    def __next__(self) -> datetime:
        return next(self.iterator).astimezone(self.local_tz)


class OnCalendar(object):
    """OnCalendar expression parser and iterator (with multiple expression support).

    This iterator wraps `TzIterator` and adds support for iterating over multiple
    expressions (separated by newlines) at once.
    """

    def __init__(self, expressions: str, start: datetime):
        """Initialize the iterator with OnCalendar expression(s) and the start time.

        `expressions` should contain one or more OnCalendar expressions with or without
        a timezone, separated with newlines. Example:
        `00:00 Europe/Riga\n00:00 UTC`.

        `start` is the timezone-aware datetime to start iteration from. The iterator
        will return datetimes using the same timezone as `start`.
        """
        if not start.tzinfo:
            raise OnCalendarError("Argument 'dt' must be timezone-aware")

        self.dt = start
        self.iterators = {}
        for expr in expressions.strip().split("\n"):
            self.iterators[TzIterator(expr, start.replace())] = start

    def __iter__(self) -> "OnCalendar":
        return self

    def __next__(self) -> datetime:
        for it in list(self.iterators.keys()):
            if self.iterators[it] > self.dt:
                continue

            try:
                self.iterators[it] = next(it)
            except StopIteration:
                del self.iterators[it]

        if not self.iterators:
            raise StopIteration

        self.dt = min(self.iterators.values())
        return self.dt
