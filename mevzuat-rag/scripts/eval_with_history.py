"""``run_retrieval_eval.run()``'ı çalıştırır ve sonucunu ``logs/eval_history.jsonl``'a
kalıcı olarak kaydeder — "history'li" retrieval eval koşusu.

docs/IMPROVEMENT_IDEAS.md'deki "Gözlemlenebilirlik #4 — Drift/regresyon
paneli" fikrinin uygulamasıdır. ``mevzuat_rag/eval/run_retrieval_eval.py``'nin
``__main__`` bloğuna BİLEREK dokunulmadı — o dosya başka bir paralel ajanın
çalışma alanı olabilir, üzerine yazmak çakışma riski taşır. Bunun yerine bu
script ayrı bir wrapper olarak aynı işlevi ("eval çalıştır + sonucu yazdır")
sağlıyor, üstüne tek fark: sonunda ``eval_history.append_history()`` ile
sonucu kalıcı kaydediyor.

    python scripts/eval_with_history.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mevzuat_rag.eval import eval_history  # noqa: E402
from mevzuat_rag.eval import run_retrieval_eval  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    result = run_retrieval_eval.run()

    for row in result["per_case"]:
        print(row)
    print("---")
    print("summary:", result["summary"])

    eval_history.append_history(result)
    print(f"\neval geçmişe kaydedildi: {eval_history.HISTORY_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
