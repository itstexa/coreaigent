"""eval_history.py + eval_trend_report.py testleri.

docs/IMPROVEMENT_IDEAS.md'deki "Gözlemlenebilirlik #4 — Drift/regresyon
paneli" fikrinin uygulamasını doğrular: append_history/read_history
gerçekten JSONL'a yazıp okuyor mu, append-only mı çalışıyor, ve
eval_trend_report.py çökmeden çalışıyor mu.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mevzuat_rag.eval import eval_history
from scripts import eval_trend_report

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _fake_result(recall_1: float, mrr: float, latency_p50: float, n_queries: int = 9) -> dict:
    return {
        "per_case": [{"query": "test sorgu", "recall@1": recall_1, "mrr": mrr}],
        "summary": {
            "recall@1": recall_1,
            "recall@3": min(recall_1 + 0.1, 1.0),
            "recall@5": min(recall_1 + 0.2, 1.0),
            "mrr": mrr,
            "latency_ms_p50": latency_p50,
            "latency_ms_max": latency_p50 * 2,
            "n_queries": n_queries,
        },
    }


def test_append_history_writes_valid_jsonl_row(tmp_path: Path):
    history_path = tmp_path / "eval_history.jsonl"
    eval_history.append_history(_fake_result(0.8, 0.75, 120.0), history_path=history_path)

    lines = history_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert "timestamp" in row
    assert row["summary"]["recall@1"] == 0.8
    assert row["summary"]["mrr"] == 0.75
    assert row["summary"]["latency_ms_p50"] == 120.0
    # per_case yazılmamalı — dosya şişmesin diye yalnızca summary tutulur.
    assert "per_case" not in row


def test_append_history_then_read_history_round_trips(tmp_path: Path):
    history_path = tmp_path / "eval_history.jsonl"
    eval_history.append_history(_fake_result(0.8, 0.75, 120.0), history_path=history_path)

    records = eval_history.read_history(history_path=history_path)
    assert len(records) == 1
    assert records[0]["summary"]["recall@1"] == 0.8


def test_read_history_missing_file_returns_empty_list(tmp_path: Path):
    missing_path = tmp_path / "does_not_exist.jsonl"
    assert eval_history.read_history(history_path=missing_path) == []


def test_append_history_is_append_only_not_overwrite(tmp_path: Path):
    history_path = tmp_path / "eval_history.jsonl"

    eval_history.append_history(_fake_result(0.7, 0.6, 100.0), history_path=history_path)
    eval_history.append_history(_fake_result(0.8, 0.7, 110.0), history_path=history_path)
    eval_history.append_history(_fake_result(0.9, 0.8, 90.0), history_path=history_path)

    records = eval_history.read_history(history_path=history_path)
    assert len(records) == 3
    assert [r["summary"]["recall@1"] for r in records] == [0.7, 0.8, 0.9]
    # sırayla yazılmış — en eski satır dosyada hâlâ ilk satır.
    lines = history_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert json.loads(lines[0])["summary"]["recall@1"] == 0.7


def test_eval_trend_report_format_table_with_records():
    records = [
        {"timestamp": "2026-08-20T00:00:00+00:00", "summary": {"recall@1": 0.7, "mrr": 0.6, "latency_ms_p50": 100.0, "n_queries": 9}},
        {"timestamp": "2026-08-21T00:00:00+00:00", "summary": {"recall@1": 0.8, "mrr": 0.7, "latency_ms_p50": 90.0, "n_queries": 9}},
    ]
    table = eval_trend_report.format_table(records, n=10)
    assert "recall@1" in table
    assert "0.7" in table
    assert "0.8" in table
    assert "2/2 kayıt" in table


def test_eval_trend_report_format_table_empty_history_does_not_crash():
    table = eval_trend_report.format_table([], n=10)
    assert isinstance(table, str)
    assert table  # boş değil, açıklayıcı bir mesaj döner


def test_eval_trend_report_main_runs_end_to_end_against_real_history_file(tmp_path: Path, capsys):
    history_path = tmp_path / "eval_history.jsonl"
    eval_history.append_history(_fake_result(0.7, 0.6, 100.0), history_path=history_path)
    eval_history.append_history(_fake_result(0.85, 0.75, 95.0), history_path=history_path)

    exit_code = eval_trend_report.main(["--history-path", str(history_path), "--n", "5"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "recall@1" in out
    assert "0.85" in out


def test_eval_trend_report_script_runs_as_subprocess_without_crashing(tmp_path: Path):
    """Scriptin gerçekten `python scripts/eval_trend_report.py` olarak
    çalıştırılabildiğini (sys.path/import kurulumunun doğru olduğunu)
    doğrular — yalnızca fonksiyon çağırmak bunu kanıtlamaz."""
    history_path = tmp_path / "eval_history.jsonl"
    eval_history.append_history(_fake_result(0.75, 0.65, 105.0), history_path=history_path)

    project_root = SCRIPTS_DIR.parent
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "eval_trend_report.py"), "--history-path", str(history_path)],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "recall@1" in result.stdout
