"""The `agent` persona compiler (persona-prompt spec; docs/ai/04 P3–P6, doc 11 S1–S2, doc 08 V4; persona-context design
D3, D5, D7; tasks 2.1–2.2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from horizon.ai.agent.persona import (
    CARD_MAX,
    ELLIPSIS,
    CastMember,
    DebateBlock,
    PersonaInput,
    You,
    compile_persona,
    cut_to,
)
from horizon.domain.pricing import count_tokens

SEED = Path(__file__).resolve().parents[3] / "seed"


def char(cid: str) -> dict[str, Any]:
    out: dict[str, Any] = json.loads((SEED / "characters" / f"{cid}.json").read_text(encoding="utf-8"))["data"]
    return out


def world(wid: str) -> dict[str, Any]:
    out: dict[str, Any] = json.loads((SEED / "worlds" / f"{wid}.json").read_text(encoding="utf-8"))["data"]
    return out


def inp(cid: str, wid: str = "wld_seedMeridian", **kw: Any) -> PersonaInput:
    c, w = char(cid), world(wid)
    you = w.get("you") or {}
    base: dict[str, Any] = {"profile": c["profile"], "appearance_summary": c["appearance"]["appearanceSummary"],
                            "advisory": c["advisory"], "world_name": w["name"],
                            "you": You(display_name=you.get("displayName", ""), about=you.get("about", ""))}
    return PersonaInput(**{**base, **kw})


def test_amara_one_on_one_blocks_in_order() -> None:
    out = compile_persona(inp("chr_seedAmara"))
    heads = [line for line in out.text.split("\n") if line.startswith("# ")]
    assert heads == ["# Who you are", "# How you talk", "# Your world and the user", "# This session", "# How to reply"]
    assert out.text.startswith("# Who you are\nYou are Dr. Amara Okafor, 38 (she/her), an emergency physician")
    assert "Catchphrase (use rarely, not in every message): \"Let's figure out what's actually going on.\"" in out.text
    assert "How you sound (style only; don't copy these word for word):" in out.text
    assert "Looks: An adult woman with deep brown skin" in out.text
    assert "Write 1–3 short messages, each on its own line, about 70 words in all." in out.text
    assert out.tokens["total"] == count_tokens(out.text)


def test_no_tag_instruction_no_mature_line_and_no_tagline() -> None:
    p = char("chr_seedAmara")["profile"]
    text = compile_persona(inp("chr_seedAmara")).text
    assert "Begin every reply" not in text and "Mature" not in text and "Keep everything safe for work" in text
    assert text.count(p["tagline"]) <= 1   # the tagline equals the catchphrase: shown once, with "use rarely"


def test_relationship_reaches_the_world_block() -> None:
    c = char("chr_seedHana")
    profile = {**c["profile"], "relationshipToUser": "your girlfriend"}
    text = compile_persona(inp("chr_seedHana", "wld_seedSunnyHollow", profile=profile)).text
    assert "To you, they are: your girlfriend." in text


def test_advisory_line_uses_the_lowercased_role() -> None:
    text = compile_persona(inp("chr_seedAmara")).text
    assert ("You can explain and inform, but you are not their emergency physician & public-health researcher. "
            "For decisions about their own health") in text
    assert "you are not their" not in compile_persona(inp("chr_seedHana", "wld_seedSunnyHollow")).text


def test_group_names_profile_roles_and_others_in_the_speak_only_line() -> None:
    others = [CastMember(name="Rin Kobayashi", role="Game-design grad student"), CastMember(name="Takeshi Mori",
                                                                                            role="Retired train engineer")]
    text = compile_persona(inp("chr_seedHana", "wld_seedSunnyHollow", mode="group", others=others)).text
    assert "and: Rin Kobayashi (game-design grad student), Takeshi Mori (retired train engineer)." in text
    assert "Never write lines for Rin Kobayashi, Takeshi Mori or" in text
    assert "Write 1–2 short messages, each on its own line, about 50 words in all." in text


def test_watch_language_rule_and_premise() -> None:
    text = compile_persona(inp("chr_seedRin", "wld_seedSunnyHollow", mode="watch", premise="A storm traps them",
                               others=[CastMember(name="Hana Morisaki", role="Florist")])).text
    assert "is watching this scene and may step in. Premise: A storm traps them. With you: Hana Morisaki (florist)." in text
    assert "otherwise the premise's; if you can't tell, English." in text


def test_debate_block_and_rules_replace_the_chat_lines() -> None:
    d = DebateBlock(motion="This house would tax sugary drinks", format="two_sided", side="prop", teammates=["Mei Lin"],
                    opponents=[CastMember(name="Victor Hale", role="Constitutional litigator")])
    text = compile_persona(inp("chr_seedAmara", mode="debate", debate=d, turn_length="medium",
                               others=[CastMember(name="Mei Lin"), CastMember(name="Victor Hale")])).text
    assert 'The motion: "This house would tax sugary drinks".' in text
    assert "You argue FOR the motion, on the Proposition with Mei Lin." in text
    assert "Arguing against it: Victor Hale (constitutional litigator)." in text
    assert "- You argue for the motion for the whole debate. Never concede it or switch sides." in text
    assert "Use the motion's language; if you can't tell, English." in text
    assert "Don't end every message with a question." not in text and "very short" not in text
    assert "about 140 words." in text


def test_panel_debate() -> None:
    d = DebateBlock(motion="Remote work is better", format="panel")
    text = compile_persona(inp("chr_seedMei", mode="debate", debate=d, others=[CastMember(name="Victor Hale",
                                                                                         role="Litigator")])).text
    assert "Each panellist argues their own position. Also on the panel: Victor Hale (litigator)." in text
    assert "- Hold the position Mei would actually hold." in text


def test_formal_means_no_emoji() -> None:
    p = char("chr_seedVictor")["profile"]
    formal = {**p, "speakingStyle": {**p["speakingStyle"], "formality": "formal"}}
    assert "- Don't use emoji." in compile_persona(inp("chr_seedVictor", profile=formal)).text


def test_no_you_card_says_the_user() -> None:
    text = compile_persona(inp("chr_seedAmara", you=None)).text
    assert "This is a private one-to-one chat with the user." in text and "The user is" not in text


# ── 2.2: the card limit (P4) ──
def test_long_backstory_is_cut_at_a_sentence_end() -> None:
    p = char("chr_seedAmara")["profile"]
    long = " ".join(f"Sentence number {i} is about the long shift." for i in range(700))   # ≈ 5,000 words
    out = compile_persona(inp("chr_seedAmara", profile={**p, "backstory": long}))
    line = next(x for x in out.text.split("\n") if x.startswith("Backstory: "))
    body = line.removeprefix("Backstory: ")
    assert body.endswith("shift." + ELLIPSIS) and count_tokens(body) <= 600
    assert "backstory" in out.cut["capped"] and "How you sound" in out.text and out.tokens["card"] <= CARD_MAX


def test_abbreviation_is_not_a_sentence_end() -> None:
    text = "She trained early. Then she met Dr. Kim and stayed for years and years and years."
    cut, did = cut_to(text, 12)
    assert did and cut == "She trained early." + ELLIPSIS


def test_cjk_item_without_a_sentence_end() -> None:
    text = "我" * 200   # 600 bytes = 200 tokens
    cut, did = cut_to(text, 60)
    assert did and cut == "我" * 59 + ELLIPSIS and count_tokens(cut) <= 60


def test_cjk_sentence_end_needs_no_space() -> None:
    cut, _ = cut_to("今天很累。" + "我" * 300, 60)
    assert cut == "今天很累。" + ELLIPSIS


def test_space_fallback_and_emoji_at_the_cut() -> None:
    cut, did = cut_to("word " * 100, 10)
    assert did and cut.endswith("word" + ELLIPSIS) and count_tokens(cut) <= 10
    cut, did = cut_to("😀" * 100, 10)   # 4 bytes each: never split
    assert did and cut == "😀" * 6 + ELLIPSIS


def test_quote_after_a_sentence_end_stays_with_it() -> None:
    cut, _ = cut_to('He said "go home." Then nothing else happened for a very long time indeed.', 8)
    assert cut == 'He said "go home."' + ELLIPSIS


def test_step_two_drops_lists_and_keeps_the_voice() -> None:
    p = char("chr_seedAmara")["profile"]
    many = [f"area of expertise number {i} with detail" for i in range(80)]
    big = {**p, "expertise": many, "boundaries": many[:30], "quirks": many[:30]}
    out = compile_persona(inp("chr_seedAmara", profile=big))
    assert out.cut["step2"] and out.cut["dropped"]["expertise"] > 0 and out.tokens["card"] <= CARD_MAX
    for keep in ("Short paragraphs.", "Catchphrase (use rarely", "How you sound"):
        assert keep in out.text
