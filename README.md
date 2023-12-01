# oncalendar

A systemd OnCalendar expression parser and evaluator.

Pre-alpha, work in progress.

## Usage

```python
from datetime import datetime
from oncalendar import OnCalendar

it = OnCalendar("Mon, 12:34", datetime.now())
for x in range(0, 10):
    print(next(it))
```