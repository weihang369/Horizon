"""The free data checks (docs/ai/02 B2, §3 checks 2–3; ai-foundation design D37; task 7.9). No network, no key.

- **Splits** are assigned once, at item creation: `int(sha256(id)[:8], 16) % 3 == 0` → `test`, else `dev`. They are
  stored on the line; `split_changes` compares every existing item with `git show HEAD:<file>` so a split never moves.
- **Overlap** (`horizon eval overlap`): any 6-word shingle of a bank entry's wording (instructions, options, `what`,
  `not_for`, examples) that appears in a dataset item fails. It catches copying, not paraphrase.
- **Label review** (`horizon eval review <set>`): a seeded sample of max(15, ⌈n/5⌉) items is printed and recorded in
  `evals/reviews/<set>.json`; the user marks disagreements there, and two or more fail the set.
- **Corpus licence check** (`horizon eval corpus-check`): every corpus file has a `SOURCES.md` row, no file carries an
  outside credit, and `LICENSE` states the public-domain terms.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from horizon.ai.questions import bank
from horizon.evals.runner import EVALS_DIR

SHINGLE = 6
CREDIT_PATTERNS = ("©", "copyright", "reprinted with permission", "used with permission", "courtesy of",
                   "prepared by a contractor", "partner organization")
LICENSE_LINE = "US federal government work, public domain in the US, not covered by the repo's MIT licence"


# ── splits ──
def split_for(item_id: str) -> str:
    return "test" if int(hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:8], 16) % 3 == 0 else "dev"


def split_problems(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """The hash rule; M11's fresh cuts (`fresh: true`, debate D17) are held out, so they are all test."""
    def want(r: Mapping[str, Any]) -> str:
        return "test" if r.get("fresh") else split_for(str(r["id"]))
    return [f"{r['id']}: split {r['split']} but the rule says {want(r)}" for r in rows if r.get("split") != want(r)]


def _lines(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if line.strip():
            row = json.loads(line)
            out[str(row["id"])] = str(row.get("split"))
    return out


def split_changes(path: Path, repo: Path) -> list[str]:
    """Existing items whose split differs from the committed version (new items are free to be added)."""
    rel = path.resolve().relative_to(repo.resolve()).as_posix()
    try:
        old = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=repo, capture_output=True, text=True, check=True,
                             encoding="utf-8").stdout
    except (subprocess.CalledProcessError, OSError):
        return []   # not committed yet
    before, now = _lines(old), _lines(path.read_text(encoding="utf-8"))
    return [f"{i}: split changed {before[i]} → {now[i]}" for i in sorted(before) if i in now and now[i] != before[i]]


# ── overlap ──
def normalise(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", text.lower()).split()


def shingles(text: str, n: int = SHINGLE) -> set[tuple[str, ...]]:
    w = normalise(text)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def _strings(v: Any) -> Iterable[str]:
    if isinstance(v, str):
        yield v
    elif isinstance(v, Mapping):
        for x in v.values():
            yield from _strings(x)
    elif isinstance(v, list | tuple):
        for x in v:
            yield from _strings(x)


def bank_shingles() -> dict[tuple[str, ...], str]:
    out: dict[tuple[str, ...], str] = {}
    b = bank()
    for qid, e in b.entries.items():
        raw = dict(e.raw)
        parts = [raw.get("instructions"), raw.get("options"), raw.get("true"), raw.get("false"), raw.get("levels"),
                 raw.get("what"), raw.get("not_for"), raw.get("examples")]
        for s in _strings(parts):
            for sh in shingles(s):
                out.setdefault(sh, qid)
    return out


def overlap_problems(items: Iterable[Mapping[str, Any]]) -> list[str]:
    known = bank_shingles()
    out: list[str] = []
    for it in items:
        text = " ".join(_strings(it.get("item")))
        hit = next((sh for sh in shingles(text) if sh in known), None)
        if hit is not None:
            out.append(f"{it['id']}: copies `{' '.join(hit)}` from bank entry {known[hit]}")
    return out


# ── label review ──
def review_sample(ids: list[str], seed: int) -> list[str]:
    k = min(len(ids), max(15, math.ceil(len(ids) / 5)))
    return sorted(random.Random(seed).sample(sorted(ids), k))


def review_result(path: Path) -> tuple[bool, int]:
    """(passes, disagreements) from a filled review file."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    n = len(doc.get("disagree") or [])
    return n < 2, n


# ── corpus ──
def corpus_problems(root: Path = EVALS_DIR / "corpus") -> list[str]:
    if not root.is_dir():
        return []
    out: list[str] = []
    sources = (root / "SOURCES.md").read_text(encoding="utf-8") if (root / "SOURCES.md").is_file() else ""
    lic = (root / "LICENSE").read_text(encoding="utf-8") if (root / "LICENSE").is_file() else ""
    if LICENSE_LINE.lower() not in " ".join(lic.split()).lower():
        out.append("LICENSE: must state the public-domain terms")
    for f in sorted(p for p in root.rglob("*") if p.is_file() and p.name not in ("SOURCES.md", "LICENSE")):
        rel = f.relative_to(root).as_posix()
        if f.suffix.lower() != ".md":
            out.append(f"{rel}: only Markdown text is committed (no figures, images or logos)")
            continue
        if rel not in sources:
            out.append(f"{rel}: no SOURCES.md row")
        low = f.read_text(encoding="utf-8").lower()
        for pat in CREDIT_PATTERNS:
            if pat in low:
                out.append(f"{rel}: contains {pat!r} (an outside credit?)")
    return out
