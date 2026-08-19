"""Runs the golden set once per stage toggle (baseline = current
config/default.yaml, then each optional stage flipped off one at a time)
and prints the Recall@K/MRR/latency delta — so it's visible which technique
is actually contributing on this corpus, not just that "everything is on".

    python -m mevzuat_rag.eval.run_ablation

Assumes the corpus is already indexed (see ingest_pipeline.py).
"""
from __future__ import annotations

from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.eval.run_retrieval_eval import run

# (label, config attribute path, value to set for the ablated run)
ABLATIONS = [
    ("hybrid kapalı (dense-only)", "hybrid", "enabled", False),
    ("rerank kapalı", "rerank", "enabled", False),
    ("multi_query kapalı", "multi_query", "enabled", False),
    ("hyde kapalı", "hyde", "enabled", False),
    ("parent_doc kapalı", "parent_doc", "enabled", False),
    ("compression kapalı", "compression", "enabled", False),
    ("router kapalı", "router", "enabled", False),
    ("crag kapalı", "crag", "enabled", False),
]


def _summary_line(label: str, summary: dict) -> str:
    return (
        f"{label:32s} recall@1={summary['recall@1']:.3f}  recall@3={summary['recall@3']:.3f}  "
        f"recall@5={summary['recall@5']:.3f}  mrr={summary['mrr']:.3f}  "
        f"p50={summary['latency_ms_p50']:.0f}ms"
    )


def main() -> None:
    baseline_config = RAGConfig.from_env()
    baseline = run(RAGEngine(baseline_config))["summary"]
    print(_summary_line("BASELINE (default.yaml)", baseline))
    print("-" * 100)

    for label, section, attr, value in ABLATIONS:
        config = RAGConfig.from_env()
        getattr(config, section).__setattr__(attr, value)
        result = run(RAGEngine(config))["summary"]
        print(_summary_line(label, result))


if __name__ == "__main__":
    main()
