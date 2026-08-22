"""Retrieval eval geçmişinin (``logs/eval_history.jsonl``) konsol tablosu.

docs/IMPROVEMENT_IDEAS.md'deki "Gözlemlenebilirlik #4 — Drift/regresyon
paneli" fikrinin uygulamasıdır. ``eval_history.read_history()``'in
döndürdüğü kayıtlardan Recall@1 / MRR / latency_ms_p50'nin zaman içindeki
son N koşusunu saf Python string formatting ile (yeni bir bağımlılık
eklemeden — matplotlib/pandas yok) basit bir tablo olarak yazdırır.

    python scripts/eval_trend_report.py
    python scripts/eval_trend_report.py --n 5
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mevzuat_rag.eval import eval_history  # noqa: E402

_COLUMNS = ("timestamp", "recall@1", "mrr", "latency_ms_p50", "n_queries")
_HEADER_LABELS = ("timestamp (UTC)", "recall@1", "mrr", "lat_p50_ms", "n_queries")
_WIDTHS = (26, 10, 8, 12, 10)


def _fmt_cell(value: object, width: int) -> str:
    text = "-" if value is None else str(value)
    return text.ljust(width)


def format_table(records: list[dict], n: int = 10) -> str:
    """Son ``n`` kaydı (en eskiden en yeniye) sabit genişlikli bir metin
    tablosu olarak döner. ``records`` boşsa açıklayıcı tek satır döner —
    çağıran taraf bunu ayrıca kontrol etmek zorunda kalmaz."""
    if not records:
        return "Henüz eval geçmişi yok (logs/eval_history.jsonl bulunamadı veya boş)."

    tail = records[-n:] if n > 0 else records

    header = "  ".join(label.ljust(w) for label, w in zip(_HEADER_LABELS, _WIDTHS))
    separator = "-" * len(header)

    lines = [header, separator]
    for record in tail:
        summary = record.get("summary", {})
        row_values = [
            record.get("timestamp"),
            summary.get("recall@1"),
            summary.get("mrr"),
            summary.get("latency_ms_p50"),
            summary.get("n_queries"),
        ]
        lines.append("  ".join(_fmt_cell(v, w) for v, w in zip(row_values, _WIDTHS)))

    lines.append(separator)
    lines.append(f"{len(tail)}/{len(records)} kayıt gösteriliyor.")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Retrieval eval geçmişinin trend tablosunu konsola yazdırır.")
    parser.add_argument("--n", type=int, default=10, help="Gösterilecek son kayıt sayısı (varsayılan: 10).")
    parser.add_argument(
        "--history-path",
        type=Path,
        default=None,
        help="logs/eval_history.jsonl dışında bir dosya kullanmak için (test/geliştirme amaçlı).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    records = eval_history.read_history(args.history_path)
    print(format_table(records, args.n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
