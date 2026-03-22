from __future__ import annotations

from typing import Any, Callable, Dict


Notifier = Callable[[str, Dict[str, Any]], None]

_notifier: Notifier | None = None


def set_notifier(notifier: Notifier | None) -> None:
    global _notifier
    _notifier = notifier


def emit_event(method: str, params: Dict[str, Any]) -> None:
    if _notifier is None:
        return
    _notifier(method, params)
