"""M8 offline checks, $0 (docs/ai/04 §5 check 1; docs/ai/05 §5 check 1; persona-context tasks 2.6, 4.10).

Compiles the `agent` system message for the six seed characters in all four modes, with each world's You card and the
other two characters of that world as the cast, and prints one Markdown table of tokens per block (`count_tokens`,
UTF-8 bytes / 3). Run from `backend/`:

    uv run python ../docs/ai/checks/m8/prompt_sizes.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from horizon.ai.agent.persona import CARD_MAX, CastMember, DebateBlock, PersonaInput, You, compile_persona

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


if __name__ == "__main__":
    main()
