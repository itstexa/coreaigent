"""CLI: ask a question, get a DeepSeek-generated answer grounded in retrieved mevzuat.

    python -m mevzuat_rag.ask "Dilekçede hangi bilgiler zorunludur?"

Requires DEEPSEEK_API_KEY in the environment. Assumes the corpus has
already been indexed (see ingest_pipeline.py).
"""
from __future__ import annotations

import argparse
import getpass

from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine


def main() -> None:
    parser = argparse.ArgumentParser(
        description="mevzuat-rag: bir soru sor, DeepSeek/Jamba-üretimli, mevzuata dayalı bir cevap al."
    )
    parser.add_argument("query", nargs="+", help="Soru metni")
    parser.add_argument(
        "--top-k", type=int, default=None,
        help="Kaç mevzuat parçası getirilsin (verilmezse config'teki retrieval_top_k kullanılır)",
    )
    args = parser.parse_args()

    query = " ".join(args.query)
    engine = RAGEngine(RAGConfig.from_env())
    result = engine.ask(query, top_k=args.top_k, actor=f"cli:{getpass.getuser()}")

    print(f"Soru: {query}\n")
    print(f"Cevap:\n{result['answer']}\n")
    print("Kaynaklar:")
    for source in result["sources"]:
        print(f"  [{source['score']:.3f}] {source['citation']}")

    if result.get("crag_status") == "EVALUATOR_FAILED_OPEN":
        print("⚠️  crag_status=EVALUATOR_FAILED_OPEN — ilgililik kontrolü teknik hata nedeniyle atlandı.\n")

    if "post_hoc_verdict" in result:
        is_valid = result["post_hoc_verdict"] not in ("REJECTED_BY_CRITIC", "STRUCTURAL_FAIL")
        print(f"\nHakem Ajan (Critic Agent) kararı: {{\"is_valid\": {str(is_valid).lower()}, \"reason\": {result.get('post_hoc_reason', '')!r}}}")
        print(f"  (post_hoc_verdict={result['post_hoc_verdict']})")


if __name__ == "__main__":
    main()
