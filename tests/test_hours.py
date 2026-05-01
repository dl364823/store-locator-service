"""Unit tests for hours parsing and open_now logic."""
from datetime import datetime

import pytest

from app.services.hours import parse_hours, is_store_open, validate_hours_string


# ---------- parse_hours ----------

def test_parse_valid_hours():
    result = parse_hours("08:00-22:00")
    assert result == (8 * 60, 22 * 60)


def test_parse_closed_string():
    assert parse_hours("closed") is None
    assert parse_hours("CLOSED") is None


def test_parse_none():
    assert parse_hours(None) is None


def test_parse_empty_string():
    assert parse_hours("") is None


def test_parse_invalid_format():
    assert parse_hours("8am-10pm") is None
    assert parse_hours("08:00") is None
    assert parse_hours("not-a-time") is None


def test_parse_close_before_open_is_invalid():
    # 09:00-08:00 is logically invalid
    assert parse_hours("09:00-08:00") is None


def test_parse_midnight_edge():
    result = parse_hours("00:00-23:59")
    assert result == (0, 23 * 60 + 59)


def test_parse_same_open_close_is_invalid():
    assert parse_hours("08:00-08:00") is None


# ---------- validate_hours_string ----------

def test_validate_accepts_valid():
    assert validate_hours_string("08:00-22:00") is True
    assert validate_hours_string("closed") is True


def test_validate_rejects_invalid():
    assert validate_hours_string("bad") is False
    assert validate_hours_string("09:00-08:00") is False


# ---------- is_store_open ----------

class _FakeStore:
    """Minimal stand-in for the Store ORM model."""
    def __init__(self, **hours):
        for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
            setattr(self, f"hours_{day}", hours.get(day))


def _monday_at(hour: int, minute: int = 0) -> datetime:
    """Return a Monday datetime at the given hour:minute."""
    # 2026-01-05 is a Monday
    return datetime(2026, 1, 5, hour, minute)


def test_open_during_hours():
    store = _FakeStore(mon="08:00-22:00")
    assert is_store_open(store, at_time=_monday_at(12)) is True


def test_closed_before_opening():
    store = _FakeStore(mon="08:00-22:00")
    assert is_store_open(store, at_time=_monday_at(7)) is False


def test_closed_after_closing():
    store = _FakeStore(mon="08:00-22:00")
    assert is_store_open(store, at_time=_monday_at(22)) is False  # 22:00 is NOT open (< close)


def test_open_exactly_at_opening():
    store = _FakeStore(mon="08:00-22:00")
    assert is_store_open(store, at_time=_monday_at(8)) is True


def test_closed_on_day_marked_closed():
    store = _FakeStore(mon="closed")
    assert is_store_open(store, at_time=_monday_at(12)) is False


def test_closed_when_hours_column_is_none():
    store = _FakeStore()  # no hours set
    assert is_store_open(store, at_time=_monday_at(12)) is False


def test_different_day_of_week():
    # Friday = weekday 4
    store = _FakeStore(fri="09:00-21:00")
    friday = datetime(2026, 1, 9, 15)  # 2026-01-09 is a Friday
    assert is_store_open(store, at_time=friday) is True


def test_sunday_hours():
    store = _FakeStore(sun="10:00-20:00")
    sunday = datetime(2026, 1, 11, 18)  # 2026-01-11 is a Sunday
    assert is_store_open(store, at_time=sunday) is True
