"""Runs a list of Stages in order, skipping disabled ones and recording a
TraceEntry (input/output candidate count + duration) for every stage that
actually ran. A stage that sets ``ctx.stopped = True`` (e.g. the Self-RAG
router deciding retrieval isn't needed) short-circuits the remaining stages.
"""
from __future__ import annotations

import time

from mevzuat_rag.pipeline.context import PipelineContext, TraceEntry
from mevzuat_rag.pipeline.stage import Stage


class Pipeline:
    def __init__(self, stages: list[Stage]):
        self.stages = stages

    def run(self, ctx: PipelineContext) -> PipelineContext:
        for stage in self.stages:
            if not stage.enabled:
                continue
            if ctx.stopped:
                break

            input_count = len(ctx.candidates)
            t0 = time.perf_counter()
            ctx = stage.run(ctx)
            duration_ms = (time.perf_counter() - t0) * 1000

            ctx.trace.append(
                TraceEntry(
                    stage=stage.name,
                    input_count=input_count,
                    output_count=len(ctx.candidates),
                    duration_ms=round(duration_ms, 2),
                )
            )
        return ctx
