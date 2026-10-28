"""Build M12's three gate sets (rag design D22; doc 02 B2, B5; evaluation-harness "The gate sets"):
- `evals/datasets/docs/docs.jsonl`: "needs documents?" about one candidate, asked under its live key `docs:{id}`;
- `evals/datasets/standalone/standalone.jsonl`: "standalone?" about the latest message;
- `evals/datasets/english/english.jsonl`: "English?" about the latest message.

Run from backend/: `uv run python ../evals/datasets/docs/build.py`. Deterministic. Labels were written blind under
`evals/reviews/m12-labels.md` (committed first), before any Jev answer.

Every state is built by the live code, with each candidate's real searchable seed titles (`m12_sets.seed_titles`,
the live title read):
- **1:1:** the turn plan's state (`plan_state_input` → `build_turn_plan_state`) for a reply;
- **group:** the cast plan's state for the first slot (`state_input`, `group_first`);
- **watch:** the cast plan's state for a scene turn (`scene`, the premise, the line being answered as "Name: line");
- **debate:** the debate plan's state at a committed history's slot (`debate_suites.cut_request` / `cut_state`), the
  members' titles added as live adds them.
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
from horizon.ai.agent.plan_state import build_turn_plan_state  # noqa: E402
from horizon.ai.agent.planner import _name, plan_state_input  # noqa: E402
from horizon.ai.contexts import (  # noqa: E402
    CastRequest,
    CharacterView,
    MessageView,
    ParticipantView,
    PlanRequest,
    SessionContext,
    WorldView,
)
from horizon.evals import debate_suites as ds  # noqa: E402
from horizon.evals.datachecks import split_for  # noqa: E402
from horizon.evals.m12_sets import seed_titles  # noqa: E402

DATASETS = ROOT / "evals" / "datasets"
TRANSCRIPTS = ROOT / "evals" / "transcripts"
# the seed the sets were labelled on (evals/README.md), so a shipped-seed edit never moves a built set (v1.1)
SEED = ROOT / "evals" / "seed-v0" / "characters"
USER = "Kai"
T0 = datetime(2026, 10, 15, 3, 0, tzinfo=UTC)
WHO = {"amara": "chr_seedAmara", "mei": "chr_seedMei", "victor": "chr_seedVictor",
       "hana": "chr_seedHana", "rin": "chr_seedRin", "takeshi": "chr_seedTakeshi"}
WORLDS = {"m": ("wld_seedMeridian", "Meridian", ["amara", "mei", "victor"]),
          "s": ("wld_seedSunnyHollow", "Sunny Hollow", ["hana", "rin", "takeshi"])}
WORLD_OF = {c: w for w, (_, _, cast) in WORLDS.items() for c in cast}

Line = tuple[str, str]   # (speaker short name or "you", text)

# ══ "needs documents?" ══
# 1:1: (character, earlier lines, the message, label, lang, source)
ONE: list[tuple[str, list[Line], str, str, str, str]] = [
    # Amara (Meridian Shift Fatigue Review 2025; ED triage guidelines)
    ("amara", [], "What did your fatigue review find about people working long shifts back to back?", "yes", "en",
     "written"),
    ("amara", [], "How many of the ED staff were burnt out by the end of the review?", "yes", "en", "written"),
    ("amara", [("you", "I keep reading about compressed rotas."), ("amara", "They're having a moment, yes.")],
     "Did your pilot wards need extra agency staff to make it work?", "yes", "en", "written"),
    ("amara", [], "When should a headache be seen by a doctor the same day?", "yes", "en", "written"),
    ("amara", [], "My head's been pounding since I cut out coffee. Is that something triage would worry about?", "yes",
     "en", "written"),
    ("amara", [], "What did the review end up recommending to the Trust board?", "yes", "en", "written"),
    ("amara", [], "Did sleep problems show up much in your review?", "yes", "en", "written"),
    ("amara", [], "Did the review find more near-miss medication errors after short sleep?", "yes", "en", "written"),
    ("amara", [], "Apa yang kajian keletihan awak jumpa tentang tidur sebelum syif?", "yes", "ms", "written"),
    ("amara", [], "你们的疲劳报告里护士的辞职率是多少？", "yes", "zh", "written"),
    ("amara", [], "Eh Amara, that fatigue review tu, berapa ramai staff yang dia cover?", "yes", "mixed", "written"),
    ("amara", [], "What did you have for lunch?", "no", "en", "transcript:long_one_on_one_en#0"),
    ("amara", [], "My dog is called Pepper, a grey whippet.", "no", "en", "transcript:long_one_on_one_en#8"),
    ("amara", [], "Long day. How's yours going?", "no", "en", "transcript:long_one_on_one_en#52"),
    ("amara", [], "I'm moving to Kuching in March for work.", "no", "en", "transcript:long_one_on_one_en#9"),
    ("amara", [], "What's the best way to get a coffee stain out of a white shirt?", "no", "en", "written (outside)"),
    ("amara", [("you", "Three nights in a row this week."), ("amara", "Oof. How are you holding up?")],
     "Drained. I just needed to say it out loud to someone.", "no", "en", "written (a feeling about shifts)"),
    ("amara", [], "你周末一般喜欢做什么？", "no", "zh", "written"),
    # Hana (Grandma's recipe notebook)
    ("hana", [], "What did your grandma put in her rainy-day soup?", "yes", "en", "written"),
    ("hana", [], "How did your grandma make sushi rice when the whole family came over?", "yes", "en", "written"),
    ("hana", [("you", "I made way too much rice again."), ("hana", "Oh no, the classic!")],
     "Is there a trick in your grandma's notebook for leftover rice?", "yes", "en", "written"),
    ("hana", [], "Does your grandma's yuzu cake put the juice in the batter or somewhere else?", "yes", "en", "written"),
    ("hana", [], "Nenek awak buat sup hari hujan tu macam mana?", "yes", "ms", "written"),
    ("hana", [], "你奶奶的柚子蛋糕是怎么做的？", "yes", "zh", "written"),
    ("hana", [], "Awak buat apa bila tak boleh tidur?", "no", "ms", "transcript:long_one_on_one_ms#18"),
    ("hana", [], "Awak ada bau kegemaran tak?", "no", "ms", "transcript:long_one_on_one_ms#5"),
    ("hana", [], "Penat hari ni. Awak macam mana?", "no", "ms", "transcript:long_one_on_one_ms#34"),
    ("hana", [], "How much should I charge for a wedding bouquet?", "no", "en", "written (outside)"),
    ("hana", [], "I miss my grandma too, you know.", "no", "en", "written (a feeling)"),
    ("hana", [], "Bunga apa yang paling tahan lama dalam pasu?", "no", "ms", "written (outside)"),
    # Mei (Four-day week pilot summaries)
    ("mei", [], "Did the four-day week pilots actually cut burnout?", "yes", "en", "written"),
    ("mei", [], "How many of the firms kept the four-day week once the trial ended?", "yes", "en", "written"),
    ("mei", [], "Were any hospitals part of those pilots?", "yes", "en", "written"),
    ("mei", [], "What happened to sick days in the pilots?", "yes", "en", "written"),
    ("mei", [("you", "Shift work is my worry with all this."), ("mei", "It should be. It's the hard case.")],
     "How did the shift-based companies keep their cover?", "yes", "en", "written"),
    ("mei", [], "Why should I be careful with that 92 percent figure?", "yes", "en", "written"),
    ("mei", [], "Which sectors were most of the pilot firms in?", "yes", "en", "written"),
    ("mei", [], "Did revenue hold up in the pilots?", "yes", "en", "written"),
    ("mei", [], "Berapa ramai pekerja yang terlibat dalam perintis minggu empat hari tu?", "yes", "ms", "written"),
    ("mei", [], "Mei, the pilot summaries tu ada cakap pasal overtime tak?", "yes", "mixed", "written"),
    ("mei", [], "What's your bet on inflation next quarter?", "no", "en", "written (her field, outside)"),
    ("mei", [], "Does raising the minimum wage kill jobs for teenagers?", "no", "en", "written (her field, outside)"),
    ("mei", [], "I tried a new running route this morning.", "no", "en", "written"),
    ("mei", [], "Honestly I'm just fed up with my boss today.", "no", "en", "written (a feeling)"),
    ("mei", [], "你最近在看什么电影？", "no", "zh", "written"),
    # Victor (Moot court notes)
    ("victor", [], "What's in your moot notes about the old Working Hours Act?", "yes", "en", "written"),
    ("victor", [], "How are you planning to close the moot?", "yes", "en", "written"),
    ("victor", [], "If the other side says the evidence is too thin, what's our line?", "yes", "en", "written"),
    ("victor", [], "Is there a precedent for phasing a change in sector by sector?", "yes", "en", "written"),
    ("victor", [], "Which rules already cover hospitals and other round-the-clock services?", "yes", "en", "written"),
    ("victor", [], "What did your notes say about conceding scope?", "yes", "en", "written"),
    ("victor", [], "Apa nota awak cakap tentang Akta Waktu Bekerja 1931?", "yes", "ms", "written"),
    ("victor", [], "你的模拟法庭笔记里，对方说“速度而不是方向”时我们怎么回应？", "yes", "zh", "written"),
    ("victor", [], "My landlord kept my whole deposit. Can I take him to court?", "no", "en",
     "written (his field, outside)"),
    ("victor", [], "Can the police search my car without a warrant?", "no", "en", "written (his field, outside)"),
    ("victor", [], "Did you really argue a case barefoot once?", "no", "en", "written"),
    ("victor", [], "Wish me luck, my interview's tomorrow!", "no", "en", "written"),
    ("victor", [], "The trains were late again.", "no", "en", "written"),
    ("victor", [], "Victor, you free tonight? Jom makan dulu lepas kerja.", "no", "mixed", "written"),
    ("victor", [], "Do you like the rain?", "no", "en", "written"),
]

# group: (world, earlier lines, the user's line, {candidate: label}, lang, source)
GROUP: list[tuple[str, list[Line], str, dict[str, str], str, str]] = [
    ("m", [], "Before the council vote, what did the four-day week pilots find about burnout?",
     {"mei": "yes", "victor": "no"}, "en", "written"),
    ("m", [], "How quickly should a headache be seen in the ED if it came on suddenly?",
     {"amara": "yes", "mei": "no"}, "en", "written"),
    ("m", [], "If we argue for a four-day week at the moot, how do we handle the 'not this fast' line?",
     {"victor": "yes", "amara": "no"}, "en", "written"),
    ("m", [], "What's everyone doing this weekend?", {"amara": "no", "mei": "no"}, "en", "written"),
    ("m", [], "Long day. How's yours going?", {"victor": "no", "mei": "no"}, "en",
     "transcript:long_group_meridian#1"),
    ("m", [], "Do nurses who sleep badly before a shift make more medication errors?",
     {"amara": "yes", "victor": "no"}, "en", "written"),
    ("m", [], "Did any of the four-day week pilots include bus companies?", {"mei": "yes", "amara": "no"}, "en",
     "written"),
    ("m", [], "When was the two-day weekend made the default here?", {"victor": "yes", "mei": "no"}, "en", "written"),
    ("m", [], "How many nurses resigned at the Trust last year?", {"amara": "yes", "mei": "no"}, "en", "written"),
    ("m", [], "Can the council phase a four-day week in for contractors, or would a court strike it down?",
     {"victor": "yes", "mei": "no"}, "en", "written"),
    ("m", [], "Apa yang perintis minggu empat hari jumpa tentang peletakan jawatan?",
     {"mei": "yes"}, "ms", "written"),
    ("m", [], "急诊分诊是怎么分级的？", {"amara": "yes"}, "zh", "written"),
    ("m", [], "Guys, quick one, the fatigue review tu cakap apa pasal rest days?", {"amara": "yes"}, "mixed",
     "written"),
    ("m", [], "What share of the pilot firms stuck with the four-day week?", {"mei": "yes", "amara": "no"}, "en",
     "written"),
    ("m", [], "Is a sugar tax a good idea or not?", {"mei": "no", "amara": "no"}, "en", "written (opinion)"),
    ("s", [], "Hana, how did your grandma make her miso soup?", {"hana": "yes"}, "en", "written"),
    ("s", [], "What did your grandmother do with leftover rice?", {"hana": "yes"}, "en", "written"),
    ("s", [], "I'm saving for a secondhand motorbike.", {"hana": "no"}, "en", "transcript:long_group_sunnyhollow#6"),
    ("s", [], "The trains were late again.", {"hana": "no"}, "en", "transcript:long_group_sunnyhollow#77"),
    ("s", [], "Nenek Hana ada simpan resipi kek yuzu tak?", {"hana": "yes"}, "ms", "written"),
    ("s", [], "Rin, how's the game launch going?", {"hana": "no"}, "en", "written"),
]

# watch: (world, premise, lines before, the line answered, {candidate: label}, source)
INQUIRY = ("A week after a heatwave filled the hospital, Amara, Mei and Victor prepare the town's public inquiry.")
BRIEFING = "Mei and Victor prepare the council's four-day week briefing over coffee, with Amara late from a shift."
POWERCUT = "Three old friends wait out a power cut in a hospital cafeteria."
PARTY = "The family secretly plans Takeshi's retirement party in the kitchen."
STORM = "A storm traps the family in the flower shop overnight."
WATCH: list[tuple[str, str, list[Line], Line, dict[str, str], str]] = [
    ("m", INQUIRY, [("victor", "We need an order of witnesses by Friday.")],
     ("mei", "Amara, how stretched were your emergency staff that week?"), {"amara": "yes", "victor": "no"},
     "written (watch)"),
    ("m", BRIEFING, [("amara", "Sorry, sorry. Handover ran long.")],
     ("victor", "Mei, what did the pilots show for organisations that run shifts?"), {"mei": "yes", "amara": "no"},
     "written (watch)"),
    ("m", POWERCUT, [("mei", "At least the vending machine still works.")],
     ("amara", "Victor, you never told us how the moot went. What was your closing going to be?"),
     {"victor": "yes", "mei": "no"}, "written (watch)"),
    ("s", PARTY, [("takeshi", "Is he asleep? Good.")],
     ("rin", "Hana, didn't Grandma have a cake everyone loved? What was her trick?"), {"hana": "yes"},
     "written (watch)"),
    ("s", STORM, [("hana", "The roses are going to be so confused.")],
     ("takeshi", "Who's hungry? We've got rice and miso and some sad spinach, nothing else."), {"hana": "yes"},
     "written (watch)"),
    ("s", STORM, [("takeshi", "Back in my day we'd sleep on the platform benches.")],
     ("rin", "My phone's at four percent. This is the worst night of my life."), {"hana": "no"}, "written (watch)"),
    ("m", INQUIRY, [("amara", "The admissions data is clean, at least.")],
     ("victor", "Mei, the inquiry wants a figure: what did the closed factories cost the town?"),
     {"mei": "no", "amara": "no"}, "written (watch; outside)"),
]

# debate: (history, slot seq, {member: label}). The line answered is the slot's latest argument. Only members whose
# titles survive X9's cap are labelled: late in the panel and three-a-side debates (d13#7, d13#12, d09#8, d09#9) the
# 2,000-token cap drops every gate, so live never asks there (recorded in m12.md).
DEBATE: list[tuple[str, int, dict[str, str]]] = [
    ("d03", 7, {"mei": "yes"}),                         # Sofia's service map: wards, depots, control rooms
    ("d03", 8, {"victor": "yes"}),                      # Mei: "pilot it in the back office", define the week
    ("d03", 12, {"mei": "yes"}),                        # Sofia: Mei's back-office pilot, Daniel pricing burnout
    ("d03", 13, {"victor": "yes"}),                     # Mei: a funded rota, a pilot
    ("d13", 8, {"mei": "yes"}),                         # Amara: staffing is binding (Victor's gate dropped by X9)
    ("d13", 9, {"victor": "no"}),                       # Mei: the shift-based staffing analogue
    ("d13", 13, {"mei": "yes", "victor": "no"}),        # Amara: converged on staffing and the windfall
    ("d09", 10, {"mei": "no"}),                         # compulsory voting
    ("d01", 7, {"amara": "no"}),                        # private cars
    ("d01", 8, {"victor": "no"}),
    ("d01", 10, {"mei": "no"}),
    ("d04", 7, {"amara": "no"}),                        # sugary drinks tax
    ("d04", 9, {"mei": "no"}),
    ("d08", 7, {"hana": "no"}),                         # school meals from local farms
    ("d06", 7, {"hana": "no"}),                         # high street closed to cars
    ("d11", 9, {"amara": "no"}),                        # homework
]

# ══ "standalone?": (character, the user's earlier line, the character's reply, follow-up, standalone) ══
# Each context gives one follow-up (label no) and one message that stands alone (label yes).
STANDALONE: list[tuple[str, str, str, str, str]] = [
    ("amara", "I did three nights in a row this week.", "That's a tough block. How are you sleeping?",
     "Badly. How long until that settles?", "How long does it take to recover from three night shifts in a row?"),
    ("amara", "My partner quit coffee on Monday.", "Brave. Any headaches yet?",
     "Yes, a dull one. Is that normal?", "Is a dull headache normal a few days after quitting coffee?"),
    ("amara", "Our ward is trialling a compressed rota.", "Four long days, then three off?",
     "That's the one. Did yours help?", "Did the compressed rota in your fatigue review lower burnout?"),
    ("amara", "I read your fatigue review last night.", "Ah, the cheerful reading.",
     "Which department came out worst?", "Which department had the worst burnout in the Meridian fatigue review?"),
    ("amara", "A patient came in with a thunderclap headache.", "Those get escalated straight away.",
     "Even if the obs look fine?", "Should a sudden severe headache be escalated even when the observations are normal?"),
    ("amara", "My mum gets headaches that wake her up at night.", "That's worth taking seriously.",
     "Same day, or can it wait?", "Should a headache that wakes someone from sleep be seen the same day?"),
    ("amara", "I'm doing twelve-hour shifts now.", "How many in a row?",
     "Four. Too many?", "Are four twelve-hour shifts in a row too many?"),
    ("amara", "The Trust is cancelling rest days again.", "That came up a lot in the review.",
     "What did it say about it?", "What did the fatigue review say about cancelled rest days?"),
    ("amara", "We lost three nurses this quarter.", "Do you know why they left?",
     "Workload mostly. Is that typical?", "Is workload the most common reason nurses give for leaving?"),
    ("amara", "I keep nodding off on the drive home.", "That's genuinely dangerous.",
     "What should I do instead?", "What should a nurse do if she keeps nodding off driving home after nights?"),
    ("amara", "Triage grades go from one to five, right?", "Yes, one is immediate.",
     "And five?", "What does triage grade five mean?"),
    ("amara", "I gave a patient advice over the phone today.", "Did you tell them it wasn't an examination?",
     "Should I have?", "Do the triage guidelines require phone advice to say it is not an examination?"),
    ("amara", "Agency costs went up during our rota change.", "Ours did too, at first.",
     "For how long?", "How long did agency costs stay high after the compressed rota started?"),
    ("hana", "I'm baking a yuzu cake this weekend.", "Oh, Grandma's favourite!",
     "Where does the juice go?", "Where does the juice go in Grandma's yuzu cake?"),
    ("hana", "I'm making sushi rice for twelve people.", "A crowd! Fun!",
     "How much vinegar, then?", "How much vinegar should I use for sushi rice for a crowd?"),
    ("hana", "My niece won't eat her soup.", "Oh no, what kind?",
     "Miso. Any tricks?", "How do I get a child to eat miso soup?"),
    ("hana", "There's so much rice left from dinner.", "Don't throw it away!",
     "What should I make with it?", "What can I make tomorrow with leftover rice?"),
    ("hana", "I'm setting the table for the party.", "Ooh, flowers?",
     "Yes, how tall can they be?", "How tall should flowers on a dinner table be?"),
    ("hana", "I'm shaping onigiri for the picnic.", "Wet hands, right?",
     "And salt, where does that go?", "Should I salt my hands or the rice when shaping onigiri?"),
    ("hana", "Grandma's notebook has a soup for rainy days.", "The dragon broth!",
     "What's in it again?", "What goes into Grandma's rainy-day soup?"),
    ("hana", "The yuzu zest smells amazing already.", "Did you rub it into the sugar?",
     "Should I have?", "Should yuzu zest be rubbed into the sugar for the cake?"),
    ("hana", "The fish for tonight is really rich.", "Then brighten the rice!",
     "With what?", "What keeps sushi rice bright when the fish is rich?"),
    ("hana", "My kid calls Grandma's soup dragon broth.", "That's exactly what she called it!",
     "Why that name?", "Why did Grandma call her rainy-day soup dragon broth?"),
    ("hana", "Grandpa loved the sushi rice at New Year.", "He never guessed the secret!",
     "What was it?", "What was the secret ingredient in Grandma's sushi rice?"),
    ("mei", "I've been reading about the four-day week pilots.", "The compendium? Good.",
     "How big were they?", "How many organisations took part in the four-day week pilots?"),
    ("mei", "Burnout fell in the pilots, apparently.", "On average, yes.",
     "By how much?", "By how much did burnout fall in the four-day week pilots?"),
    ("mei", "My hospital wants to try a four-day week.", "Then read the gap section.",
     "Why that part?", "Did any of the four-day week pilots include an acute hospital?"),
    ("mei", "Ninety-two percent kept it, that's huge.", "Huge, but read the caveat.",
     "Which caveat?", "Why do the pilot authors warn against reading the 92% as a national estimate?"),
    ("mei", "Shift-based firms struggled with cover.", "They needed more hours.",
     "How many more?", "How many more staffed hours did shift-based pilot firms need?"),
    ("mei", "The best firms redesigned before the trial.", "Meetings, mostly.",
     "And the others?", "What happened at pilot firms that cut a day without redesigning work?"),
    ("mei", "Survey response dropped near the end.", "It always does.",
     "From what to what?", "How far did survey response fall in the four-day week pilots?"),
    ("mei", "Resignations went down in most pilots.", "On average, yes.",
     "To what?", "What was the average resignation rate by the end of the four-day week pilots?"),
    ("mei", "What do the authors recommend next?", "Sector trials, mostly.",
     "In which sectors?", "Which sectors do the pilot authors want trialled before a national standard?"),
    ("mei", "Revenue stayed flat in the pilots.", "Broadly, yes.",
     "And output?", "Did the four-day week pilots measure output consistently?"),
    ("mei", "Most firms were in professional services.", "Seventy-one percent.",
     "And the rest?", "How many of the four-day week pilot organisations ran shift-based services?"),
    ("mei", "Sick days fell too, I heard.", "They did.",
     "By the same amount?", "By how much did sick days fall in the four-day week pilots?"),
    ("mei", "The pilots ran in Meridian, right?", "Between 2023 and 2025.",
     "All volunteers?", "Did every organisation in the four-day week pilots volunteer?"),
    ("victor", "The other side will say the evidence is thin.", "They always do.",
     "How do we answer it?", "How should we answer the claim that the four-day week evidence base is narrow?"),
    ("victor", "I'm drafting the closing for Thursday.", "Keep it gracious.",
     "Any lines to use?", "What closing lines do the moot court notes suggest?"),
    ("victor", "They'll argue about speed, not the goal.", "Then they've conceded the goal.",
     "What then?", "What happens in the debate once the opposition accepts the goal?"),
    ("victor", "We need a historical anchor.", "The 1931 Act is perfect.",
     "What did it do?", "What did the Meridian Working Hours Act 1931 do?"),
    ("victor", "Hospitals can't just close on Fridays.", "They already run on shift rules.",
     "Under what?", "Which part of the Working Time Code covers continuous-coverage sectors?"),
    ("victor", "Can we phase it in?", "There's precedent for that.",
     "What kind?", "What phase-in precedent do the moot notes give?"),
    ("victor", "The 1931 Act exempted some sectors.", "Continuous services, yes.",
     "And farming?", "How long a transition did the 1931 Act give agriculture?"),
    ("victor", "Judges in the last moot liked concessions.", "They reward grace.",
     "Even in the closing?", "Should a moot closing concede a fair point gracefully?"),
    ("victor", "They'll say the status quo is neutral.", "It isn't.",
     "Why not?", "Why isn't the status quo neutral in the four-day week debate?"),
    ("victor", "Collective agreements come first, you said.", "In a phase-in, yes.",
     "And who leads?", "Who should act as model employer in a phased four-day week?"),
    ("victor", "Courts have upheld staged duties before.", "Where the end point is clear.",
     "Only then?", "Do courts uphold staged duties only when the end point is clear?"),
    ("victor", "Res ipsa loquitur for the close?", "One of two options.",
     "What's the other?", "What closing options do the moot court notes list?"),
    ("victor", "I'm worried we sound triumphant.", "So am I, a little.",
     "How do we avoid it?", "How do we avoid sounding triumphant in a moot closing?"),
]

# ══ "English?": (character, the message, lang); English is yes, every other language no ══
ENGLISH: list[tuple[str, str, str]] = [
    ("amara", "Is it okay to have roti canai right before a night shift?", "en"),
    ("amara", "My sister Leila works nights in Ipoh. Any advice for her?", "en"),
    ("hana", "Can I use calamansi instead of yuzu in the glaze?", "en"),
    ("hana", "My nenek always said to salt your hands for onigiri. Is that true?", "en"),
    ("mei", "Did the pilots include any firms in Kuala Lumpur?", "en"),
    ("mei", "How did the four-day week change sick days?", "en"),
    ("victor", "What's the Working Hours Act's transition period again?", "en"),
    ("victor", "Is 'speed, not direction' a fair summary of their case?", "en"),
    ("amara", "The Shinkansen trip home wiped me out. How long should I rest?", "en"),
    ("hana", "Which flowers go well with a bowl of ramen on the table?", "en"),
    ("amara", "Berapa lama saya patut rehat selepas tiga syif dua belas jam?", "ms"),
    ("amara", "Sakit kepala saya datang tiba-tiba dan sangat teruk. Perlu ke hospital?", "ms"),
    ("hana", "Nenek awak letak jus yuzu dalam adunan ke?", "ms"),
    ("hana", "Macam mana nak buat nasi sushi untuk ramai orang?", "ms"),
    ("mei", "Berapa banyak syarikat kekalkan minggu kerja empat hari?", "ms"),
    ("mei", "Adakah cuti sakit berkurang semasa perintis itu?", "ms"),
    ("victor", "Apakah duluan untuk melaksanakan perubahan secara berperingkat?", "ms"),
    ("victor", "Bagaimana kita jawab kalau mereka kata bukti terlalu sedikit?", "ms"),
    ("amara", "Kajian awak liputi berapa ramai kakitangan klinikal?", "ms"),
    ("hana", "Kenapa nenek panggil sup itu sup naga?", "ms"),
    ("amara", "连续上三个夜班之后要休息多久？", "zh"),
    ("amara", "突然剧烈的头痛需要马上看医生吗？", "zh"),
    ("hana", "柚子汁应该放在面糊里还是糖霜里？", "zh"),
    ("hana", "剩饭第二天可以做什么？", "zh"),
    ("mei", "四天工作制试点里倦怠下降了多少？", "zh"),
    ("mei", "有没有医院参加了那些试点？", "zh"),
    ("victor", "1931年的工时法规定了什么？", "zh"),
    ("victor", "模拟法庭的结辩应该怎么收尾？", "zh"),
    ("mei", "试点的调查回复率最后降到多少？", "zh"),
    ("amara", "分诊等级一是什么意思？", "zh"),
    ("amara", "Amara, lepas night shift saya selalu pening, is that normal ke?", "mixed"),
    ("amara", "Doc, saya dah buat three twelve-hour shifts, perlu rest berapa hari?", "mixed"),
    ("hana", "Hana, yuzu cake tu, juice masuk glaze ke batter?", "mixed"),
    ("hana", "这个 onigiri 要怎么 shape 才不会散？", "mixed"),
    ("mei", "Mei, those pilots tu ada hospital tak?", "mixed"),
    ("mei", "试点里的 burnout 到底降了多少 percent？", "mixed"),
    ("victor", "Victor, kalau dorang cakap evidence tak cukup, kita nak jawab apa?", "mixed"),
    ("victor", "那个 Working Hours Act 是哪一年 pass 的？", "mixed"),
    ("amara", "Your fatigue review tu cover berapa sites?", "mixed"),
    ("hana", "Grandma 的 rainy-day soup 里面放什么？", "mixed"),
]


# ── the live state builders ──
def profiles() -> dict[str, dict[str, Any]]:
    return {cid: json.loads((SEED / f"{cid}.json").read_text(encoding="utf-8"))["data"]["profile"]
            for cid in WHO.values()}


def titles(prof: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    by_name = seed_titles()
    return {cid: by_name[str(p["name"])] for cid, p in prof.items() if str(p["name"]) in by_name}


def messages(lines: list[Line], prof: dict[str, dict[str, Any]]) -> list[MessageView]:
    out = []
    for i, (who, text) in enumerate(lines):
        user = who == "you"
        cid = None if user else WHO[who]
        out.append(MessageView(id=f"m{i}", seq=i + 1, author_type="user" if user else "character", character_id=cid,
                               name=USER if user else str(prof[str(cid)]["name"]), kind="chat", content=text))
    return out


def session(world: str, ids: list[str], lines: list[Line], prof: dict[str, dict[str, Any]], mode: str,
            premise: str = "") -> SessionContext:
    wid, wname, _ = WORLDS[world]
    parts = [ParticipantView(character_id=cid, name=str(prof[cid]["name"]), role="speaker",
                             character_role=str(prof[cid].get("role") or ""), energy={"current": 500, "max": 1000})
             for cid in ids]
    return SessionContext(session_id="ses_eval", seed="m12-eval", world=WorldView(id=wid, name=wname,
                                                                                  you={"displayName": USER}),
                          mode=mode, title="eval", participants=parts, recent=messages(lines, prof),
                          config={"premise": premise} if premise else {})


def views(ids: list[str], prof: dict[str, dict[str, Any]]) -> list[CharacterView]:
    return [CharacterView(id=cid, name=str(prof[cid]["name"]), profile=prof[cid]) for cid in ids]


def one_state(who: str, earlier: list[Line], message: str, prof: dict[str, dict[str, Any]],
              docs: dict[str, list[str]]) -> dict[str, Any]:
    cid = WHO[who]
    sctx = session(WORLD_OF[who], [cid], [*earlier, ("you", message)], prof, "one_on_one")
    req = PlanRequest(session=sctx, speaker_id=cid, cast=views([cid], prof), kind="reply", latest=message,
                      started_at=T0, documents={cid: docs[cid]})
    return dict(build_turn_plan_state(plan_state_input(req)).state)


def group_state(world: str, earlier: list[Line], message: str, prof: dict[str, dict[str, Any]],
                docs: dict[str, list[str]]) -> dict[str, Any]:
    ids = [WHO[c] for c in WORLDS[world][2]]
    sctx = session(world, ids, [*earlier, ("you", message)], prof, "group")
    req = CastRequest(session=sctx, kind="group_first", candidates=ids, cast=views(ids, prof), latest=message,
                      base_faces=dict.fromkeys(ids, "neutral"), started_at=T0,
                      documents={c: docs[c] for c in ids if c in docs})
    return dict(build_turn_plan_state(state_input(req)).state)


def watch_state(world: str, premise: str, before: list[Line], latest: Line, prof: dict[str, dict[str, Any]],
                docs: dict[str, list[str]]) -> dict[str, Any]:
    ids = [WHO[c] for c in WORLDS[world][2]]
    cands = [c for c in ids if c != WHO[latest[0]]]   # the last speaker never speaks twice in a row
    sctx = session(world, ids, [*before, latest], prof, "watch", premise)
    req = CastRequest(session=sctx, kind="scene", candidates=cands, cast=views(cands, prof),
                      latest=f"{prof[WHO[latest[0]]]['name']}: {latest[1]}", base_faces=dict.fromkeys(cands, "neutral"),
                      started_at=T0, documents={c: docs[c] for c in cands if c in docs})
    return dict(build_turn_plan_state(state_input(req)).state)


def debate_state(did: str, seq: int, docs: dict[str, list[str]]) -> dict[str, Any]:
    h = ds.load_history(did)
    assert h is not None, did
    sl = next(s for s in ds.slots(h) if s["seq"] == seq)
    req = ds.cut_request(h, sl, ds.profiles())
    req = req.model_copy(update={"documents": {c: docs[c] for c in sl["eligible"] if c in docs}})
    state, _, _, _ = ds.cut_state(req)
    return state


# ── the rows ──
def docs_row(n: int, state: dict[str, Any], who: str, label: str, lang: str, kind: str, source: str,
             prof: dict[str, dict[str, Any]]) -> dict[str, Any]:
    cid = WHO[who]
    if str(prof[cid]["name"]) not in (state.get("quoted_documents") or {}):
        raise ValueError(f"dcs-{n:03d}: {who} has no titles in the state, so live never asks about them")
    item_id = f"dcs-{n:03d}"
    return {"id": item_id, "question_id": "docs", "split": split_for(item_id), "lang": lang, "kind": kind,
            "item": {"state": state, "name": _name(str(prof[cid]["name"])), "key": f"docs:{cid}"},
            "label": label, "source": source}


def build_docs(prof: dict[str, dict[str, Any]], docs: dict[str, list[str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for who, earlier, message, label, lang, source in ONE:
        rows.append(docs_row(len(rows) + 1, one_state(who, earlier, message, prof, docs), who, label, lang,
                             "one_on_one", source, prof))
    for world, earlier, message, labels, lang, source in GROUP:
        state = group_state(world, earlier, message, prof, docs)
        for who, label in labels.items():
            rows.append(docs_row(len(rows) + 1, state, who, label, lang, "group", source, prof))
    for world, premise, before, latest, labels, source in WATCH:
        state = watch_state(world, premise, before, latest, prof, docs)
        for who, label in labels.items():
            rows.append(docs_row(len(rows) + 1, state, who, label, "en", "watch", source, prof))
    for did, seq, labels in DEBATE:
        state = debate_state(did, seq, docs)
        for who, label in labels.items():
            rows.append(docs_row(len(rows) + 1, state, who, label, "en", "debate", f"debate:{did}#{seq}", prof))
    return rows


def build_standalone(prof: dict[str, dict[str, Any]], docs: dict[str, list[str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for who, said, reply, follow, alone in STANDALONE:
        earlier = [("you", said), (who, reply)]
        for message, label in ((follow, "no"), (alone, "yes")):
            item_id = f"std-{len(rows) + 1:03d}"
            rows.append({"id": item_id, "question_id": "standalone", "split": split_for(item_id), "lang": "en",
                         "kind": "one_on_one", "item": {"state": one_state(who, earlier, message, prof, docs)},
                         "label": label, "source": "written"})
    return rows


def build_english(prof: dict[str, dict[str, Any]], docs: dict[str, list[str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for who, message, lang in ENGLISH:
        item_id = f"eng-{len(rows) + 1:03d}"
        rows.append({"id": item_id, "question_id": "english", "split": split_for(item_id), "lang": lang,
                     "kind": "one_on_one", "item": {"state": one_state(who, [], message, prof, docs)},
                     "label": "yes" if lang == "en" else "no", "source": "written"})
    return rows


def problems(sets: dict[str, list[dict[str, Any]]]) -> list[str]:
    out: list[str] = []
    d = sets["docs"]
    langs = Counter(r["lang"] for r in d)
    if not 110 <= len(d) <= 130:
        out.append(f"docs: {len(d)} items (want about 120)")
    if sum(r["label"] == "yes" for r in d) < 60:
        out.append(f"docs: {sum(r['label'] == 'yes' for r in d)} yes (want at least 60)")
    if (langs["ms"], langs["zh"], langs["mixed"]) != (10, 6, 4):
        out.append(f"docs: languages {dict(langs)} (want ms 10, zh 6, mixed 4, the rest English)")
    if {r["kind"] for r in d} != {"one_on_one", "group", "watch", "debate"}:
        out.append("docs: every mode needs items")
    s = sets["standalone"]
    if len(s) != 100 or sum(r["label"] == "no" for r in s) != 50:
        out.append(f"standalone: {len(s)} items, {sum(r['label'] == 'no' for r in s)} follow-ups (want 100, 50)")
    e = Counter(r["lang"] for r in sets["english"])
    if dict(e) != {"en": 10, "ms": 10, "zh": 10, "mixed": 10}:
        out.append(f"english: {dict(e)} (want 10 each)")
    for name, rows in sets.items():
        tests = sum(r["split"] == "test" for r in rows)
        if not tests or tests == len(rows):
            out.append(f"{name}: needs both splits")
    return out


def main() -> int:
    prof = profiles()
    docs = titles(prof)
    sets = {"docs": build_docs(prof, docs), "standalone": build_standalone(prof, docs),
            "english": build_english(prof, docs)}
    bad = problems(sets)
    for line in bad:
        print(line)
    for name, rows in sets.items():
        out = DATASETS / name / f"{name}.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        c = Counter((r["label"], r["split"]) for r in rows)
        print(f"{name}: {len(rows)} -> {out.relative_to(ROOT).as_posix()}: "
              + ", ".join(f"{k}/{s} {n}" for (k, s), n in sorted(c.items())))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
