"""Job handler registry. Handlers register a job_type → async callable(ctx) -> dict."""

from typing import Awaitable, Callable, Dict

_HANDLERS: Dict[str, Callable] = {}


def register(job_type: str, handler: Callable[..., Awaitable[Dict]]) -> None:
    _HANDLERS[job_type] = handler


def get_handler(job_type: str):
    return _HANDLERS.get(job_type)


def registered_types():
    return sorted(_HANDLERS.keys())
