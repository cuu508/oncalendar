# oncalendar

A systemd OnCalendar expression parser and evaluator. Requires Python 3.10+.

Alpha, work in progress.

This package provides two classes:

* `oncalendar.BaseIterator`: supports expressions without timezone
  (example: "Mon, 12:34"). Accepts both naive and timezone-aware datetimes
  as the start time.
* `oncalendar.TzIterator`: supports expressions with and without timezone.
  (example: "Mon, 12:34 Europe/Riga"). Requires the start datetime to be timezone-aware.


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