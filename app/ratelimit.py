"""Tiny in-memory sliding-window limiter for failed logins.

It is per-process: fine for a single Render instance, not a substitute for a shared
rate limiter (Redis, API gateway) if the service is scaled to several instances.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

MAX_FAILURES = 8
WINDOW_SECONDS = 300

_lock = threading.Lock()
_failures: dict[str, deque[float]] = defaultdict(deque)


def _prune(key: str, now: float) -> deque[float]:
    events = _failures[key]
    while events and now - events[0] > WINDOW_SECONDS:
        events.popleft()
    if not events:
        _failures.pop(key, None)
        return deque()
    return events


def is_blocked(key: str) -> bool:
    with _lock:
        return len(_prune(key, time.monotonic())) >= MAX_FAILURES


def record_failure(key: str) -> None:
    with _lock:
        now = time.monotonic()
        _prune(key, now)
        _failures[key].append(now)
        if len(_failures) > 10_000:  # bound memory under attack
            for stale in list(_failures)[:1000]:
                _failures.pop(stale, None)


def reset(key: str) -> None:
    with _lock:
        _failures.pop(key, None)


def clear_all() -> None:
    with _lock:
        _failures.clear()
