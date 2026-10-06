"""The scripted profile drafter's bank: a byte-for-byte port of `frontend/src/mock/banks/drafts.ts` (`draftFromSeed`,
`regenerateField`), pinned by the shared fixtures in `tests/fixtures/drafts/` (generation-jobs design D9).

Key order follows the TypeScript object literals, so the serialised draft is identical too.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from horizon.domain.jsrng import JsRng, js_slice

PROFESSIONAL = re.compile(r"doctor|physician|nurse|lawyer|attorney|counsel|economist|therapist|accountant|pharmac|engineer"
                          r"|teacher|professor|scientist|advisor|consultant", re.I)
MEDICAL = re.compile(r"doctor|nurse|physician", re.I)
NAMES = ("Sarah", "Kenji", "Lucia", "Omar", "Priya", "Theo", "Aiko", "Marcus", "Noor", "Elias")
TRAITS = ("curious", "patient", "dry-humoured", "warm", "precise", "stubborn", "playful", "loyal", "candid")

Draft = dict[str, Any]


def _upper_first(s: str) -> str:
    return s[:1].upper() + s[1:]


def pick_name(seed: str) -> str:
    m = re.match(r"\s*([A-Z][a-z]+)(?=[\s,])", seed)
    return m.group(1) if m else NAMES[JsRng(seed).int(0, len(NAMES) - 1)]


def role_from(seed: str) -> str:
    m = re.search(r"\b(?:a|an)\s+([^,.]+)", seed, re.I)
    raw = re.sub(r"\bwho\b.*\Z", "", m.group(1) if m else seed, flags=re.I).strip()
    if not raw:
        return "Friend"
    return js_slice(re.sub(r"^[A-Za-z0-9_]", lambda x: x.group(0).upper(), raw), 60)


def draft_from_seed(seed: str, intent: str, palette_ids: Sequence[str]) -> Draft:
    rng = JsRng(f"draft:{seed}")
    name = pick_name(seed)
    role = role_from(seed)
    advisory = intent == "expert" or bool(PROFESSIONAL.search(seed))
    traits = rng.shuffle(TRAITS)[:4]
    age = rng.int(24, 58)
    tagline = rng.pick(["Ask me the real question.", "One thing at a time.", "I've seen worse. Probably.",
                        "Let's make this simple."])
    summary = f"{_upper_first(traits[0][0])}{traits[0][1:]} and {traits[1]}, with a {traits[2]} streak."
    tone = rng.pick(["warm", "dry", "upbeat", "measured"])
    formality = rng.pick(["casual", "neutral", "formal"])
    quirk = rng.pick(["Counts points on fingers.", "Answers questions with a question first.", "Uses food metaphors."])
    catch = rng.pick(["Here's the thing.", "Fair, but no.", "Okay, story time."])
    profile: dict[str, Any] = {
        "name": name,
        "role": role,
        "age": age,
        "pronouns": "",
        "tagline": tagline,
        "personality": {"summary": summary, "traits": traits},
        "backstory": f"{name} spent years as a {role.lower()} before anyone thought to ask what they actually think. "
                     "Now they say it.",
        "speakingStyle": {"summary": "Plain words, short paragraphs, the occasional aside.", "tone": tone,
                          "formality": formality, "quirks": [quirk], "catchphrases": [catch]},
        "expertise": [role.lower()],
        "goals": "Be useful without pretending to know everything.",
        "boundaries": ["No definitive diagnoses or legal advice; points to a professional for decisions."] if advisory
        else ["Keeps things friendly and SFW."],
        "greeting": f"Hi, I'm {name}. What can I do for you?",
        "exampleLines": [],
        "relationshipToUser": "a close friend" if intent == "companion" else "",
        "systemPromptPreview": f"You are {name}, {role.lower()}. Speak in a {traits[0]}, {traits[1]} way.",
    }
    age_band = "young_adult" if age < 30 else "adult" if age < 45 else "middle_aged"
    body = {"ageBand": age_band, "build": rng.pick(["slim", "average", "athletic"]), "height": "average",
            "skinTone": rng.pick(["light", "beige", "olive", "tan", "brown", "deep brown"])}
    face = {"shape": rng.pick(["oval", "round", "heart", "square"]), "baseline": "neutral", "marks": []}
    eyes = {"shape": rng.pick(["almond", "round", "upturned"]), "color": rng.pick(["dark brown", "brown", "hazel", "green", "grey"]),
            "glasses": rng.pick(["none", "none", "round", "square"])}
    hair = {"length": rng.pick(["short", "chin", "shoulder", "long"]),
            "style": rng.pick(["straight", "wavy", "curly", "ponytail", "low bun", "bob"]),
            "color": rng.pick(["black", "dark brown", "chestnut", "auburn", "honey blonde"]),
            "fringe": rng.pick(["none", "side-swept", "curtain"])}
    medical = bool(MEDICAL.search(seed))
    archetype = ("medical" if PROFESSIONAL.search(seed) and medical else "business") if advisory \
        else rng.pick(["casual", "street", "cosy"])
    outfit = {"archetype": archetype, "primaryColor": "#2F5D8A", "secondaryColor": "#F5F2EA"}
    accessories = ["stethoscope"] if advisory and medical else [rng.pick(["watch", "earrings", "scarf"])]
    vibe = [rng.pick(["warm", "confident", "gentle", "energetic"])]
    attributes = {"body": body, "face": face, "eyes": eyes, "hair": hair, "outfit": outfit, "accessories": accessories,
                  "vibe": vibe}
    summary_text = (f"{age_band.replace('_', ' ', 1)} {role.lower()}, {hair['length']} {hair['color']} {hair['style']} hair, "
                    f"{eyes['color']} eyes, {archetype} outfit.")
    palette_id = rng.pick(list(palette_ids))
    brief = {"genres": [rng.pick(["lo-fi", "city-pop", "acoustic folk", "piano", "synthwave"])],
             "moods": [rng.pick(["hopeful", "calm", "playful", "confident"])], "bpm": rng.int(80, 124),
             "instruments": ["piano", rng.pick(["synth", "guitar", "bells"])], "vibe": f"{name}'s everyday theme"}
    return {"profile": profile, "attributes": attributes, "appearanceSummary": summary_text, "paletteId": palette_id,
            "advisory": advisory, "brief": brief}


def regenerate_field(profile: Mapping[str, Any], field: str, attempt: int) -> dict[str, Any]:
    rng = JsRng(f"field:{profile['name']}:{field}:{attempt}")
    if field == "tagline":
        return {"tagline": rng.pick(["Let's keep it honest.", "Bring snacks, bring questions.", "I'll tell you what I'd do.",
                                     "Slow is smooth, smooth is fast."])}
    if field == "greeting":
        return {"greeting": rng.pick(["Oh, hey! Good timing.", "There you are. Sit, talk.", "Hi again. What's the plan?"])}
    if field == "backstory":
        return {"backstory": f"{profile['name']} grew up somewhere small and loud, learned the job the hard way, and kept the "
                             "stories."}
    if field == "goals":
        return {"goals": rng.pick(["Finish one big project this year.", "Teach someone everything they know.",
                                   "Take a real holiday, finally."])}
    return {field: profile.get(field)} if field in profile else {}
