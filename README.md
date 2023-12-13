# oncalendar

[![Tests](https://github.com/cuu508/oncalendar/actions/workflows/pytest.yml/badge.svg)](https://github.com/cuu508/oncalendar/actions/workflows/pytest.yml)

A systemd [OnCalendar expression](https://www.man7.org/linux/man-pages/man7/systemd.time.7.html#CALENDAR_EVENTS)
parser and evaluator. Requires Python 3.10+.

oncalendar is written for and being used in [Healthchecks](https://github.com/healthchecks/healthchecks/)
(a scheduled task monitoring service).

This package provides three iterators:

* **oncalendar.BaseIterator(expression: str, start: datime)**: supports expressions
  without timezone (example: "Mon, 12:34"). Accepts both naive and timezone-aware
  datetimes as the start time.
* **oncalendar.TzIterator(expression: str, start: datetime)**: supports expressions
  with and without timezone. (example: "Mon, 12:34 Europe/Riga"). Requires the start
  datetime to be timezone-aware.
* **oncalendar.OnCalendar(expressions:str, start: datetime)**: supports multiple
  expressions with or without timezones, separated by newlines. Requires the start
  datetime to be timezone-aware. Example:

  ```
  2020-01-01
  12:34 Europe/Riga
  ```

## Installation

```
pip install oncalendar
```

## Usage

```python
from datetime import datetime
from oncalendar import BaseIterator

it = BaseIterator("Mon, 12:34", datetime.now())
for x in range(0, 10):
    print(next(it))
```

Produces:

```
2023-12-11 12:34:00
2023-12-18 12:34:00
2023-12-25 12:34:00
2024-01-01 12:34:00
2024-01-08 12:34:00
2024-01-15 12:34:00
2024-01-22 12:34:00
2024-01-29 12:34:00
2024-02-05 12:34:00
2024-02-12 12:34:00
```

If oncalendar receives an invalid expression, it raises `oncalendar.OnCalendarError`
exception:

```python
from datetime import datetime
from oncalendar import BaseIterator

BaseIterator("Mon, 123:456", datetime.now())
```

Produces:

```
oncalendar.OnCalendarError: Bad hour
```

If oncalendar hits year 2200 while iterating, it stops iteration by raising
`StopIteration`:

```python
from datetime import datetime
from oncalendar import BaseIterator

# 2199 is not leap year, and we stop at 2200
print(next(BaseIterator("2199-2-29", datetime.now())))
```

Produces:

```
StopIteration
```

## Known Limitations

* Does not support decimals in the second field.