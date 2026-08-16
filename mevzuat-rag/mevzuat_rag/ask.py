"""CLI: ask a question, get a DeepSeek-generated answer grounded in retrieved mevzuat.

    python -m mevzuat_rag.ask "Dilekçede hangi bilgiler zorunludur?"

Requires DEEPSEEK_API_KEY in the environment. Assumes the corpus has
already been indexed (see ingest_pipeline.py).
"""
from __future__ import annotations

import sys

from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine


def main() -> None:
    if len(sys.argv) < 2:
        print('Kullanım: python -m mevzuat_rag.ask "soru"', file=sys.stderr)
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    engine = RAGEngine(RAGConfig.from_env())
    result = engine.ask(query)

    print(f"Soru: {query}\n")
    print(f"Cevap:\n{result['answer']}\n")
    print("Kaynaklar:")
    for source in result["sources"]:
        print(f"  [{source['score']:.3f}] {source['citation']}")


if __name__ == "__main__":
    main()
