"""[4] Parent Document Retrieval — the small chunks that won [2]/[3] are
grouped by their parent madde and each parent's FULL article text (all its
fıkra/bent children, reconstructed live from the store — see
``store.get_chunks_by_madde``, never a separately stored/stale copy) is what
actually goes to [7] Generate. A parent that multiple winning chunks belong
to is expanded once, keeping the highest child score. Total expanded
context is capped at ``context_window_tokens * token_budget_fraction``; if
it doesn't fit, the lowest-scored parents are dropped first.
"""
from __future__ import annotations

from mevzuat_rag.models import ChunkMetadata, LegislationChunk
from mevzuat_rag.pipeline.candidate import Candidate
from mevzuat_rag.pipeline.context import PipelineContext
from mevzuat_rag.token_estimate import estimate_tokens


def _parent_key(candidate: Candidate) -> tuple[str, int] | None:
    metadata = candidate.chunk.metadata
    if metadata.madde_no is None:
        return None
    return (metadata.kanun_no, metadata.madde_no)


def _build_parent_text(children: list[LegislationChunk]) -> str:
    return "\n".join(child.text for child in children)


class ParentDocStage:
    name = "parent_doc"

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def run(self, ctx: PipelineContext) -> PipelineContext:
        config = ctx.resolved_config.parent_doc
        store = ctx.engine.store

        best_score_by_parent: dict[tuple[str, int], float] = {}
        order: list[tuple[str, int]] = []
        passthrough: list[Candidate] = []

        for candidate in ctx.candidates:
            key = _parent_key(candidate)
            if key is None:
                passthrough.append(candidate)
                continue
            if key not in best_score_by_parent:
                order.append(key)
            best_score_by_parent[key] = max(best_score_by_parent.get(key, float("-inf")), candidate.score)

        expanded: list[Candidate] = []
        for kanun_no, madde_no in order:
            siblings = store.get_chunks_by_madde(kanun_no, madde_no)
            if not siblings:
                continue
            parent_text = _build_parent_text(siblings)
            template = siblings[0]
            parent_metadata = ChunkMetadata(
                kanun_no=template.metadata.kanun_no,
                kanun_adi=template.metadata.kanun_adi,
                madde_no=madde_no,
                fikra_no=None,
                bent=None,
                kaynak_url=template.metadata.kaynak_url,
                source_hash=template.metadata.source_hash,
                durum=template.metadata.durum,
                mevzuat_turu=template.metadata.mevzuat_turu,
                contains_table=template.metadata.contains_table,
            )
            parent_chunk = LegislationChunk(
                id=f"parent:{kanun_no}:{madde_no}",
                text=parent_text,
                metadata=parent_metadata,
                citation=f"{kanun_no} sayılı {template.metadata.kanun_adi}, Madde {madde_no} (tam metin)",
            )
            score = best_score_by_parent[(kanun_no, madde_no)]
            candidate = Candidate(
                id=parent_chunk.id, text=parent_text, score=score, source="parent_expanded",
                parent_id=f"{kanun_no}:{madde_no}", metadata={"child_count": len(siblings)}, chunk=parent_chunk,
            )
            expanded.append(candidate)

        expanded.sort(key=lambda c: c.score, reverse=True)

        budget = int(config.context_window_tokens * config.token_budget_fraction)
        kept: list[Candidate] = []
        used_tokens = 0
        for candidate in expanded:
            cost = estimate_tokens(candidate.text)
            if kept and used_tokens + cost > budget:
                continue
            kept.append(candidate)
            used_tokens += cost

        ctx.candidates = passthrough + kept
        return ctx
