"""The question bank (docs/ai/02 B9, doc 13 W5; question-bank spec; ai-foundation design D1–D3).

Every Jev question is one JSON file here, `<id>.json`, loaded once into an immutable `QuestionBank`. The live
`Decider` and `horizon eval` both build requests from it, so the evaluation measures exactly what runs.

- **Conventions** (`_conventions.json`): the doc 11 S6 sentence the loader appends to every question's instructions,
  and the longest text a `label` state field may hold. The file is part of every entry's lock hash, so editing the
  sentence re-versions every question at once.
- **The lock** (`questions.lock.json`): `{id: {version, sha256}}`. `check_lock()` fails when an entry's content
  changed without a higher version, when a version went down, or when an entry is missing from the lock.
  `write_lock()` (the `horizon eval bank-lock` dev command) refuses to record a changed entry whose version didn't go up.
- **Options.** A static option compiles to its `what`, then ` Not for: …`, then ` For example: …` (B9: one string per
  option). A dynamic option fills the entry's template from the caller's values; the version covers the template.
- **Shuffle** (doc 01 A3 rule 4): options are ordered by SHA-256 of `"{seed}:{key}"`, so a seed always gives the same
  order and `none` is shuffled with the rest.
- **One subject in the instructions** (M9, turn-plan-emotion design D11): `{name}` in an entry's instructions is filled
  with the name of the character the question is about. The name follows the `label` rule (short, one line); entries
  without the placeholder compile exactly as before.
- **A debate side** (M11, debate design D7, D12): `{side}` and `{other}` name the side a question is about and the
  other one, filled from code labels only ("Proposition", "Opposition"), never from user text; a score entry's `{n}` is
  a criterion's position (1–6). Entries without them compile exactly as before.
- **Shared knobs** (M11, D7, D12): `floor.member` is the `floor` of every `member_*` entry and `verdict.margin` the
  `margin` threshold of every `rubric_*` entry; the loader refuses a bank where they differ.
- **Shared text** (M14, safety D3): the content rules (doc 11 S1's two lists) are fixed text at the end of the
  instructions of `unsafe_request`, `unsafe_note`, `output_rules` and `motion_rules`, never a state field; the loader
  refuses a bank where the copies differ. `safety.tSteer` is the `tSteer` of both `unsafe_*` entries (a shared knob).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from horizon.ai.decider import Choice, Noul, QMeta, Question, Score

HERE = Path(__file__).resolve().parent
CONVENTIONS = HERE / "_conventions.json"
LOCK = HERE / "questions.lock.json"
KINDS = ("choice", "noul", "score")
FIELD_KINDS = frozenset({"quoted", "label", "number", "id", "bool", "list_label"})
NAME = "{name}"   # the one placeholder an entry's instructions may hold (design D11)
SIDES = ("Proposition", "Opposition")   # M11 (debate D7): the only values `{side}` / `{other}` take
POSITION_MAX = 6                         # `{n}`: a rubric criterion's position (the contract allows 2–6 criteria)
SHARED_KNOBS = (("floor.member", "member_", "floor"), ("verdict.margin", "rubric_", "thresholds.margin"),
                ("safety.tSteer", "unsafe_", "thresholds.tSteer"))
RULES_START = "Outside the content rules:"   # M14 (safety D3): where S1's rules text starts in an entry's instructions
SHARED_TEXT = (("content rules", ("unsafe_request", "unsafe_note", "output_rules", "motion_rules", "judge_breaks_rules"),
                RULES_START),)   # M14 (safety D21): the drift judge reads the same rules


def canonical(o: Any) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class BankError(ValueError):
    """A malformed entry, an unknown id, or a lock mismatch."""


@dataclass(frozen=True)
class BankEntry:
    id: str
    version: int
    purpose: str
    type: Literal["choice", "noul", "score"]
    label: str
    instructions: str
    raw: Mapping[str, Any] = field(repr=False)
    state: Mapping[str, str] = field(default_factory=dict)
    deadline: str = ""
    floor: float | None = None
    thresholds: Mapping[str, float] = field(default_factory=dict)
    shuffle: bool = False

    @property
    def options(self) -> Mapping[str, Any]:
        return self.raw.get("options") or {}


def _load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _entry(raw: Mapping[str, Any], name: str) -> BankEntry:
    def need(k: str) -> Any:
        if k not in raw:
            raise BankError(f"{name}: missing {k!r}")
        return raw[k]

    kind = need("type")
    if kind not in KINDS:
        raise BankError(f"{name}: type must be one of {KINDS}")
    if need("id") != name:
        raise BankError(f"{name}: id {raw['id']!r} must match the file name")
    version = need("version")
    if not isinstance(version, int) or version < 1:
        raise BankError(f"{name}: version must be a positive integer")
    state = need("state")
    bad = {k: v for k, v in state.items() if v not in FIELD_KINDS}
    if bad:
        raise BankError(f"{name}: unknown state field kinds {bad}")
    for k, v in state.items():
        if v == "quoted" and not k.startswith("quoted_"):
            raise BankError(f"{name}: quoted field {k!r} must be named quoted_*")
        if v != "quoted" and k.startswith("quoted_"):
            raise BankError(f"{name}: field {k!r} is named quoted_* but declared {v!r}")
    if kind == "choice":
        opts = need("options")
        if opts.get("kind") not in ("static", "dynamic"):
            raise BankError(f"{name}: options.kind must be static or dynamic")
        if opts["kind"] == "static" and not opts.get("items"):
            raise BankError(f"{name}: static options need items")
        if opts["kind"] == "dynamic" and not opts.get("describe"):
            raise BankError(f"{name}: dynamic options need a describe template")
    elif kind == "noul":
        need("true")
        need("false")
    else:
        levels = need("levels")
        if not isinstance(levels, list) or not 2 <= len(levels) <= 10:
            raise BankError(f"{name}: a score has 2–10 levels")
    floor = raw.get("floor")
    return BankEntry(id=name, version=version, purpose=str(need("purpose")), type=kind, label=str(need("label")),
                     instructions=str(need("instructions")), raw=raw, state=dict(state),
                     deadline=str(raw.get("deadline") or raw["purpose"]),
                     floor=float(floor) if floor is not None else None,
                     thresholds={str(k): float(v) for k, v in (raw.get("thresholds") or {}).items()},
                     shuffle=bool(raw.get("shuffle", False)))


def shuffled(keys: Sequence[str], seed: str) -> list[str]:
    """The seeded option order (A3 rule 4): stable for a seed, independent of the input order."""
    return sorted(keys, key=lambda k: hashlib.sha256(f"{seed}:{k}".encode()).hexdigest())


def option_label(value: Any, limit: int) -> str:
    """A value filled into a dynamic option follows the `label` rule (doc 11 S6; group-watch design D7): one line, at
    most `limit` characters. Longer user-written text belongs in a `quoted_*` state field; here it is cut."""
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def static_option(o: Mapping[str, Any]) -> str:
    text = str(o["what"]).strip()
    if o.get("not_for"):
        text += f" Not for: {str(o['not_for']).strip()}"
    ex = o.get("examples") or []
    if ex:
        text += " For example: " + "; ".join(str(x).strip() for x in ex)
    return text


@dataclass(frozen=True)
class QuestionBank:
    entries: Mapping[str, BankEntry]
    conventions: Mapping[str, Any]

    @property
    def sentence(self) -> str:
        return str(self.conventions["quotedSentence"])

    def get(self, qid: str) -> BankEntry:
        try:
            return self.entries[qid]
        except KeyError as e:
            raise BankError(f"unknown question {qid!r}") from e

    def question(self, qid: str, *, values: Sequence[Mapping[str, Any]] = (), exclude: Sequence[str] = (),
                 seed: str | None = None, about: str | None = None, name: str | None = None,
                 none: bool = True, side: str | None = None, n: int | None = None) -> Question:
        """Compile an entry into the Decider's question. `values` fills a dynamic choice's options (each needs a
        `key`); `exclude` drops option keys (a mentioned speaker); `seed` orders options when the entry shuffles;
        `name` fills the instructions' `{name}`; `none=False` leaves out a dynamic choice's `none` option (M10,
        group-watch design D6: the first slot has no `none` when nobody is mentioned); `side` fills `{side}` and
        `{other}` (M11), and `n` a score's `{n}`."""
        e = self.get(qid)
        instructions = f"{self._sided(e, self._named(e, name), side, n).rstrip()} {self.sentence}"
        meta = QMeta(id=e.id, version=e.version, label=e.label, purpose=e.purpose, deadline=e.deadline,
                     state=e.state, about=about, label_max=int(self.conventions.get("labelMaxChars", 40)))
        if e.type == "noul":
            return Noul(instructions, str(e.raw["true"]), str(e.raw["false"]), meta=meta)
        if e.type == "score":
            return Score(instructions, [str(x) for x in e.raw["levels"]], meta=meta)
        opts = e.options
        options: dict[str, str] = {}
        if opts["kind"] == "static":
            for k, o in opts["items"].items():
                options[str(k)] = static_option(o)
        else:
            limit = int(self.conventions.get("labelMaxChars", 40))
            for v in values:
                key = str(v["key"])
                if key in exclude:
                    continue
                filled = {k: (x if k == "key" else option_label("" if x is None else x, limit)) for k, x in v.items()}
                options[key] = str(opts["describe"]).format_map(filled)
            if opts.get("none") and none:
                options["none"] = str(opts["none"])
        if e.shuffle:
            if seed is None:
                raise BankError(f"{qid}: a shuffled question needs a seed")
            options = {k: options[k] for k in shuffled(list(options), f"{seed}:{qid}")}
        return Choice(instructions, options, meta=meta)

    def _named(self, e: BankEntry, name: str | None) -> str:
        if NAME not in e.instructions:
            return e.instructions
        limit = int(self.conventions.get("labelMaxChars", 40))
        if name is None or not name.strip():
            raise BankError(f"{e.id}: its instructions name a subject; compile it with a name")
        if len(name) > limit or "\n" in name or "\r" in name:
            raise BankError(f"{e.id}: a subject's name must be one line of at most {limit} characters")
        return e.instructions.replace(NAME, name.strip())

    @staticmethod
    def _sided(e: BankEntry, text: str, side: str | None, n: int | None) -> str:
        """M11 (debate D7, D12): `{side}` / `{other}` from the two code labels only, and `{n}` a position 1–6."""
        if "{side}" in text or "{other}" in text:
            if side not in SIDES:
                raise BankError(f"{e.id}: compile it with side set to one of {SIDES} (got {side!r})")
            other = SIDES[1] if side == SIDES[0] else SIDES[0]
            text = text.replace("{side}", side).replace("{other}", other)
        if "{n}" in text:
            if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= POSITION_MAX:
                raise BankError(f"{e.id}: compile it with n, a whole number from 1 to {POSITION_MAX} (got {n!r})")
            text = text.replace("{n}", str(n))
        return text

    # ── the lock ──
    def digest(self, qid: str) -> str:
        return hashlib.sha256(canonical({"entry": self.entries[qid].raw, "conventions": self.conventions})
                              .encode("utf-8")).hexdigest()

    def lock_problems(self, lock: Mapping[str, Any]) -> list[str]:
        out: list[str] = []
        for qid, e in sorted(self.entries.items()):
            row = lock.get(qid)
            if row is None:
                out.append(f"{qid}: not in the lock (run `horizon eval bank-lock`)")
                continue
            if e.version < int(row["version"]):
                out.append(f"{qid}: version went down ({row['version']} → {e.version})")
            elif self.digest(qid) != row["sha256"]:
                if e.version == int(row["version"]):
                    out.append(f"{qid}: content changed without a version bump (still v{e.version})")
                else:
                    out.append(f"{qid}: bumped to v{e.version}; run `horizon eval bank-lock` to record it")
            elif e.version != int(row["version"]):
                out.append(f"{qid}: version changed without a content change")
        for qid in sorted(set(lock) - set(self.entries)):
            out.append(f"{qid}: in the lock but no entry exists")
        return out

    def new_lock(self, old: Mapping[str, Any]) -> dict[str, Any]:
        """The lock after an edit. Refuses a changed entry whose version didn't go up."""
        out: dict[str, Any] = {}
        for qid, e in sorted(self.entries.items()):
            row, digest = old.get(qid), self.digest(qid)
            if row is not None and digest != row["sha256"] and e.version <= int(row["version"]):
                raise BankError(f"{qid}: content changed; bump its version above {row['version']} first")
            out[qid] = {"version": e.version, "sha256": digest}
        return out


def load_bank(root: Path = HERE) -> QuestionBank:
    conventions = _load_json(root / CONVENTIONS.name)
    entries: dict[str, BankEntry] = {}
    for p in sorted(root.glob("*.json")):
        if p.name.startswith("_") or p.name == LOCK.name:
            continue
        entries[p.stem] = _entry(_load_json(p), p.stem)
    _check_shared(entries)
    _check_shared_text(entries)
    return QuestionBank(entries=entries, conventions=conventions)


def _knob(e: BankEntry, where: str) -> float | None:
    return e.floor if where == "floor" else e.thresholds.get(where.split(".", 1)[1])


def _check_shared(entries: Mapping[str, BankEntry]) -> None:
    """M11 (debate D7, D12): one knob held by several entries must hold one value."""
    for knob, prefix, where in SHARED_KNOBS:
        values = {qid: _knob(e, where) for qid, e in sorted(entries.items()) if qid.startswith(prefix)}
        if len(set(values.values())) > 1:
            raise BankError(f"{knob} differs across its entries: {values}")


def _check_shared_text(entries: Mapping[str, BankEntry]) -> None:
    """M14 (safety D3): fixed text held by several entries must be one text, as a shared knob is one value."""
    for what, ids, start in SHARED_TEXT:
        present = {qid: entries[qid].instructions for qid in ids if qid in entries}
        if not present:
            continue
        texts = {qid: (t[t.find(start):].strip() if start in t else None) for qid, t in present.items()}
        if len(set(texts.values())) > 1 or None in texts.values():
            raise BankError(f"the {what} text differs across {', '.join(sorted(texts))}")


@lru_cache(maxsize=1)
def bank() -> QuestionBank:
    """The shipped bank, loaded once."""
    return load_bank()


def read_lock(path: Path = LOCK) -> dict[str, Any]:
    return dict(_load_json(path)) if path.is_file() else {}


def check_lock(b: QuestionBank | None = None, path: Path = LOCK) -> list[str]:
    return (b or bank()).lock_problems(read_lock(path))


def write_lock(b: QuestionBank | None = None, path: Path = LOCK) -> dict[str, Any]:
    new = (b or bank()).new_lock(read_lock(path))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return new
