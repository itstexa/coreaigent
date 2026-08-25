"""Runs the golden set against the indexed corpus and reports Recall@K / MRR / latency.

    python -m mevzuat_rag.eval.run_retrieval_eval

Goes through RAGEngine.retrieve() — i.e. the real pipeline (mevzuat_rag/
pipeline/), whatever combination of stages the engine's config has enabled
(hybrid/rerank/etc.) — not a raw embed+search shortcut, so this actually
measures what a given stage combination contributes (see README's "her
stage açık/kapalı iken ölçüm" note).

Assumes the corpus has already been indexed (see ingest_pipeline.py or
smoke_test.py). Compares against (kanun_no, madde_no) identity rather than
raw chunk IDs, since IDs are an implementation detail and structural
identity is what a human golden-set author can actually verify.

2026-08-22: golden_set.jsonl'a ``must_refuse: true`` satırları eklendi
(corpus-dışı sorular, bkz. docs/IMPROVEMENT_IDEAS.md, Gözlemlenebilirlik
#3) — bunlar için Recall/MRR anlamsız (doğru madde diye bir şey yok),
bunun yerine "retrieve() gerçekten boş döndü mü" (min_score=0.05'in
her şeyi elediği doğrulanmış davranış, bkz. NOTES.md) ayrı bir
``refuse_accuracy`` metriğiyle raporlanıyor.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.eval.retrieval_metrics import mrr, precision_at_k, recall_at_k

GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.jsonl"
K_VALUES = (1, 3, 5)


def _madde_key(kanun_no: str, madde_no) -> str:
    return f"{kanun_no}:{madde_no}"


def run(engine: RAGEngine | None = None) -> dict:
    engine = engine or RAGEngine()
    cases = [json.loads(line) for line in GOLDEN_SET_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]

    per_case = []
    latencies_ms = []
    for case in cases:
        must_refuse = bool(case.get("must_refuse", False))
        relevant = {_madde_key(e["kanun_no"], e["madde_no"]) for e in case["expected"]}

        t0 = time.perf_counter()
        hits = engine.retrieve(case["query"], top_k=max(K_VALUES))
        latency_ms = (time.perf_counter() - t0) * 1000
        latencies_ms.append(latency_ms)

        retrieved = [_madde_key(hit.chunk.metadata.kanun_no, hit.chunk.metadata.madde_no) for hit in hits]
        row = {"query": case["query"], "latency_ms": round(latency_ms, 1), "must_refuse": must_refuse}
        if must_refuse:
            # Doğru madde diye bir şey yok — burada "başarı" retrieve()'in
            # boş dönmesi (min_score eşiğinin her şeyi elemesi).
            row["refused_correctly"] = len(hits) == 0
        else:
            for k in K_VALUES:
                row[f"recall@{k}"] = round(recall_at_k(retrieved, relevant, k), 3)
                row[f"precision@{k}"] = round(precision_at_k(retrieved, relevant, k), 3)
            row["mrr"] = round(mrr(retrieved, relevant), 3)
        per_case.append(row)

    n = len(per_case)
    positive_cases = [r for r in per_case if not r["must_refuse"]]
    refuse_cases = [r for r in per_case if r["must_refuse"]]

    summary: dict[str, object] = {}
    if positive_cases:
        np_ = len(positive_cases)
        summary.update({f"recall@{k}": round(sum(r[f"recall@{k}"] for r in positive_cases) / np_, 3) for k in K_VALUES})
        summary.update({f"precision@{k}": round(sum(r[f"precision@{k}"] for r in positive_cases) / np_, 3) for k in K_VALUES})
        summary["mrr"] = round(sum(r["mrr"] for r in positive_cases) / np_, 3)
    if refuse_cases:
        summary["refuse_accuracy"] = round(sum(r["refused_correctly"] for r in refuse_cases) / len(refuse_cases), 3)
    summary["latency_ms_p50"] = round(sorted(latencies_ms)[n // 2], 1)
    summary["latency_ms_max"] = round(max(latencies_ms), 1)
    summary["n_queries"] = n
    summary["n_refuse_queries"] = len(refuse_cases)

    return {"per_case": per_case, "summary": summary}


if __name__ == "__main__":
    result = run()
    for row in result["per_case"]:
        print(row)
    print("---")
    print("summary:", result["summary"])
