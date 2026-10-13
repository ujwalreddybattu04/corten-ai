"""Calendar context local to Pharma; no dependency on shared agent prompts."""
import re
from datetime import date, datetime, timedelta, timezone


def date_context(today: date | None = None) -> str:
    """Today's date with its weekday and the next seven days, written out. Models are unreliable at calendar
    arithmetic: given only a date, "this Friday" was written as today's date. With the days listed, it is a lookup."""
    today = today or datetime.now(timezone.utc).date()
    upcoming = ", ".join(f"{day:%A} {day.day} {day:%B}" for day in (today + timedelta(days=n) for n in range(1, 8)))
    return f"{today:%A}, {today.day} {today:%B %Y} (the next seven days: {upcoming})"


_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_DAY_OFFSETS = {"day before yesterday": -2, "yesterday": -1, "today": 0, "tonight": 0, "tomorrow": 1,
                "day after tomorrow": 2}


def _day(value: date) -> str:
    return f"{value:%A} {value.day} {value:%B %Y}"


def resolve_relative_dates(text: str, today: date | None = None) -> str:
    """Exact dates for 'this Friday', 'tomorrow', 'next Monday', 'next month' and similar phrases in a question, as
    a note for the model. Even with the days listed, a small model wrote 'this Friday, 20 October' on a Tuesday the
    13th; the dates are worked out here instead. Returns "" when the question has no such phrase."""
    today = today or datetime.now(timezone.utc).date()
    lower = " ".join((text or "").lower().split())
    notes = []
    for phrase, offset in _DAY_OFFSETS.items():
        if re.search(rf"\b{phrase}\b", lower) and not (phrase in ("yesterday", "tomorrow") and f"day {'before' if phrase == 'yesterday' else 'after'} {phrase}" in lower):
            notes.append(f"'{phrase}' is {_day(today + timedelta(days=offset))}")
    for index, name in enumerate(_WEEKDAYS):
        for match in re.finditer(rf"\b(?:(this|next|coming|last|on)\s+)?{name}\b", lower):
            qualifier, ahead = match.group(1), (index - today.weekday()) % 7
            coming = today + timedelta(days=ahead or (7 if qualifier in ("coming", "next") else 0))
            label = f"{qualifier + ' ' if qualifier and qualifier != 'on' else ''}{name.title()}"
            if qualifier == "last":
                notes.append(f"'last {name.title()}' is {_day(today - timedelta(days=(today.weekday() - index) % 7 or 7))}")
            elif qualifier == "next":
                notes.append(f"'next {name.title()}' is ambiguous: the coming {name.title()} is {_day(coming)}, and "
                             f"{name.title()} of next week is {_day(today + timedelta(days=7 - today.weekday() + index))}; "
                             "use the one the user means and name the date")
            else:
                notes.append(f"'{label}' is {_day(coming)}")
    week_start = today - timedelta(days=today.weekday())
    month_first = today.replace(day=1)
    periods = {
        "this week": f"the week of Monday {week_start.day} {week_start:%B %Y}",
        "next week": f"the week of Monday {(week_start + timedelta(days=7)).day} {(week_start + timedelta(days=7)):%B %Y}",
        "last week": f"the week of Monday {(week_start - timedelta(days=7)).day} {(week_start - timedelta(days=7)):%B %Y}",
        "this month": f"{today:%B %Y}",
        "next month": f"{(month_first + timedelta(days=32)).replace(day=1):%B %Y}",
        "last month": f"{(month_first - timedelta(days=1)):%B %Y}",
        "this year": str(today.year), "next year": str(today.year + 1), "last year": str(today.year - 1),
    }
    notes += [f"'{phrase}' is {value}" for phrase, value in periods.items() if re.search(rf"\b{phrase}\b", lower)]
    notes = list(dict.fromkeys(notes))
    if not notes:
        return ""
    return f"\n\n(Dates for reference, from today {_day(today)}: " + "; ".join(notes) + ".)"

