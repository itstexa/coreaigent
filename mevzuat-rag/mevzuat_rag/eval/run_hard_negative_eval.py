"""Hard-negative retrieval eval — measures the reranker's actual DISCRIMINATION
power, not just "was the right article somewhere in the results".

This is the implementation of docs/IMPROVEMENT_IDEAS.md's Retrieval #4 —
"Hard-negative eval seti": golden_set.jsonl (see run_retrieval_eval.py) only
has positive examples, so Recall@K/MRR can be 1.0 even if the reranker barely
separates the correct madde from a superficially similar, wrong one — Recall/
MRR only checks whether the correct chunk appears in the top-K at all, never
whether it clearly outranks a plausible wrong answer sitting right next to
it. hard_negatives.jsonl instead pairs each query with one specific, real
wrong madde from the same tiny corpus (sample_data/legislation/*.md) chosen
because it shares vocabulary/theme with the correct one (see each row's
"reason") — the kind of near-miss a human could actually confuse, not a
random unrelated article.

    python -m mevzuat_rag.eval.run_hard_negative_eval

Retrieval-only — no DeepSeek/LLM key needed. Router/Multi-Query/HyDE/CRAG
(the LLM-backed pipeline stages) are disabled for the default engine this
script builds, so the score comparison is attributable to Hybrid Retrieve +
Rerank alone, not confounded by generated query variants or router fallback
behavior. Rerank's production top_n=5/min_score=0.05 cutoffs are also widened
here (see _default_config()) so BOTH the correct and the hard-negative
candidate are guaranteed to still be present in retrieve()'s returned list —
production tunes those cutoffs for precision, but applying them here would
silently drop whichever candidate loses, hiding the exact score gap we want
to measure. If a candidate is still missing from the returned list for some
other reason (e.g. it never enters Hybrid Retrieve's candidate pool at all),
its score is treated as 0.0 rather than crashing.

Does NOT touch golden_set.jsonl or run_retrieval_eval.py — fully separate
eval, separate file, separate metric.
"""
from __future__ import annotations

import json
from pathlib import Path

from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine

HARD_NEGATIVES_PATH = Path(__file__).parent / "hard_negatives.jsonl"


def _madde_key(kanun_no: str, madde_no) -> str:
    return f"{kanun_no}:{madde_no}"


def _default_config() -> RAGConfig:
    """RAGConfig tuned for this eval: no LLM-backed stages, no rerank cutoffs
    that could hide the score of whichever candidate loses."""
    config = RAGConfig.from_env()
    config.router.enabled = False
    config.multi_query.enabled = False
    config.hyde.enabled = False
    config.crag.enabled = False
    config.rerank.top_n = 50
    config.rerank.min_score = float("-inf")
    return config


def run(engine: RAGEngine | None = None) -> dict:
    engine = engine or RAGEngine(_default_config())
    cases = [json.loads(line) for line in HARD_NEGATIVES_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]

    per_case = []
    for case in cases:
        correct_key = _madde_key(case["correct"]["kanun_no"], case["correct"]["madde_no"])
        wrong_key = _madde_key(case["hard_negative"]["kanun_no"], case["hard_negative"]["madde_no"])

        hits = engine.retrieve(case["query"], top_k=50)
        scores = {_madde_key(hit.chunk.metadata.kanun_no, hit.chunk.metadata.madde_no): float(hit.score) for hit in hits}

        correct_score = scores.get(correct_key, 0.0)
        wrong_score = scores.get(wrong_key, 0.0)
        margin = correct_score - wrong_score

        per_case.append({
            "query": case["query"],
            "correct": correct_key,
            "hard_negative": wrong_key,
            "correct_score": round(correct_score, 4),
            "hard_negative_score": round(wrong_score, 4),
            "margin": round(margin, 4),
            "discriminated": margin > 0,
            "reason": case.get("reason", ""),
        })

    n = len(per_case)
    summary = {
        "discrimination_accuracy": round(sum(1 for r in per_case if r["discriminated"]) / n, 3) if n else 0.0,
        "avg_margin": round(sum(r["margin"] for r in per_case) / n, 4) if n else 0.0,
        "n_pairs": n,
    }

    return {"per_case": per_case, "summary": summary}


if __name__ == "__main__":
    result = run()
    for row in result["per_case"]:
        print(row)
    print("---")
    print("summary:", result["summary"])
