from __future__ import annotations

import subprocess
import sys
from pathlib import Path


CLI = Path(__file__).parents[1] / ".agents" / "tools" / "approval.py"


def make_log(tmp_path: Path, *, status: str = "Pending Approval", stage: str = "Requirement Analysis") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    log = tmp_path / "APPROVAL_LOG.md"
    log.write_text(
        """# Approval Log

## Active Entry

- **Status**: {status}
- **Stage**: {stage}
- **Session Started**: 2026-08-25
- **Related Doc(s)**: `docs/design/DESIGN.md`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - test scope
- **Open Questions Resolved This Session**:
  - —
- **Approved By**:
- **Approval Date**:

---

## History
""".format(status=status, stage=stage),
        encoding="utf-8",
    )
    return log


def run(log: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), "--log", str(log), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_status_reports_active_entry(tmp_path: Path) -> None:
    result = run(make_log(tmp_path), "status")

    assert result.returncode == 0
    assert "Status: Pending Approval" in result.stdout
    assert "Stage: Requirement Analysis" in result.stdout


def test_approve_records_human_decision_and_date(tmp_path: Path) -> None:
    log = make_log(tmp_path)

    result = run(
        log,
        "approve",
        "--stage",
        "Requirement Analysis",
        "--by",
        "Serda",
        "--date",
        "2026-08-25",
    )

    assert result.returncode == 0
    content = log.read_text(encoding="utf-8")
    assert "- **Status**: Approved" in content
    assert "- **Approved By**: Serda" in content
    assert "- **Approval Date**: 2026-08-25" in content


def test_approve_rejects_wrong_stage_without_mutating_log(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    before = log.read_text(encoding="utf-8")

    result = run(log, "approve", "--stage", "Solution Architecture", "--by", "Serda")

    assert result.returncode == 2
    assert "not 'Solution Architecture'" in result.stderr
    assert log.read_text(encoding="utf-8") == before


def test_approve_rejects_empty_approver_and_invalid_date(tmp_path: Path) -> None:
    empty_approver = run(
        make_log(tmp_path / "empty"),
        "approve",
        "--stage",
        "Requirement Analysis",
        "--by",
        "   ",
    )
    assert empty_approver.returncode == 2
    assert "Approver cannot be empty" in empty_approver.stderr

    invalid_date = run(
        make_log(tmp_path / "date"),
        "approve",
        "--stage",
        "Requirement Analysis",
        "--by",
        "Serda",
        "--date",
        "25-08-2026",
    )
    assert invalid_date.returncode == 2
    assert "ISO date" in invalid_date.stderr


def test_approve_rejects_already_decided_entry(tmp_path: Path) -> None:
    log = make_log(tmp_path, status="Approved")

    result = run(log, "approve", "--stage", "Requirement Analysis", "--by", "Serda")

    assert result.returncode == 2
    assert "already 'Approved'" in result.stderr
