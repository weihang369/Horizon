"""M8 offline checks, $0 (docs/ai/04 §5 check 1; docs/ai/05 §5 check 1; persona-context tasks 2.6, 4.10).

1. Compiles the `agent` system message for the six seed characters in all four modes, with each world's You card and
   the other two characters of that world as the cast, and prints a Markdown table of tokens per block
   (`count_tokens`, UTF-8 bytes / 3).
2. Builds the full `agent` request for the same 24 cases with a long history (a 600-token summary and about a full
   window of lines), checks each section against its cap, and checks that the next turn's request begins with this
   one's messages (X6).

Run from `backend/`:

    uv run python ../docs/ai/checks/m8/prompt_sizes.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from horizon.ai.agent.budget import WINDOWS
from horizon.ai.agent.persona import CARD_MAX, CastMember, DebateBlock, PersonaInput, You, compile_persona, persona_input
from horizon.ai.agent.turn import AgentTurnEngine
from horizon.ai.contexts import CharacterView, MessageView, ParticipantView, SessionContext, TurnContext, WorldView
from horizon.ai.naive.summary import cut_summary
from horizon.domain.pricing import count_tokens

ROOT = Path(__file__).resolve().parents[4]
SEED = ROOT / "seed"


def load(kind: str, id_: str) -> dict[str, Any]:
    out: dict[str, Any] = json.loads((SEED / kind / f"{id_}.json").read_text(encoding="utf-8"))["data"]
    return out


def seed_chars() -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8"))["data"] for p in sorted((SEED / "characters").glob("*.json"))]


def inputs(c: dict[str, Any], cast: list[dict[str, Any]]) -> dict[str, PersonaInput]:
    w = load("worlds", c["worldId"])
    you = w.get("you") or {}
    others = [CastMember(name=o["profile"]["name"], role=o["profile"]["role"]) for o in cast if o["id"] != c["id"]]
    base: dict[str, Any] = {"profile": c["profile"], "appearance_summary": c["appearance"]["appearanceSummary"],
                            "advisory": c["advisory"], "world_name": w["name"],
                            "you": You(display_name=you.get("displayName", ""), about=you.get("about", ""))}
    debate = DebateBlock(motion="This house would make every workplace offer a four-day week", format="two_sided",
                         side="prop", teammates=[], opponents=others)
    return {
        "1:1": PersonaInput(**base, mode="one_on_one"),
        "group": PersonaInput(**base, mode="group", others=others),
        "watch": PersonaInput(**base, mode="watch", others=others, premise="The power goes out on a stormy evening"),
        "debate": PersonaInput(**base, mode="debate", others=others, debate=debate, turn_length="medium"),
    }


class _Deps:
    """What the agent engine reads from AiDeps, for an offline request build (no gateway, no clock)."""

    def switch(self, name: str) -> bool:
        return False

    def windows(self) -> dict[str, int]:
        return dict(WINDOWS)

    def llm(self, key: str) -> Any:
        return None

    class prices:  # noqa: N801
        class chat:  # noqa: N801
            model = "deepseek/deepseek-v4.1-flash"


def turn_context(c: dict[str, Any], cast: list[dict[str, Any]], mode: str, n_messages: int) -> TurnContext:
    """A context with a long history: a 600-token summary plus about a full window of alternating lines."""
    w = load("worlds", c["worldId"])
    parts = [ParticipantView(character_id=o["id"], name=o["profile"]["name"], role="speaker",
                             character_role=o["profile"]["role"], side="prop" if o["id"] == c["id"] else "opp",
                             energy={"current": 500, "max": 1000}) for o in cast]
    others = [o for o in cast if o["id"] != c["id"]] or [c]
    recent = []
    for i in range(n_messages):
        if i % 2 == 0:
            recent.append(MessageView(id=f"m{i}", seq=i + 1, author_type="user", name="user", kind="chat",
                                      content=f"Message {i}: what do you make of the rota change and the late trains?"))
        else:
            o = c if i % 4 == 1 else others[i % len(others)]
            recent.append(MessageView(id=f"m{i}", seq=i + 1, author_type="character", character_id=o["id"],
                                      name=o["profile"]["name"], kind="chat",
                                      content="Honestly, it depends on the night.\nI'd sleep first, then decide."))
    summary = " ".join(f"Kai mentioned fact number {i} about work." for i in range(60))
    config = {"motion": "This house would ban algorithmic hiring", "format": "two_sided", "turnLength": "medium"} \
        if mode == "debate" else ({"premise": "The power goes out"} if mode == "watch" else None)
    s = SessionContext(session_id="ses_check", world=WorldView(id=w["id"], name=w["name"], you=w.get("you")), mode=mode,
                       title="check", config=config, participants=parts, recent=recent, summary=cut_summary(summary))
    return TurnContext(session=s, speaker=CharacterView(id=c["id"], name=c["profile"]["name"], profile=c["profile"],
                                                        appearance_summary=c["appearance"]["appearanceSummary"],
                                                        advisory=c["advisory"]), message_id="m", max_tokens=200)


def context_check(chars: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """doc 05 §5 check 1: every section within its cap with a long history, and the prefix byte-identical across two
    consecutive turns (X6)."""
    eng = AgentTurnEngine(_Deps())  # type: ignore[arg-type]
    rows = ["| Character | Mode | Card ≤ 1,500 | Summary ≤ 600 | History | Window | Prefix stable |",
            "|---|---|---|---|---|---|---|"]
    findings: list[str] = []
    modes = {"one_on_one": "1:1", "group": "group", "watch": "watch", "debate": "debate"}
    for c in chars:
        cast = [o for o in chars if o["worldId"] == c["worldId"]]
        for mode, label in modes.items():
            n = 250 if mode == "one_on_one" else 350           # about a full window of these lines
            a = turn_context(c, cast if mode != "one_on_one" else [c], mode, n)
            b = turn_context(c, cast if mode != "one_on_one" else [c], mode, n + 2)
            ra, pa = eng.request(a)
            rb, _ = eng.request(b)
            card = compile_persona(persona_input(a)).tokens["card"]
            summary = count_tokens(a.session.summary or "")   # the summary text; its heading is a fixed line
            hist = ra.messages[len(pa):-1] if ra.messages[-1]["role"] == "system" else ra.messages[len(pa):]
            history = sum(count_tokens(str(m["content"])) for m in hist)
            window = WINDOWS[mode]
            stable = rb.messages[:len(pa) + len(hist) - 1] == ra.messages[:len(pa) + len(hist) - 1]
            rows.append(f"| {c['profile']['name']} | {label} | {card} | {summary} | {history} | {window} | "
                        f"{'yes' if stable else '**no**'} |")
            if card > 1500 or summary > 600 or history > 2 * window or not stable:
                findings.append(f"{c['profile']['name']} ({label})")
    return rows, findings


def main() -> None:
    chars = seed_chars()
    rows = ["| Character | Mode | Card | World | Session | Rules | **Total** | Cut |", "|---|---|---|---|---|---|---|---|"]
    findings: list[str] = []
    for c in chars:
        cast = [o for o in chars if o["worldId"] == c["worldId"]]
        for mode, inp in inputs(c, cast).items():
            out = compile_persona(inp)
            t = out.tokens
            cut = "step 2" if out.cut["step2"] else ("capped: " + ", ".join(out.cut["capped"]) if out.cut["capped"] else "—")
            rows.append(f"| {c['profile']['name']} | {mode} | {t['card']} | {t['world']} | {t['session']} | "
                        f"{t['rules']} | **{t['total']}** | {cut} |")
            if out.cut["step2"] or out.cut["capped"] or t["card"] > CARD_MAX:
                findings.append(f"{c['profile']['name']} ({mode}): {cut}")
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print("\n".join(rows))
    print("\nFindings: " + ("; ".join(findings) if findings else "none (no seed card is capped or needs step 2)"))
    rows2, findings2 = context_check(chars)
    print("\n" + "\n".join(rows2))
    print("\nFindings: " + ("; ".join(findings2) if findings2 else "none (every cap holds and every prefix is stable)"))


if __name__ == "__main__":
    main()
