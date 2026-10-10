"""The `horizon eval …` subcommands (evaluation-harness spec; ai-foundation design D33–D37).

Registered on the main parser by `horizon.cli`. Each command lives in its own function so the main CLI stays small.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any


def _bank_lock(_args: argparse.Namespace) -> int:
    """Record the bank's versions and content hashes (design D1). Refuses a changed entry whose version didn't go up."""
    from horizon.ai.questions import BankError, check_lock, load_bank, write_lock

    b = load_bank()
    try:
        lock = write_lock(b)
    except BankError as e:
        print(f"horizon: {e}", file=sys.stderr)
        return 2
    problems = check_lock(b)
    for p in problems:
        print(f"horizon: {p}", file=sys.stderr)
    print(f"horizon: questions.lock.json records {len(lock)} question(s)")
    return 1 if problems else 0


def register(sub: Any) -> None:
    ev = sub.add_parser("eval", help="the evaluation harness and its dev commands")
    esub = ev.add_subparsers(dest="eval_cmd", required=True)
    esub.add_parser("bank-lock", help="record the question bank's versions (after bumping an edited question)") \
        .set_defaults(fn=_bank_lock)
