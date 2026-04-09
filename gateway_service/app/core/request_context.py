from __future__ import annotations

from contextvars import ContextVar

_correlation_id_var: ContextVar[str | None] = ContextVar("gateway_correlation_id", default=None)


def set_correlation_id(correlation_id: str) -> None:
    _correlation_id_var.set(correlation_id)


def get_correlation_id() -> str | None:
    return _correlation_id_var.get()
