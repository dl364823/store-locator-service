import re
from datetime import datetime, timezone

# Maps Python weekday() (0=Mon … 6=Sun) to the store hours column name
_DAY_TO_COLUMN: dict[int, str] = {
    0: "hours_mon",
    1: "hours_tue",
    2: "hours_wed",
    3: "hours_thu",
    4: "hours_fri",
    5: "hours_sat",
    6: "hours_sun",
}

_HOURS_RE = re.compile(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$")


def parse_hours(hours_str: str | None) -> tuple[int, int] | None:
    """Parse 'HH:MM-HH:MM' → (open_minutes, close_minutes).

    Returns None for 'closed', None input, or any invalid format so callers
    can treat None as "store is closed for this period".
    """
    if not hours_str or hours_str.strip().lower() == "closed":
        return None

    match = _HOURS_RE.match(hours_str.strip())
    if not match:
        return None

    oh, om, ch, cm = map(int, match.groups())
    open_mins = oh * 60 + om
    close_mins = ch * 60 + cm

    # close_time must be strictly after open_time (e.g. "09:00-08:00" is invalid)
    if close_mins <= open_mins:
        return None

    return open_mins, close_mins


def is_store_open(store: object, at_time: datetime | None = None) -> bool:
    """Return True if the store is open at the given UTC time (defaults to now).

    NOTE: Store hours are compared against UTC. Since the schema has no timezone
    column, UTC is used as a consistent reference. This is a known limitation —
    results may differ by a few hours for stores in non-UTC timezones.
    """
    now = at_time or datetime.now(timezone.utc).replace(tzinfo=None)
    col = _DAY_TO_COLUMN[now.weekday()]
    hours_str = getattr(store, col, None)
    parsed = parse_hours(hours_str)
    if parsed is None:
        return False
    open_mins, close_mins = parsed
    current_mins = now.hour * 60 + now.minute
    return open_mins <= current_mins < close_mins


def get_hours_dict(store: object) -> dict[str, str | None]:
    return {
        day: getattr(store, f"hours_{day}", None)
        for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    }


def validate_hours_string(value: str) -> bool:
    """Return True if value is either 'closed' or a valid 'HH:MM-HH:MM' string."""
    if value.strip().lower() == "closed":
        return True
    return parse_hours(value) is not None
