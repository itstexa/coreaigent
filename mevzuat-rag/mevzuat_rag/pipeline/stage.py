"""The Stage protocol every pipeline stage implements. See runner.py for how
stages are invoked and traced."""
from __future__ import annotations

from typing import Protocol

from mevzuat_rag.pipeline.context import PipelineContext


class Stage(Protocol):
    name: str
    enabled: bool

    def run(self, ctx: PipelineContext) -> PipelineContext: ...
