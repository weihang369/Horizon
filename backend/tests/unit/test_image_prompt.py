"""The image prompt compiler (generation-jobs task 3.3; ai-ports "Image prompt compiler").

Golden fixtures in `tests/fixtures/image_prompt/` hold the TESTING.md templates with the README's v2 fixes for four seed
characters (Python only: the frontend has no compiler). Regenerate deliberately with `HORIZON_UPDATE_GOLDEN=1`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from horizon.ai.image_prompt import EMOTIONS, ImagePromptCompiler, fix_compound_colours

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "image_prompt"
CHARS = ("chr_seedHana", "chr_seedAmara", "chr_seedRin", "chr_seedVictor")


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
        "base": c.base(p, a).prompt,
        "edits": {e: c.emotion_edit(p, e).prompt for e in EMOTIONS},
        "sheet": c.sheet(p, a).prompt,
        "tweak": c.tweak(p, "a slightly warmer smile").prompt,
    }


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
    assert lines[0].endswith("Adult character with adult proportions and a mature face.")
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
