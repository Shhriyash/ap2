from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.core.request_context import get_correlation_id

_logger = logging.getLogger("agent_audit")


def _configure() -> None:
    if _logger.handlers:
        return
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(logs_dir / "agent.log", encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)


def log_event(event_type: str, payload: dict[str, Any]) -> None:
    _configure()
    with_correlation = dict(payload)
    correlation_id = get_correlation_id()
    if correlation_id:
        with_correlation["correlation_id"] = correlation_id
    _logger.info("%s %s", event_type, json.dumps(with_correlation, ensure_ascii=True))
