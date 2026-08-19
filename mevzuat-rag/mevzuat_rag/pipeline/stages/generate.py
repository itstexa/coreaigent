"""[7] Generate — grounded, cited DeepSeek answer over ctx.candidates.
Reproduces exactly the pre-pipeline RAGEngine.ask() behavior (same
generation.generate_answer call, same "sources" shape). GenerationError
propagates uncaught, same as before — callers that want it handled catch it
themselves (see ask.py)."""
from __future__ import annotations

from mevzuat_rag import generation
from mevzuat_rag.pipeline.context import PipelineContext


class GenerateStage:
    name = "generate"

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def run(self, ctx: PipelineContext) -> PipelineContext:
        hits = [candidate.to_result() for candidate in ctx.candidates]
        result = generation.generate_answer(ctx.original_query, hits)
        result["sources"] = [
            {"citation": hit.chunk.citation, "score": round(float(hit.score), 3), "text": hit.chunk.text}
            for hit in hits
        ]
        ctx.answer = result
        return ctx
