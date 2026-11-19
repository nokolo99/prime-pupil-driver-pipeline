"""Simulated clock for the demo.

The whole system reads time through models.now(), which adds this offset. The demo panel's
"skip ahead" buttons increase the offset, so timers and reminders fire as if days passed.
In production the offset is always zero.
"""

from datetime import timedelta

_offset = timedelta(0)


def offset() -> timedelta:
    return _offset


def set_offset(days: float) -> None:
    global _offset
    _offset = timedelta(days=days)


def offset_days() -> float:
    return _offset.total_seconds() / 86400
