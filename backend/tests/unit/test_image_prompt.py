"""The image prompt compiler (generation-jobs task 3.3; ai-ports "Image prompt compiler").

Golden fixtures in `tests/fixtures/image_prompt/` hold the TESTING.md templates with the README's v2 fixes for four seed
characters (Python only: the frontend has no compiler). Regenerate deliberately with `HORIZON_UPDATE_GOLDEN=1`.

M15 (images-music design D6, D7): compiler v3 (doc 12 I1) and W3's identity edit; every golden records `version`.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

from horizon.ai.image_prompt import (
    AGE,
    CLOTHED,
    EMOTIONS,
    IDENTITY,
    IMAGE_PROMPT_VERSION,
    ORIGINAL,
    ImagePromptCompiler,
    fix_compound_colours,
)

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "image_prompt"
CHARS = ("chr_seedHana", "chr_seedAmara", "chr_seedRin", "chr_seedVictor")
SEED = ("chr_seedAmara", "chr_seedHana", "chr_seedMei", "chr_seedRin", "chr_seedTakeshi", "chr_seedVictor")


def compiler() -> ImagePromptCompiler:
    return ImagePromptCompiler(json.loads((ROOT / "seed" / "style-presets.json").read_text(encoding="utf-8"))["data"])


def seed_character(cid: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((ROOT / "seed" / "characters" / f"{cid}.json").read_text(encoding="utf-8"))["data"]
    return data


def compile_all(cid: str) -> dict[str, Any]:
    c = compiler()
    ch = seed_character(cid)
    p, a = ch["profile"], ch["appearance"]
    return {
        "character": cid,
        "version": IMAGE_PROMPT_VERSION,
        "base": c.base(p, a).prompt,
        "edits": {e: c.emotion_edit(p, e).prompt for e in EMOTIONS},
        "identity_edit": {e: c.emotion_edit(p, e, identity=True).prompt for e in EMOTIONS if e != "blink"},
        "sheet": c.sheet(p, a).prompt,
        "tweak": c.tweak(p, "a slightly warmer smile").prompt,
    }


def every_prompt(cid: str) -> list[str]:
    got = compile_all(cid)
    return [got["base"], got["sheet"], got["tweak"], *got["edits"].values(), *got["identity_edit"].values()]


@pytest.mark.parametrize("cid", CHARS)
def test_golden_prompts(cid: str) -> None:
    got = compile_all(cid)
    path = GOLDEN / f"{cid.removeprefix('chr_seed').lower()}.json"
    if os.environ.get("HORIZON_UPDATE_GOLDEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(got, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    assert got == json.loads(path.read_text(encoding="utf-8"))


def test_angry_has_no_blush() -> None:
    angry = compiler().emotion_edit({"age": 30}, "angry").prompt
    assert "flush" not in angry.lower() and "blush" not in angry.lower()
    assert "blush" in compiler().emotion_edit({"age": 30}, "embarrassed").prompt


def test_v2_fixes() -> None:
    hana = seed_character("chr_seedHana")
    base = compiler().base(hana["profile"], hana["appearance"]).prompt
    assert "faint warm smile" in base                      # baseline soft (fix 1)
    assert "pink-tinted" not in base and "chestnut with a soft pink tint" in base   # base colour first (fix 4)
    assert "curious pondering look" in compiler().emotion_edit({"age": 30}, "thinking").prompt   # fix 2
    rin = seed_character("chr_seedRin")
    assert "composed, slightly intense gaze" in compiler().base(rin["profile"], rin["appearance"]).prompt
    assert fix_compound_colours("a pink-tinted chestnut bob") == "a chestnut bob with a soft pink tint"


def test_base_follows_the_template() -> None:
    victor = seed_character("chr_seedVictor")
    base = compiler().base(victor["profile"], victor["appearance"]).prompt
    lines = base.split("\n")
    assert lines[0].endswith(f"Adult character with adult proportions and a mature face. {ORIGINAL}")
    assert lines[2].startswith("Subject: A 45-year-old constitutional litigator.")
    assert "Victor" not in base  # name-free (rule 2)
    assert lines[-1].startswith("Avoid: ")
    assert [ln.split(":")[0] for ln in lines if ln and ":" in ln][-5:] == ["Composition", "Expression", "Background",
                                                                          "Lighting", "Avoid"]


def test_under_18_is_refused() -> None:
    out = compiler().base({"age": 17, "role": "student", "name": "X"}, {"attributes": {}})
    assert out.prompt == "" and out.refused and out.warnings[0].startswith("REFUSED")
    assert compiler().emotion_edit({"age": 16}, "happy").refused


def test_tweak_ignores_pose_and_background() -> None:
    out = compiler().tweak({"age": 30}, "put her on a beach background")
    assert out.warnings and "Keep the pose, background and art style." in out.prompt
    assert not compiler().tweak({"age": 30}, "a warmer smile").warnings


# ── v3 (doc 12 I1) and W3 (images-music design D6, D7) ──
@pytest.mark.parametrize("cid", SEED)
def test_original_and_clothed_in_base_and_sheet(cid: str) -> None:
    ch = seed_character(cid)
    for prompt in (compiler().base(ch["profile"], ch["appearance"]).prompt,
                   compiler().sheet(ch["profile"], ch["appearance"]).prompt):
        assert prompt.split("\n")[0].endswith(f"mature face. {ORIGINAL}")   # after the style and adult lines
        outfit = prompt[prompt.index("Outfit: "):]
        assert outfit.split(" Accessories: ")[0].split("\n")[0].endswith(CLOTHED)


def test_clothed_adds_an_outfit_line_when_none_is_named() -> None:
    assert f"Outfit: everyday style. {CLOTHED}" in compiler().base({"age": 30, "role": "baker"}, {"attributes": {}}).prompt
    assert "Outfit" not in compiler().subject({"age": 30, "role": "baker"}, {"attributes": {}})


def test_the_checked_subject_is_unchanged_by_v3() -> None:
    """The I3 check (M14) reads `subject()` alone: v3's template lines never reach it."""
    hana = seed_character("chr_seedHana")
    subject = compiler().subject(hana["profile"], hana["appearance"])
    assert CLOTHED not in subject and ORIGINAL not in subject


def test_the_sheet_avoids_a_young_look() -> None:
    last = compiler().sheet({"age": 30, "role": "baker"}, {"attributes": {}}).prompt.split("\n")[-1]
    assert last.startswith("Avoid: ") and "childlike or teenage features" in last


def test_edits_keep_the_apparent_age_and_a_tweak_has_no_originality_line() -> None:
    for e in EMOTIONS:
        assert f"art style. {AGE} Change ONLY" in compiler().emotion_edit({"age": 30}, e).prompt
    tweak = compiler().tweak({"age": 30}, "a thin silver nose ring").prompt
    assert f"art style. {AGE} Apply ONLY this small change: a thin silver nose ring." in tweak
    assert ORIGINAL not in tweak


def test_the_identity_line_only_when_asked() -> None:
    plain = compiler().emotion_edit({"age": 30}, "happy").prompt
    marked = compiler().emotion_edit({"age": 30}, "happy", identity=True).prompt
    assert IDENTITY not in plain
    assert marked == plain.replace(f"{AGE} Change ONLY", f"{AGE} {IDENTITY} Change ONLY")


@pytest.mark.parametrize("cid", SEED)
def test_the_name_never_appears(cid: str) -> None:
    words = [w for w in re.split(r"[\s\-]+", str(seed_character(cid)["profile"]["name"])) if w]
    for prompt in every_prompt(cid):
        for w in words:
            assert not re.search(rf"\b{re.escape(w)}\b", prompt, re.I), (w, prompt[:80])


@pytest.mark.parametrize("cid", SEED)
def test_positive_wording_only(cid: str) -> None:
    for prompt in every_prompt(cid):
        assert not re.search(r"nudity|underwear|swimwear|blood|weapon", prompt, re.I)


def test_glasses_named_once() -> None:
    """U-14: Mei's chip said square glasses and her details put a pair on her head, so the base had two."""
    def eyes_line(glasses: str, details: str = "") -> str:
        a = {"attributes": {"eyes": {"shape": "almond", "color": "amber", "glasses": glasses}, "extraDetails": details}}
        return re.findall(r"Eyes: [^.]*\.", compiler().subject({"age": 41}, a))[0]
    assert eyes_line("square") == "Eyes: almond amber eyes, square glasses."
    assert eyes_line("half_rim") == "Eyes: almond amber eyes, half-rim glasses."
    assert eyes_line("square", "Rectangular glasses pushed up on her head.") == "Eyes: almond amber eyes."
    assert eyes_line("none", "A pencil through the bun.") == "Eyes: almond amber eyes."
    mei = seed_character("chr_seedMei")
    assert "pushed up" not in compiler().base(mei["profile"], mei["appearance"]).prompt
