from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Deque, Dict, List, Optional

_MAX_EVENTS = 300
_lock = Lock()
_events: Deque[Dict[str, Any]] = deque(maxlen=_MAX_EVENTS)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def report_event(component: str, level: str, message: str, context: Optional[Dict[str, Any]] = None):
    event = {
        "timestamp": _utc_now_iso(),
        "component": component,
        "level": level,
        "message": message,
        "context": context or {},
    }
    with _lock:
        _events.append(event)


def report_error(component: str, message: str, context: Optional[Dict[str, Any]] = None):
    report_event(component=component, level="error", message=message, context=context)


def get_recent_events(component: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(limit, _MAX_EVENTS))
    with _lock:
        events = list(_events)

    if component:
        events = [event for event in events if event.get("component") == component]

    return list(reversed(events[-safe_limit:]))
