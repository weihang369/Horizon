"""Build the who-speaks sets: `who_first.jsonl`, `who_second.jsonl` and `who_scene.jsonl` (group-watch D23; doc 07
G11; evaluation-harness "M10 decision sets").

Run from backend/: `uv run python ../evals/datasets/who_speaks/build.py`. It is deterministic: the same tables give
the same files. Labels were written blind under `evals/reviews/m10-labels.md` (committed first), before any Jev answer.

Each item's state is built by the live code: the cast plan's state (`state_input` → `build_turn_plan_state`) for the
first slot and watch, and the follow plan's (`follow_state`) for the second slot. The recent lines come from the
committed frozen group transcripts (the two turns before a turn) or, for watch, the committed watch histories; the
user's line and the first reply are written for the item. `last_spoke` counts the character lines since each candidate
last spoke in that context, for the least-recently-spoken baseline.

The watch part (`who_scene`) is built from `evals/watch/*.json` once the histories exist (task 10.2); until then the
builder writes the two group files only.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from horizon.ai.agent.cast_plan import state_input  # noqa: E402
from horizon.ai.agent.follow_plan import follow_state  # noqa: E402
from horizon.ai.agent.plan_state import build_turn_plan_state  # noqa: E402
from horizon.ai.agent.planner import _name  # noqa: E402
from horizon.ai.contexts import (  # noqa: E402
    CastRequest,
    CharacterView,
    FollowRequest,
    MessageView,
    ParticipantView,
    SessionContext,
    WorldView,
)
from horizon.evals.datachecks import split_for  # noqa: E402

TRANSCRIPTS = ROOT / "evals" / "transcripts"
WATCH = ROOT / "evals" / "watch"
SEED = ROOT / "seed" / "characters"
USER = "Kai"
T0 = datetime(2026, 10, 3, 3, 0, tzinfo=UTC)
WHO = {"amara": "chr_seedAmara", "mei": "chr_seedMei", "victor": "chr_seedVictor",
       "hana": "chr_seedHana", "rin": "chr_seedRin", "takeshi": "chr_seedTakeshi"}
WORLDS = {"m": ("wld_seedMeridian", "Meridian", "long_group_meridian", ["amara", "mei", "victor"]),
          "s": ("wld_seedSunnyHollow", "Sunny Hollow", "long_group_sunnyhollow", ["hana", "rin", "takeshi"])}

# ── who_first: (world, context turn or None, the user's line, acceptable, lang) ──
FIRST: list[tuple[str, int | None, str, list[str], str]] = [
    # Meridian, English (25)
    ("m", 5, "Is it safe to take ibuprofen and paracetamol together for a bad back?", ["amara"], "en"),
    ("m", 9, "If we raise the minimum wage by 15%, what happens to youth hiring?", ["mei"], "en"),
    ("m", 13, "Can the state legally stop a protest outside parliament?", ["victor"], "en"),
    ("m", 17, "My landlord kept my whole deposit for 'wear and tear'. Do I have any recourse?", ["victor"], "en"),
    ("m", 21, "Is a four-day week actually cheaper for employers, or just a nice slogan?", ["mei"], "en"),
    ("m", 25, "I've had a headache for three days and paracetamol isn't touching it.", ["amara"], "en"),
    ("m", 31, "Victor, did you really argue a case barefoot once?", ["victor"], "en"),
    ("m", 35, "Amara, how do you stay calm on a night with five ambulances queued outside?", ["amara"], "en"),
    ("m", 39, "Mei, are you still betting inflation drops below 2% this year?", ["mei"], "en"),
    ("m", 43, "Should the council fund free clinics or tax rebates for small shops? Make your case.", ["amara", "mei"], "en"),
    ("m", 47, "Is a heatwave a public health emergency or an economic one?", ["amara", "mei"], "en"),
    ("m", 51, "Would a curfew for under-16s even survive a court challenge?", ["victor"], "en"),
    ("m", 55, "Unemployment fell last quarter but everyone I know is broke. How does that add up?", ["mei"], "en"),
    ("m", 59, "Measles cases are up at my kid's school. Should I panic?", ["amara"], "en"),
    ("m", 63, "Argue the other side for me: why shouldn't we ban cars from the city centre?", ["victor"], "en"),
    ("m", 67, "Give me a number: how many jobs would a new container port create?", ["mei"], "en"),
    ("m", 71, "I signed a contract without reading the non-compete clause. Am I stuck with it?", ["victor"], "en"),
    ("m", 75, "What's the evidence that taxing fizzy drinks actually changes anything?", ["amara", "mei"], "en"),
    ("m", 79, "Does working from home make people less productive or not?", ["mei"], "en"),
    ("m", 83, "My dad refuses to see a doctor about his chest pain. What do I say to him?", ["amara"], "en"),
    ("m", 87, "Can a council member be sued for something they said in a meeting?", ["victor"], "en"),
    ("m", 91, "Is it fair to make vaccination a condition of a council job?", ["victor", "amara"], "en"),
    ("m", 95, "Rent control: a fair deal for tenants or a slow disaster?", ["mei"], "en"),
    ("m", 6, "The new trauma ward needs money. Who actually has the legal power to decide that?", ["victor"], "en"),
    ("m", 10, "I can't sleep properly since I started night shifts. Any tips?", ["amara"], "en"),
    # Sunny Hollow, English (25)
    ("s", 5, "What flowers say 'sorry' without being too dramatic?", ["hana"], "en"),
    ("s", 9, "Any tips for the final boss in Hollow Knight? I've died forty times.", ["rin"], "en"),
    ("s", 13, "Why are trains always late the moment it rains?", ["takeshi"], "en"),
    ("s", 17, "Takeshi, go on, tell me another one of your terrible puns.", ["takeshi"], "en"),
    ("s", 21, "Rin, how's the game jam going? Did you sleep at all?", ["rin"], "en"),
    ("s", 25, "Hana, did the moonflowers finally open?", ["hana"], "en"),
    ("s", 29, "My orchid's leaves are going yellow. Is it dying on me?", ["hana"], "en"),
    ("s", 33, "How do I start making games if I've never written code?", ["rin"], "en"),
    ("s", 37, "What was the longest route you ever drove in one shift?", ["takeshi"], "en"),
    ("s", 41, "I need a bouquet for my mum's 60th and my budget is tiny.", ["hana"], "en"),
    ("s", 45, "Is a gaming PC worth it, or should I just get a console?", ["rin"], "en"),
    ("s", 49, "I have to be up at 5am tomorrow. Someone tell me it's survivable.", ["rin", "takeshi"], "en"),
    ("s", 53, "Who in this family is most likely to cry at a wedding?", ["hana", "takeshi"], "en"),
    ("s", 57, "What's the trick to keeping cut tulips fresh for a whole week?", ["hana"], "en"),
    ("s", 61, "Should I quit my job and try streaming full time?", ["rin"], "en"),
    ("s", 65, "How did your two girls turn out so different from each other?", ["takeshi"], "en"),
    ("s", 69, "Is the night train to Penang still running these days?", ["takeshi"], "en"),
    ("s", 73, "The shop window looks amazing today. Who arranged it?", ["hana"], "en"),
    ("s", 77, "Rin, your sister says you lost at Mario Kart to a nine-year-old.", ["rin"], "en"),
    ("s", 81, "What can I grow on a sunny balcony that's hard to kill?", ["hana"], "en"),
    ("s", 85, "Do you think AI will take game designers' jobs?", ["rin"], "en"),
    ("s", 89, "How do you manage to be on time every single day?", ["takeshi"], "en"),
    ("s", 93, "I forgot my sister's birthday. How do I fix this before tonight?", ["hana"], "en"),
    ("s", 97, "Speedrunning seems pointless to me. Convince me otherwise.", ["rin"], "en"),
    ("s", 6, "Did the old steam engines really need someone shovelling coal the whole way?", ["takeshi"], "en"),
    # Malay (5)
    ("m", 14, "Doktor, anak saya dah demam tiga hari. Perlu bawa ke hospital ke?", ["amara"], "ms"),
    ("m", 18, "Kalau gaji minimum naik, harga barang pun akan naik ke?", ["mei"], "ms"),
    ("s", 14, "Bunga apa yang sesuai untuk majlis tunang adik saya?", ["hana"], "ms"),
    ("s", 18, "Ada tak game yang best untuk main berdua dengan adik saya?", ["rin"], "ms"),
    ("s", 22, "Pakcik, betul ke kereta api dulu lebih tepat masa daripada sekarang?", ["takeshi"], "ms"),
    # Chinese (3)
    ("m", None, "房东不退押金，我可以告他吗？", ["victor"], "zh"),
    ("s", None, "这个周末适合送什么花给妈妈？", ["hana"], "zh"),
    ("m", None, "我胸口有点闷，需要去急诊吗？", ["amara"], "zh"),
    # mixed (2)
    ("s", 26, "Rin, your game ada bug lah, the save file hilang!", ["rin"], "mixed"),
    ("m", 30, "Mei, inflation ni bila nak turun ah? My groceries so expensive now.", ["mei"], "mixed"),
]

# ── who_second: (world, context turn or None, the user's line, first replier, first reply, acceptable ([] = none),
# lang) ──
SECOND: list[tuple[str, int | None, str, str, str, list[str], str]] = [
    # Meridian, English: none (28)
    ("m", 7, "Thanks, that really helps.", "amara", "Glad it helps. Drink some water and rest tonight.", [], "en"),
    ("m", 11, "What time does the council meeting start on Thursday?", "victor",
     "Nine sharp, in the old library. Bring the amended agenda.", [], "en"),
    ("m", 15, "Amara, is it okay to go for a run with a mild cold?", "amara",
     "If it's all above the neck, an easy run is fine. Fever or chest symptoms, rest.", [], "en"),
    ("m", 19, "Good night, all.", "mei", "Good night, Kai. Try not to dream about spreadsheets.", [], "en"),
    ("m", 23, "Mei, what's the unemployment rate right now?", "mei",
     "About 3.4 percent nationally, give or take a tenth depending on the survey.", [], "en"),
    ("m", 27, "My mum passed away last week.", "amara", "I'm so sorry, Kai. How are you holding up, honestly?", [], "en"),
    ("m", 32, "Victor, can I record a meeting without telling anyone?", "victor",
     "Not lawfully here, and certainly not wisely. Ask for consent on the record.", [], "en"),
    ("m", 36, "I finally finished the budget report!", "mei",
     "Congratulations. Did the numbers survive contact with reality?", [], "en"),
    ("m", 40, "Is the library open on Sundays?", "victor", "Only the reading room, ten until four.", [], "en"),
    ("m", 44, "Amara, thanks for the advice about my dad.", "amara",
     "Of course. Let me know how the appointment goes.", [], "en"),
    ("m", 48, "See you all tomorrow.", "victor", "Until tomorrow. Do try to sleep.", [], "en"),
    ("m", 52, "How long should I ice a sprained ankle?", "amara",
     "Twenty minutes at a time, a few times a day for the first two days.", [], "en"),
    ("m", 56, "Mei, can you send me that chart on wage growth?", "mei",
     "Sending it now. The second tab has the regional split.", [], "en"),
    ("m", 60, "Haha, okay, that was actually funny.", "victor", "I do try. Occasionally it lands.", [], "en"),
    ("m", 64, "I'm going to take a short break.", "amara", "Good idea. Stretch your legs while you're at it.", [], "en"),
    ("m", 68, "Victor, what's the deadline to appeal a parking fine?", "victor",
     "Twenty-one days from the notice. Keep a photo of the sign.", [], "en"),
    ("m", 72, "Is flu season starting early this year?", "amara",
     "It is. Cases are up in the clinics, so get the jab soon.", [], "en"),
    ("m", 76, "Got it, I'll book the GP for Monday.", "amara", "Good. Mention the dizziness specifically.", [], "en"),
    ("m", 80, "Mei, coffee or tea while we work through this?", "mei",
     "Coffee. Strong enough to have an opinion.", [], "en"),
    ("m", 84, "Okay, I'll draft the letter tonight.", "victor", "Keep it short. Facts first, adjectives never.", [], "en"),
    ("m", 88, "What's a good book on how the courts actually work?", "victor",
     "Start with Bingham's 'The Rule of Law'. Short, and clear as glass.", [], "en"),
    ("m", 92, "I passed my exam!", "amara", "Kai, that's brilliant. Celebrate properly tonight.", [], "en"),
    ("m", 96, "Can I take ibuprofen on an empty stomach?", "amara",
     "Better with food. It can irritate the stomach lining.", [], "en"),
    ("m", 4, "Mei, what did you have for lunch?", "mei", "Leftover laksa. Peak economics: zero marginal cost.", [], "en"),
    ("m", 8, "Thanks Victor, that clears it up.", "victor", "My pleasure. Precision is my only hobby.", [], "en"),
    ("m", 12, "Is it raining where you are?", "amara", "Pouring. The car park's become a lake.", [], "en"),
    ("m", 16, "Mei, you're wrong, rent control always lowers rents.", "mei",
     "For sitting tenants in the short run, yes. The supply effect comes later, and it bites.", [], "en"),
    ("m", 20, "Are free bus passes for students a good idea?", "mei",
     "Cheap to run, and attendance goes up a little. I'd do it.", [], "en"),
    # Meridian, English: someone (16)
    ("m", 24, "What do you two think about the four-day week vote?", "mei",
     "Productivity holds up in most trials, but the cost depends heavily on the sector.", ["amara", "victor"], "en"),
    ("m", 28, "Raising the wage floor will kill small shops, right?", "victor",
     "Legally the council can set it. Whether it should is another matter.", ["mei"], "en"),
    ("m", 33, "Everyone, quick round: what's this city's biggest problem?", "amara",
     "Clinic waiting times. People wait six hours for basic care.", ["mei", "victor"], "en"),
    ("m", 37, "Can the council force restaurants to post calorie counts on menus?", "victor",
     "It can, if the bylaw is proportionate and clearly drafted.", ["amara"], "en"),
    ("m", 41, "Night shifts are fine as long as you sleep eight hours, right?", "mei",
     "The pay premium for nights suggests otherwise: people need paying to do them.", ["amara"], "en"),
    ("m", 45, "Mei says the port will create ten thousand jobs. Victor, would the land deal hold up?", "mei",
     "Ten thousand is the optimistic end. I'd say six to eight.", ["victor"], "en"),
    ("m", 49, "Amara, Mei, which matters more for the city: hospitals or jobs?", "amara",
     "Hospitals. Nobody works if they're sick.", ["mei"], "en"),
    ("m", 53, "Honestly, precedent doesn't matter. Judges just do what they like.", "mei",
     "Courts are more predictable than markets, I'll give them that much.", ["victor"], "en"),
    ("m", 57, "Victor just said the drinks tax is unconstitutional. Is he right, Amara?", "victor",
     "I said it's vulnerable, not doomed. Words matter.", ["amara"], "en"),
    ("m", 61, "Unemployment benefits just make people lazy.", "amara",
     "Losing a job is one of the most stressful things that can happen to a person.", ["mei"], "en"),
    ("m", 65, "So who's right about the curfew, Victor or Mei?", "victor",
     "I am, naturally. A blanket curfew won't survive judicial review.", ["mei"], "en"),
    ("m", 69, "Should we ban phones in schools? I want all three views.", "mei",
     "The evidence on test scores is mixed but leans positive.", ["amara", "victor"], "en"),
    ("m", 73, "Victor, can the council legally close the night clinic?", "victor",
     "Yes, if it follows the consultation rules. Whether it's right is another debate.", ["amara"], "en"),
    ("m", 77, "Let's settle it: is the minimum wage a health issue too?", "mei",
     "Indirectly, through income. That's more Amara's turf than mine.", ["amara"], "en"),
    ("m", 81, "Can someone explain why my council tax went up?", "victor",
     "The levy changed in the last budget. Mei can tell you why it was needed.", ["mei"], "en"),
    ("m", 85, "Should vaccination be mandatory for nurses?", "victor",
     "Lawful if it's justified and proportionate, as the courts have held.", ["amara"], "en"),
    # Sunny Hollow, English: none (22)
    ("s", 7, "Thanks Hana, the bouquet was perfect.", "hana", "Yay! I'm so happy she liked it!", [], "en"),
    ("s", 11, "When are you opening up tomorrow, Hana?", "hana", "Nine! I'll have the kettle on.", [], "en"),
    ("s", 15, "Good night everyone.", "takeshi", "Good night. Train leaves at seven, don't be late.", [], "en"),
    ("s", 19, "Rin, did you finish the level?", "rin", "Finished it at 3am. Don't tell Dad.", [], "en"),
    ("s", 23, "Takeshi, what's your favourite train?", "takeshi",
     "The old Kiha 58. Rattled like a biscuit tin, ran like a clock.", [], "en"),
    ("s", 27, "Haha, okay, that pun was bad.", "takeshi", "Bad puns are my track record.", [], "en"),
    ("s", 31, "How often should I water a cactus?", "hana", "Every two or three weeks, and less in winter.", [], "en"),
    ("s", 35, "I'm heading out for groceries.", "hana", "Get the good strawberries if you see them!", [], "en"),
    ("s", 39, "Rin, which controller do you use?", "rin", "Pro controller. The cheap ones drift.", [], "en"),
    ("s", 43, "My cat knocked over a vase again.", "hana", "Oh no! Was it the blue one?", [], "en"),
    ("s", 47, "See you at dinner.", "takeshi", "Seven o'clock. Not seven-oh-five.", [], "en"),
    ("s", 51, "Hana, can I pick up the order on Friday?", "hana", "Of course! I'll keep it in the cool room.", [], "en"),
    ("s", 55, "I finally fixed my bike.", "takeshi", "Good work. Oil the chain once a month.", [], "en"),
    ("s", 59, "Rin, what's the game you're making called?", "rin", "Working title 'Lantern Moth'. It'll change.", [], "en"),
    ("s", 63, "Okay, I'm off to bed.", "rin", "Finally. Some of us have class at nine.", [], "en"),
    ("s", 67, "Are peonies in season yet?", "hana", "Just about! Another two weeks for the best ones.", [], "en"),
    ("s", 71, "Takeshi, thanks for the lift yesterday.", "takeshi",
     "Anytime. Departure and arrival, both on schedule.", [], "en"),
    ("s", 75, "It's so hot today.", "hana", "The flowers are wilting too! I've got every fan on.", [], "en"),
    ("s", 79, "Rin, can you send me the download link?", "rin", "Sent. Don't judge the menu screen.", [], "en"),
    ("s", 83, "What's for dinner tonight?", "takeshi", "Curry. Same as every Thursday, as it should be.", [], "en"),
    ("s", 87, "My exam went fine.", "hana", "I knew it would! So proud of you.", [], "en"),
    ("s", 91, "Rin, should I learn Unity or Godot?", "rin",
     "Godot. Free, light, and it won't change its pricing on you.", [], "en"),
    # Sunny Hollow, English: someone (12)
    ("s", 95, "What do you all think of my new haircut?", "hana",
     "It's so cute! The fringe really suits you.", ["rin", "takeshi"], "en"),
    ("s", 4, "Rin says trains are boring. Takeshi, defend yourself!", "rin",
     "They're boring. They go in a line.", ["takeshi"], "en"),
    ("s", 8, "Is it true bees die after stinging anything?", "rin",
     "Pretty sure, yeah. They just explode or something.", ["hana"], "en"),
    ("s", 12, "Family vote: pizza or ramen tonight?", "takeshi",
     "Ramen. Pizza is a delayed train of a meal.", ["hana", "rin"], "en"),
    ("s", 16, "Hana, does Rin ever water the plants when you're away?", "hana",
     "Um... she tries? There was the cactus incident.", ["rin"], "en"),
    ("s", 20, "Takeshi, is Rin's game any good?", "takeshi",
     "I don't understand it, but I'm proud of her.", ["rin"], "en"),
    ("s", 24, "Trains run faster when they're empty, right? Basic physics.", "hana",
     "Oh, I never thought about it! Maybe?", ["takeshi"], "en"),
    ("s", 28, "You can't overwater a fern, can you?", "rin", "No idea. Plants are Hana's thing.", ["hana"], "en"),
    ("s", 32, "I want everyone's opinion: should I adopt a second cat?", "hana",
     "Yes yes yes! Cats need friends!", ["rin", "takeshi"], "en"),
    ("s", 36, "Who's coming to the night market with me?", "rin", "Me, if there's takoyaki.", ["hana", "takeshi"], "en"),
    ("s", 40, "Takeshi, Hana told me you cried at the train museum.", "takeshi",
     "Dust. There was dust in the museum.", ["hana"], "en"),
    ("s", 44, "Is it bad to play games until 3am every night?", "takeshi",
     "Bad for punctuality, which is bad for everything.", ["rin"], "en"),
    # Malay (6)
    ("s", 48, "Terima kasih, Kak Hana!", "hana", "Sama-sama! Datang lagi ya!", [], "ms"),
    ("s", 52, "Pukul berapa kereta api terakhir ke Ipoh malam ni?", "takeshi", "Pukul sebelas malam. Jangan lambat.", [], "ms"),
    ("m", 58, "Doktor, boleh saya makan ubat ni dengan kopi?", "amara",
     "Boleh, tapi jangan minum kopi terlalu banyak sebab jantung boleh berdebar.", [], "ms"),
    ("m", 62, "Selamat malam semua.", "mei", "Selamat malam, Kai.", [], "ms"),
    ("m", 66, "Apa pendapat semua tentang cukai minuman manis?", "amara",
     "Dari segi kesihatan, ia membantu kurangkan minuman manis.", ["mei", "victor"], "ms"),
    ("s", 56, "Rin cakap kereta api tu selalu lambat. Betul ke, pakcik?", "rin",
     "Memang lambat. Saya tunggu sejam semalam.", ["takeshi"], "ms"),
    # Chinese (4)
    ("m", None, "谢谢你，这个建议很有用。", "amara", "不客气，好好休息。", [], "zh"),
    ("s", None, "花店明天几点开门？", "hana", "早上九点！", [], "zh"),
    ("m", None, "大家觉得最低工资应该涨吗？", "victor", "从法律上讲，议会有权调整。", ["mei"], "zh"),
    ("s", None, "晚安！", "takeshi", "晚安，明天七点准时。", [], "zh"),
    # mixed (2)
    ("m", 70, "Okay lah, thanks Victor, I'll file the appeal tomorrow.", "victor", "Good. Keep copies of everything.", [], "mixed"),
    ("s", 60, "Eh Rin, your dad says gaming rosakkan otak, betul ke?", "rin",
     "Dad also thinks the internet is a fad.", ["takeshi"], "mixed"),
]


def profiles() -> dict[str, dict[str, Any]]:
    return {cid: json.loads((SEED / f"{cid}.json").read_text(encoding="utf-8"))["data"]["profile"]
            for cid in WHO.values()}


def transcript(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((TRANSCRIPTS / f"{name}.json").read_text(encoding="utf-8"))
    return data


def context_lines(world: str, turn: int | None) -> list[tuple[str, str | None, str]]:
    """(author type, character id, text) of the two transcript turns before `turn`."""
    if turn is None:
        return []
    turns = transcript(WORLDS[world][2])["turns"]
    out: list[tuple[str, str | None, str]] = []
    for t in turns[max(0, turn - 2):turn]:
        out.append(("user", None, str(t["user"])))
        out += [("character", str(r["speaker"]), str(r["text"])) for r in t["replies"]]
    return out


def last_spoke(lines: list[tuple[str, str | None, str]], ids: list[str]) -> dict[str, int | None]:
    chars = [cid for kind, cid, _ in lines if kind == "character"]
    out: dict[str, int | None] = {}
    for cid in ids:
        idx = max((i for i, c in enumerate(chars) if c == cid), default=None)
        out[cid] = None if idx is None else len(chars) - 1 - idx
    return out


def session(world: str, lines: list[tuple[str, str | None, str]], prof: dict[str, dict[str, Any]]) -> SessionContext:
    wid, wname, _, cast = WORLDS[world]
    ids = [WHO[c] for c in cast]
    parts = [ParticipantView(character_id=cid, name=str(prof[cid]["name"]), role="speaker",
                             character_role=str(prof[cid].get("role") or ""), energy={"current": 500, "max": 1000})
             for cid in ids]
    recent = [MessageView(id=f"m{i}", seq=i + 1, author_type=kind, character_id=cid,
                          name=USER if kind == "user" else str(prof[str(cid)]["name"]), kind="chat", content=text)
              for i, (kind, cid, text) in enumerate(lines)]
    return SessionContext(session_id="ses_eval", seed="m10-eval", world=WorldView(id=wid, name=wname,
                                                                                  you={"displayName": USER}),
                          mode="group", title="eval", participants=parts, recent=recent)


def views(ids: list[str], prof: dict[str, dict[str, Any]]) -> list[CharacterView]:
    return [CharacterView(id=cid, name=str(prof[cid]["name"]), profile=prof[cid]) for cid in ids]


def values(ids: list[str], prof: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    return [{"key": cid, "name": str(prof[cid]["name"]), "role": str(prof[cid].get("role") or "")} for cid in ids]


def id_prefix(base: str, n: int, tests: int = 20) -> str:
    """The first of `base`, `base1`, `base2`, … whose hash split gives the part at least `tests` test items (D23's
    floor). The split depends on the id alone, never on a label or an answer, so this choice can't favour either."""
    k = 0
    while True:
        pre = base if k == 0 else f"{base}{k}"
        if sum(split_for(f"{pre}-{i:03d}") == "test" for i in range(1, n + 1)) >= tests:
            return pre
        k += 1


def source(world: str, turn: int | None) -> str:
    return f"transcript:{WORLDS[world][2]}#{turn} (written line)" if turn is not None else "written"


def build_first(prof: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    pre = id_prefix("whf", len(FIRST))
    for n, (world, turn, line, ok, lang) in enumerate(FIRST, 1):
        ids = [WHO[c] for c in WORLDS[world][3]]
        ctx = context_lines(world, turn)
        since = last_spoke(ctx, ids)
        sctx = session(world, [*ctx, ("user", None, line)], prof)
        req = CastRequest(session=sctx, kind="group_first", candidates=ids, cast=views(ids, prof), latest=line,
                          base_faces=dict.fromkeys(ids, "neutral"), turns_since=since, started_at=T0)
        state = build_turn_plan_state(state_input(req)).state
        item_id = f"{pre}-{n:03d}"
        rows.append({"id": item_id, "question_id": "who_first", "split": split_for(item_id), "lang": lang,
                     "kind": "group", "item": {"state": state, "values": values(ids, prof), "seed": f"m10-who:{n}",
                                               "none": False},
                     "label": {"candidates": ids, "acceptable": [WHO[c] for c in ok], "none_ok": False,
                               "last_spoke": since},
                     "source": source(world, turn)})
    return rows


def second_request(row: tuple[str, int | None, str, str, str, list[str], str],
                   prof: dict[str, dict[str, Any]]) -> FollowRequest:
    """The live follow plan's request for one second-slot item (the latency suite's follow part rebuilds it to time
    the state assembly, D9)."""
    world, turn, line, first, reply, _, _ = row
    cast = [WHO[c] for c in WORLDS[world][3]]
    fid = WHO[first]
    cands = [c for c in cast if c != fid]
    ctx = [*context_lines(world, turn), ("user", None, line), ("character", fid, reply)]
    return FollowRequest(session=session(world, ctx, prof), first_id=fid, first_name=str(prof[fid]["name"]),
                         first_message_id="m_first", first_text=reply, message=line, candidates=cands,
                         cast=views(cands, prof), base_faces=dict.fromkeys(cands, "neutral"),
                         turns_since=last_spoke(ctx, cands), started_at=T0)


def second_requests() -> list[tuple[str, str, FollowRequest]]:
    """(item id, split, request) for every second-slot item."""
    prof = profiles()
    pre = id_prefix("whs", len(SECOND))
    return [(f"{pre}-{n:03d}", split_for(f"{pre}-{n:03d}"), second_request(row, prof))
            for n, row in enumerate(SECOND, 1)]


def build_second(prof: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    pre = id_prefix("whs", len(SECOND))
    for n, row in enumerate(SECOND, 1):
        world, turn, line, first, reply, ok, lang = row
        fid = WHO[first]
        req = second_request(row, prof)
        cands, since = req.candidates, req.turns_since
        state = follow_state(req).state
        item_id = f"{pre}-{n:03d}"
        rows.append({"id": item_id, "question_id": "who_second", "split": split_for(item_id), "lang": lang,
                     "kind": "group", "item": {"state": state, "values": values(cands, prof), "seed": f"m10-who2:{n}",
                                               "name": _name(str(prof[fid]["name"]))},
                     "label": {"candidates": cands, "acceptable": [WHO[c] for c in ok], "none_ok": not ok,
                               "last_spoke": since},
                     "source": source(world, turn)})
    return rows


def check(first: list[dict[str, Any]], second: list[dict[str, Any]]) -> list[str]:
    """D23's counts and splits (m10-labels.md)."""
    problems = []
    if Counter(r["lang"] for r in first) != Counter({"en": 50, "ms": 5, "zh": 3, "mixed": 2}):
        problems.append(f"who_first languages {dict(Counter(r['lang'] for r in first))}")
    if len(second) != 90 or Counter(r["lang"] for r in second)["en"] != 78:
        problems.append(f"who_second: {len(second)} items, {Counter(r['lang'] for r in second)}")
    nones = sum(r["label"]["none_ok"] for r in second)
    if not 0.60 <= nones / len(second) <= 0.70:
        problems.append(f"who_second: {nones} none items of {len(second)} (rule: about 65 %)")
    for rows in (first, second):
        for r in rows:
            lab = r["label"]
            if not lab["none_ok"] and not 1 <= len(lab["acceptable"]) <= 2:
                problems.append(f"{r['id']}: {len(lab['acceptable'])} acceptable (rule: 1 or 2)")
            if any(a not in lab["candidates"] for a in lab["acceptable"]):
                problems.append(f"{r['id']}: an acceptable answer isn't a candidate")
        tests = sum(1 for r in rows if r["split"] == "test")
        if tests < 20:
            problems.append(f"{rows[0]['question_id']}: {tests} test items (rule: at least 20)")
    return problems


def write(name: str, rows: list[dict[str, Any]]) -> None:
    (HERE / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8",
                             newline="\n")


def main() -> int:
    prof = profiles()
    first, second = build_first(prof), build_second(prof)
    problems = check(first, second)
    if problems:
        print("\n".join(problems))
        return 1
    write("who_first.jsonl", first)
    write("who_second.jsonl", second)
    for rows in (first, second):
        print(f"wrote {len(rows)} {rows[0]['question_id']} items: splits {dict(Counter(r['split'] for r in rows))}, "
              f"languages {dict(Counter(r['lang'] for r in rows))}")
    print(f"who_second: {sum(r['label']['none_ok'] for r in second)} none items")
    if (WATCH / "meridian_long.json").is_file():
        from scene import build_scene, write_scene   # the watch part, once the histories exist (task 10.2)

        write_scene(build_scene(prof))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
