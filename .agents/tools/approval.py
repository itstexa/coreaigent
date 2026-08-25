#!/usr/bin/env python3
"""Record human approval for the active pipeline entry.

This is intentionally a small, dependency-free CLI. The approval log is an
audit record; the command is the human authorization event consumed by the
next pipeline stage.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path


DEFAULT_LOG = Path(__file__).resolve().parents[2] / "docs" / "APPROVAL_LOG.md"


class ApprovalError(ValueError):
    """A user-correctable approval command error."""


def _active_entry(text: str) -> tuple[int, int, str]:
    start_match = re.search(r"^## Active Entry\s*$", text, re.MULTILINE)
    if not start_match:
        raise ApprovalError("Approval log has no '## Active Entry' section.")

    end_match = re.search(r"^---\s*$|^## History\s*$", text[start_match.end() :], re.MULTILINE)
    if not end_match:
        raise ApprovalError("Active approval entry has no end marker.")

    start = start_match.end()
    end = start + end_match.start()
    return start, end, text[start:end]


def _field(entry: str, name: str) -> str:
    pattern = re.compile(rf"^- \*\*{re.escape(name)}\*\*: ?(?P<value>.*)$", re.MULTILINE)
    match = pattern.search(entry)
    if not match:
        raise ApprovalError(f"Active entry is missing the '{name}' field.")
    return match.group("value").strip()


def _replace_field(entry: str, name: str, value: str) -> str:
    pattern = re.compile(rf"^(- \*\*{re.escape(name)}\*\*:)(?: ?).*$", re.MULTILINE)
    updated, count = pattern.subn(lambda match: f"{match.group(1)} {value}", entry, count=1)
    if count != 1:
        raise ApprovalError(f"Active entry is missing the '{name}' field.")
    return updated


def _parse_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ApprovalError("Date must be an ISO date: YYYY-MM-DD.") from exc


def _write_active(log_path: Path, text: str, entry: str, start: int, end: int) -> None:
    log_path.write_text(text[:start] + entry + text[end:], encoding="utf-8")


def status(log_path: Path) -> int:
    _, _, entry = _active_entry(log_path.read_text(encoding="utf-8"))
    print(f"Status: {_field(entry, 'Status')}")
    print(f"Stage: {_field(entry, 'Stage')}")
    print(f"Approved By: {_field(entry, 'Approved By')}")
    print(f"Approval Date: {_field(entry, 'Approval Date')}")
    return 0


def approve(log_path: Path, stage: str, approver: str, approval_date: str) -> int:
    text = log_path.read_text(encoding="utf-8")
    start, end, entry = _active_entry(text)
    current_status = _field(entry, "Status")
    current_stage = _field(entry, "Stage")

    if not stage.strip():
        raise ApprovalError("Stage cannot be empty.")
    if not approver.strip():
        raise ApprovalError("Approver cannot be empty.")
    if current_stage != stage:
        raise ApprovalError(f"Active entry is for stage '{current_stage}', not '{stage}'.")
    if current_status != "Pending Approval":
        raise ApprovalError(f"Active entry is already '{current_status}'.")

    normalized_date = _parse_date(approval_date)
    entry = _replace_field(entry, "Status", "Approved")
    entry = _replace_field(entry, "Approved By", approver.strip())
    entry = _replace_field(entry, "Approval Date", normalized_date)
    _write_active(log_path, text, entry, start, end)
    print(f"Approved: {stage} by {approver.strip()} on {normalized_date}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record pipeline approval in docs/APPROVAL_LOG.md")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG, help="approval log path")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("status", help="show the active approval entry")

    approve_parser = commands.add_parser("approve", help="approve the active entry")
    approve_parser.add_argument("--stage", required=True, help="exact active-entry stage")
    approve_parser.add_argument("--by", required=True, dest="approver", help="human approver name")
    approve_parser.add_argument("--date", default=date.today().isoformat(), dest="approval_date")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    log_path = args.log.resolve()
    if not log_path.is_file():
        parser.error(f"Approval log not found: {log_path}")

    try:
        if args.command == "status":
            return status(log_path)
        return approve(log_path, args.stage, args.approver, args.approval_date)
    except (ApprovalError, OSError) as exc:
        print(f"approval: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
