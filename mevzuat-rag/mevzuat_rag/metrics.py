"""Shared ingest/query timing helpers.

The package already has a pipeline TraceEntry format. This module provides
the same record shape for ingest and any manual instrumentation so every
timing ends up in one schema instead of two.
"""
from __future__ import annotations

import functools
import threading
import time
from typing import Any, Callable

_records: list[dict[str, Any]] = []
_lock = threading.Lock()


class _TimerContext:
    def __init__(self, stage: str, metadata: dict[str, Any] | None = None):
        self.stage = stage
        self.metadata = dict(metadata or {})
        self.input_count: int | None = None
        self.output_count: int | None = None
        self.duration_ms: float | None = None
        self._start: float | None = None

    def __enter__(self) -> "_TimerContext":
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        end = time.perf_counter()
        self.duration_ms = round((end - (self._start or end)) * 1000.0, 2)

        status = "ok"
        if exc_type is not None:
            status = "error"
            self.metadata["error"] = str(exc)

        record = {
            "stage": self.stage,
            "duration_ms": self.duration_ms,
            "input_count": self.input_count,
            "output_count": self.output_count,
            "metadata": self.metadata,
            "status": status,
        }

        with _lock:
            _records.append(record)

        return False


def timer(stage_name: str, **metadata: Any) -> _TimerContext:
    input_count = metadata.pop("input_count", None)
    output_count = metadata.pop("output_count", None)

    if "metadata" in metadata and isinstance(metadata.get("metadata"), dict):
        nested = dict(metadata.pop("metadata"))
        base = {**nested, **metadata}
    else:
        base = dict(metadata)

    ctx = _TimerContext(stage_name, base)
    if input_count is not None:
        ctx.input_count = input_count
    if output_count is not None:
        ctx.output_count = output_count

    return ctx


def timed(stage_name: str):
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with _TimerContext(stage_name) as ctx:
                if args:
                    first = args[0]
                    if isinstance(first, (list, tuple, set)):
                        ctx.input_count = len(first)

                result = func(*args, **kwargs)

                if isinstance(result, (list, tuple, set)):
                    ctx.output_count = len(result)
                elif isinstance(result, int):
                    ctx.output_count = result

                return result

        return wrapper

    return decorator


def get_records() -> list[dict[str, Any]]:
    with _lock:
        return list(_records)


def clear_records() -> None:
    with _lock:
        _records.clear()
