"""Interactive REPL: `make serve` (no QUERY) or `python -m mevzuat_rag.repl`.
Reads one query per line from stdin, prints RAGEngine.ask()'s grounded
answer + sources, until EOF or Ctrl+C. This package is deliberately a
library/CLI, not an HTTP server (see README) — this is the "serve queries
from the terminal" equivalent.
"""
from __future__ import annotations

import argparse
import getpass

from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine


def main() -> None:
    parser = argparse.ArgumentParser(
        description="mevzuat-rag REPL — stdin'den soru oku, cevap yazdır."
    )
    parser.add_argument(
        "--top-k", type=int, default=None,
        help="Kaç mevzuat parçası getirilsin (verilmezse config'teki retrieval_top_k kullanılır)",
    )
    args = parser.parse_args()

    engine = RAGEngine(RAGConfig.from_env())
    actor = f"cli:{getpass.getuser()}"
    print(f"mevzuat-rag REPL (profil: {engine.config.profile}) — çıkmak için Ctrl+C veya boş satır.\n")
    try:
        while True:
            query = input("Soru> ").strip()
            if not query:
                break
            result = engine.ask(query, top_k=args.top_k, actor=actor)
            print(f"\nCevap:\n{result['answer']}\n")
            for source in result.get("sources", []):
                print(f"  [{source['score']:.3f}] {source['citation']}")
            print()
    except (KeyboardInterrupt, EOFError):
        print("\nkapatılıyor.")


if __name__ == "__main__":
    main()
