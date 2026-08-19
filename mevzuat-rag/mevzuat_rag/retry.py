"""Small synchronous retry helper with exponential backoff — every external
call (LLM, DB, reranker) is supposed to have try/except + timeout + fallback;
this covers the retry part for calls that are worth retrying (transient
network/rate-limit failures), while the caller still decides the fallback
for a final failure."""
from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def call_with_retry(fn: Callable[[], T], attempts: int, backoff_base_s: float) -> T:
    last_exc: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(backoff_base_s * (2**attempt))
    assert last_exc is not None
    raise last_exc
