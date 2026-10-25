"""Markdown export (session-lifecycle "Markdown export", D-59): a byte-for-byte port of the MockClient's
`exportMarkdown` and `footnoteCitations` (`mock/script/citations.ts`). Citation markers `[n]` become footnotes `[^k]`,
numbered across the whole transcript, and `## Sources` lists `[^k]: {title}, {locator}. "{quote}"`."""

from __future__ import annotations

import re
from typing import Any

_FENCE = re.compile(r"(```[\s\S]*?(?:```|\Z)|`[^`\n]*`)")
_MARK = re.compile(r"\[(\d{1,2})\](?!\()")


def map_markers(text: str, ns: set[int], fn: Any) -> str:
    """Replace `[n]` markers that have a citation, skipping inline code and fenced code blocks."""
    parts = _FENCE.split(text)
    out = []
    for i, part in enumerate(parts):
        if i % 2:
            out.append(part)
        else:
            out.append(_MARK.sub(lambda m: fn(int(m.group(1))) if int(m.group(1)) in ns else m.group(0), part))
    return "".join(out)


def footnote_citations(content: str, citations: list[dict[str, Any]] | None, notes: list[str]) -> str:
    if not citations:
        return content
    by_n = {int(c["n"]): c for c in citations}
    assigned: dict[int, int] = {}

    def fn(n: int) -> str:
        k = assigned.get(n)
        if k is None:
            c = by_n[n]
            k = len(notes) + 1
            assigned[n] = k
            quote = re.sub(r"\s+", " ", str(c["quote"])).strip()
            loc = f", {c['locator']}" if c.get("locator") else ""
            notes.append(f'[^{k}]: {c["title"]}{loc}. "{quote}"')
        return f"[^{k}]"

    return map_markers(content, set(by_n), fn)


def export_markdown(session: dict[str, Any], messages: list[dict[str, Any]], names: dict[str, str]) -> str:
    def name(cid: str | None) -> str:
        return names.get(cid, cid) if cid else ""

    cast = ", ".join(f"{name(p['characterId'])}{f' ({p['side']})' if p.get('side') else ''}" for p in session["participants"])
    lines = [f"# {session['title']}", "", f"- Mode: {session['mode']}", f"- Cast: {cast}"]
    cfg = session.get("config") or {}
    if session["mode"] == "debate":
        lines.append(f"- Motion: {cfg.get('motion')}")
    if session["mode"] == "watch":
        lines.append(f"- Premise: {cfg.get('premise')}")
    lines.append("")
    notes: list[str] = []
    for m in messages:
        a = m["author"]
        if a["type"] == "user":
            who = "You" if m["kind"] == "chat" else "MODERATOR"
        elif a["type"] == "character":
            who = name(a.get("characterId"))
        elif a["type"] == "host":
            who = "HOST"
        else:
            who = "—"
        emo = f" [{m['emotion']}]" if m.get("emotion") else ""
        lines += [f"**{who}**{emo}: {footnote_citations(m['content'], m.get('citations'), notes)}", ""]
    st = session.get("state") or {}
    v = st.get("verdict") if isinstance(st, dict) else None
    if v:
        lines += ["## Verdict", "", f"Stronger case: {v.get('strongerCase') or 'too close to call'}",
                  *(["", v["rationale"]] if v.get("rationale") else [])]
    if notes:
        lines += ["", "## Sources", "", *notes]
    return "\n".join(lines)
