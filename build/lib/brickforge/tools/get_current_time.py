"""Simulated current time for turnaround scenario. Returns next time in queue on each call."""

import threading
from langchain_core.tools import tool

_TIME_QUEUE = [
    "2026-02-25T10:00:00.000",
    "2026-02-25T10:05:00.000",
    "2026-02-25T10:10:00.000",
    "2026-02-25T10:15:00.000",
    "2026-02-25T10:20:00.000",
    "2026-02-25T10:25:00.000",
    "2026-02-25T10:30:00.000",
]
_index = 0
_lock = threading.Lock()


def reset_index() -> None:
    """Reset simulated time back to the first entry in the queue."""
    global _index
    with _lock:
        _index = 0


def get_next_time(advance: bool = True, backward: bool = False) -> str:
    """Return the current simulated time. If backward is True, step queue back (with wrap) then return. If advance is True (and not backward), step forward then return. Else peek."""
    global _index
    with _lock:
        if backward:
            _index = (_index - 1) % len(_TIME_QUEUE)
        elif advance:
            _index += 1
        t = _TIME_QUEUE[_index % len(_TIME_QUEUE)]
    return t


@tool
def get_current_time(advance: bool = False) -> str:
    """Get the simulated current time for the turnaround scenario. Pass advance=True when you need the time for this turn (e.g. before querying Genie for checklist); then use that time in your Genie query. Use advance=False only to peek (default)."""
    return f"Current time: {get_next_time(advance)}"
