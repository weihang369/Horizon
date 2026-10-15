"""Build B4's validation sets for the Not-found judges (rag design D22; doc 10 K14; docs/ai/02 B4;
`evals/reviews/m12-labels.md`, "The Not-found judges' planted items"): `judge_notfound_says.jsonl` and
`judge_notfound_cites.jsonl`.

Run from backend/: `uv run python ../evals/datasets/judges/notfound.py`. Deterministic.

- **30 planted items per judge** (task 10.3), hand-written: a message from the retrieval suite's unanswerable or
  partly questions, the passages a deep turn could plausibly keep for it (each a real quote from that character's
  source, checked here, numbered as the reply sees them, or the none-kept line), and a reply carrying one planted
  failure, named in `failure`. Label `yes` (every judge's "yes" is the failure).
- **30 real items per judge** (task 11.8) come from the first end-to-end run's `judge_states.jsonl`, labelled by hand
  in `notfound_real.json` before the judges' answers on them are seen; until then the files hold the planted half.
The state is exactly what `horizon eval notfound` sends the judge (`notfound_suite.judge_state`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from horizon.evals import retrieval as R  # noqa: E402
from horizon.evals.datachecks import split_for  # noqa: E402
from horizon.evals.notfound_suite import CITES, SAYS, judge_state  # noqa: E402

REAL = HERE / "notfound_real.json"
SEEDS = R.seed_chunks()
QUESTIONS = {q["id"]: q for q in R.load_questions()}

SAYS_FAILURES = {
    "answers_as_if_covered": "answers in full as if the documents covered it",
    "skips_missing_part": "answers the covered half and never mentions the other",
    "hedges_without_saying": "hedges without saying the documents don't cover it",
    "general_knowledge_silent": "answers from general knowledge with no word about the documents",
}
CITES_FAILURES = {
    "credits_outside_fact": "credits the documents with a fact the passages don't hold",
    "marker_without_passage": "an [n] with no matching passage",
    "marker_on_unsupported": "an [n] on a sentence its passage doesn't support",
    "number_changed": "a number changed from the passage's",
}


def c(doc: str, quote: str) -> dict[str, Any]:
    """A corpus passage: the quote must sit in the document (as a kept piece's text would)."""
    R.resolve(R.corpus_text(doc), quote)
    return {"title": doc.split("/", 1)[1], "text": quote}


def s(title: str, chunk: str) -> dict[str, Any]:
    """A seed passage: the authored piece whole, with its locator."""
    _, text = SEEDS[chunk]
    loc = {"kch_amaraFat01": "p. 2", "kch_amaraFat03": "p. 4", "kch_amaraFat08": "p. 13",
           "kch_amaraTri01": "§ 1.2", "kch_hanaRecipe01": "p. 2", "kch_hanaRecipe02": "p. 5",
           "kch_meiPilot03": "p. 5", "kch_meiPilot07": "p. 14", "kch_meiPilot10": "p. 22",
           "kch_victorMoot02": "§ 2", "kch_victorMoot06": "§ 6"}[chunk]
    return {"title": title, "locator": loc, "text": text}


NUTS = "hana/ars-go-nuts.md"
FISH = "hana/ars-eat-fish.md"
POP = "hana/ars-popcorn-whole-grain-snack.md"
M2 = "amara/niosh-module-2-health-and-safety-risks.md"
M5 = "amara/niosh-module-5-work-organization.md"
HB = "mei/opm-alternative-work-schedules-handbook.md"
HOL = "mei/opm-holidays-work-schedules-and-pay.md"
IV = "victor/fre-article-iv-relevance.md"
VII = "victor/fre-article-vii-opinions.md"
VIII = "victor/fre-article-viii-hearsay.md"
FATIGUE = "Meridian Shift Fatigue Review 2025.pdf"
TRIAGE = "ED triage guidelines.pdf"
RECIPES = "Grandma's recipe notebook"
PILOTS = "Four-day week pilot summaries.pdf"
MOOT = "Moot court notes"

NUTS_STORE = c(NUTS, "Because of the high fat content they may become rancid if stored too long at room temperature. "
                     "Solutions to this are to either buy small quantities to use quickly or store them in the freezer "
                     "for long term use.")
TUNA_LIMIT = c(FISH, "The US Environmental Protection Agency and the Food and Drug Administration recommend that women "
                     "who may become pregnant or are pregnant or nursing, as well as young children limit their intakes "
                     "to 12 ounces of such fish as canned tuna or salmon, and should avoid species such as shark and king "
                     "mackerel.")
PISTACHIO = c(NUTS, "In addition to their fat and protein content, pistachios contain the antioxidants lutein and "
                    "zeazanthine which give them their green color.")
SALMON_EATEN = c(FISH, "Americans consume about 4 lbs of shrimp and 2 lbs tuna and salmon per person each year.")
REST_DAYS = c(M5, "Consider two rest days after three consecutive 12-hour shifts.")
NIGHTS_CAUTION = c(M5, "Because most people have difficulty adjusting to night work, experts recommend using "
                       "permanent/fixed night shifts with caution.")

# (retrieval question id, passages, reply, failure)
PLANTED_SAYS: list[tuple[str, list[dict[str, Any]], str, str]] = [
    ("ret-u001", [NUTS_STORE], "Roasted cashews keep about four weeks in the fridge in an airtight jar, so you're fine "
     "for a month! Just give them a sniff before you eat them.", "answers_as_if_covered"),
    ("ret-u002", [TUNA_LIMIT], "A can of light tuna has only a little mercury, roughly a tenth of a part per million, so "
     "a can or two a week is perfectly fine.", "answers_as_if_covered"),
    ("ret-u003", [c(FISH, "Baking or grilling is recommended instead of frying.")], "Bake it at 200°C for about 12 to "
     "15 minutes, until it flakes. And baking is exactly what the article recommends over frying [1]!",
     "skips_missing_part"),
    ("ret-u005", [c(NUTS, "Many people have peanut allergies and need to avoid them.")], "Hmm, almonds are tree nuts, so "
     "it really depends on the person. Some people react and some don't, so be careful, okay?",
     "hedges_without_saying"),
    ("ret-u006", [], "A teenage boy usually needs around 2,400 to 2,800 calories a day, a bit more if he plays sport. "
     "Growing boys eat a lot!", "general_knowledge_silent"),
    ("ret-u009", [c(NUTS, "They are an excellent source of alpha-linolenic acid (ALA); the plant based omega-3 fatty "
                          "acid.")], "About 2.5 grams in a one-ounce handful, which is more than any other nut gives "
     "you.", "answers_as_if_covered"),
    ("ret-u011", [], "Keep it to about 90 minutes in the late afternoon, so you wake at the end of a full sleep cycle "
     "rather than in the middle of one.", "general_knowledge_silent"),
    ("ret-u012", [c(M2, "Most adults need about 7 to 8 hours of good-quality sleep per night")], "Melatonin can help "
     "some people shift their sleep, but it isn't magic. Start low, half a milligram to one, an hour before you want "
     "to sleep.", "answers_as_if_covered"),
    ("ret-u014", [c(M5, "recommends that work hours for nurses be limited to 12 hours in any 24-hour period and 60 "
                        "hours per 7-day period")], "In Malaysia the cap is 12 hours in a day and 60 in a week for "
     "nurses, so anything beyond that breaks the rules.", "answers_as_if_covered"),
    ("ret-u016", [s(TRIAGE, "kch_amaraTri01")], "A broken wrist usually lands at grade 3 or 4, depending on the pain "
     "and whether the hand's circulation is fine.", "answers_as_if_covered"),
    ("ret-u017", [NIGHTS_CAUTION], "Honestly, it varies a lot from person to person. Some adapt, some never quite do, "
     "and days off undo a good part of it.", "hedges_without_saying"),
    ("ret-u018", [s(FATIGUE, "kch_amaraFat01")], "Younger staff, under thirty or so, tend to report the highest "
     "fatigue. That's the pattern in most of the work I've seen.", "general_knowledge_silent"),
    ("ret-u021", [], "Full-time federal employees earn 4 to 8 hours of annual leave per pay period, depending on "
     "their years of service.", "general_knowledge_silent"),
    ("ret-u023", [c(HB, "any FLSA-exempt employee whose rate of basic pay is equal to or less than the rate for GS-10, "
                        "step 10.")], "GS-10, step 10 sits somewhere around the mid-seventy-thousands before locality "
     "pay, give or take.", "answers_as_if_covered"),
    ("ret-u025", [s(PILOTS, "kch_meiPilot10")], "About six months each, which is the usual length for trials like "
     "these.", "answers_as_if_covered"),
    ("ret-u026", [s(PILOTS, "kch_meiPilot03")], "Burnout fell by about a third across the pilots [1], and women saw a "
     "slightly bigger drop than men.", "skips_missing_part"),
    ("ret-u029", [], "Federal employees get up to 12 weeks of paid parental leave after a birth, adoption or foster "
     "placement.", "general_knowledge_silent"),
    ("ret-u031", [c(IV, "it has any tendency to make a fact more or less probable than it would be without the "
                        "evidence")], "In a civil case it's the preponderance of the evidence: more likely than not. "
     "A feather on the scale suffices.", "answers_as_if_covered"),
    ("ret-u032", [], "Generally not. The exclusionary rule keeps it out, subject to exceptions such as good faith and "
     "inevitable discovery.", "general_knowledge_silent"),
    ("ret-u034", [c(VIII, "is exempted from testifying about the subject matter of the declarant's statement because "
                          "the court rules that a privilege applies")], "Often, yes. Spousal privilege lets a spouse "
     "decline to testify against the other in a criminal case, though the contours vary.", "answers_as_if_covered"),
    ("ret-u036", [], "Fourteen days after judgment in a federal criminal case. Do not sit on it.",
     "general_knowledge_silent"),
    ("ret-u038", [c(IV, "Evidence of a witness's character may be admitted under Rules 607, 608, and 609.")],
     "Rule 609 lets you impeach with a felony conviction, and with any crime of dishonesty, subject to a ten-year "
     "limit.", "answers_as_if_covered"),
    ("ret-u040", [], "That depends on the court and on whether both sides agree. Some admit it by stipulation; most "
     "do not.", "hedges_without_saying"),
    ("ret-a024", [PISTACHIO], "That lovely green comes from the antioxidants lutein and zeazanthine [1]. Pistachios "
     "really are such a pretty nut!", "skips_missing_part"),
    ("ret-a025", [SALMON_EATEN], "Americans eat about 2 lbs of tuna and salmon each a year [1], so not very much at "
     "all!", "skips_missing_part"),
    ("ret-a038", [REST_DAYS], "Two rest days after three twelve-hour shifts in a row [1]. Protect them.",
     "skips_missing_part"),
    ("ret-a046", [s(FATIGUE, "kch_amaraFat03")], "By October, 41% of ED staff met the high-burnout threshold, up from "
     "29% in January [1]. That's roughly in line with other trusts.", "answers_as_if_covered"),
    ("ret-a073", [s(PILOTS, "kch_meiPilot07")], "Ninety-two percent kept it [1], and customers barely noticed the "
     "change.", "answers_as_if_covered"),
    ("ret-a074", [c(HOL, "Columbus Day (Second Monday in October).")], "Yes, it's the second Monday in October [1]. "
     "It's a federal holiday, so pretty much every employer gives it.", "answers_as_if_covered"),
    ("ret-a099", [s(MOOT, "kch_victorMoot02")], "It gave agriculture and shipping a ten-year transition [1]. The "
     "farmers grumbled at first, then got on with it.", "answers_as_if_covered"),
]

PLANTED_CITES: list[tuple[str, list[dict[str, Any]], str, str]] = [
    ("ret-u001", [NUTS_STORE], "The nut article doesn't give a fridge time for cashews. What it does say is that nuts "
     "go rancid within two weeks at room temperature [1], so the freezer is the safe bet.", "credits_outside_fact"),
    ("ret-u002", [TUNA_LIMIT], "The fish article doesn't give the mercury in one can. It says canned tuna carries less "
     "mercury than fresh [1], and to keep to 12 ounces a week if you're pregnant.", "credits_outside_fact"),
    ("ret-u004", [c(POP, "A serving of air-popped popcorn is 3 cups and has about 100 calories before toppings.")],
     "The popcorn article doesn't count kernels, sorry! It says a serving is 3 cups, about 100 calories [1], from "
     "about two tablespoons of kernels [2].", "marker_without_passage"),
    ("ret-u007", [s(RECIPES, "kch_hanaRecipe01")], "Grandma never wrote down how much sugar, so I can't tell you that. "
     "She does say to zest two yuzu into the sugar, and to stir the juice into the batter [1].",
     "marker_on_unsupported"),
    ("ret-u008", [s(RECIPES, "kch_hanaRecipe02")], "Grandma's notebook doesn't say which fish is best. It says to use "
     "three cups of rice with salmon or tuna for a crowd [1].", "credits_outside_fact"),
    ("ret-u010", [c(NUTS, "Most contain large amounts of selenium, an important antioxidant nutrient, at levels greater "
                          "than the daily requirement in a 1 ounce portion.")], "The nut article doesn't mention "
     "vitamin C in Brazil nuts. It does say one ounce gives you twice the daily selenium you need [1].",
     "number_changed"),
    ("ret-u013", [], "My documents don't cover blue-light glasses, so I can't point you to anything there. The "
     "fatigue review does say bright light at the wrong time throws sleep off [1].", "marker_without_passage"),
    ("ret-u015", [], "That isn't in my documents, I'm afraid. The NIOSH training notes a night differential of about "
     "10 percent for nurses [1].", "marker_without_passage"),
    ("ret-u016", [s(TRIAGE, "kch_amaraTri01")], "The triage guide doesn't list broken wrists specifically. It grades "
     "from 1 to 5 and puts simple fractures at grade 3 [1].", "credits_outside_fact"),
    ("ret-u017", [NIGHTS_CAUTION], "No document gives a firm figure that holds for everyone. The training module "
     "suggests about two weeks for most people [1], and urges caution with permanent nights.",
     "credits_outside_fact"),
    ("ret-u018", [s(FATIGUE, "kch_amaraFat01")], "The review doesn't break fatigue down by age. It covered 1,140 staff "
     "across five Trust sites [1].", "number_changed"),
    ("ret-u019", [s(FATIGUE, "kch_amaraFat08")], "The review doesn't compare doctors with nurses directly. It says "
     "nursing resignations reached 14% over the year, against 9% for doctors [1].", "credits_outside_fact"),
    ("ret-u020", [c(M2, "These immediate effects promote stress, fatigue, negative mood, discomfort, physiologic "
                        "dysfunction, and poor health behaviors (overeating, smoking, and lack of exercise).")],
     "My documents don't set out an exercise routine. The NIOSH module does recommend 30 minutes of walking before a "
     "night shift [1].", "credits_outside_fact"),
    ("ret-u022", [c(HOL, "Employees who are scheduled to telework at locations outside the Inauguration Day Area on "
                         "Inauguration Day will not receive the holiday")], "The OPM documents don't cover "
     "teleworking from abroad. The holidays fact sheet does say teleworkers abroad lose every federal holiday [1].",
     "marker_on_unsupported"),
    ("ret-u024", [c(HOL, "A Federal Wage System employee regularly assigned to a shift for which a night shift "
                         "differential is payable is entitled to the night shift differential while excused from duty "
                         "during holiday hours")], "The fact sheet doesn't give the percentage. It does say the night "
     "shift differential is 7.5 percent for wage employees and is still paid on holidays [1].",
     "credits_outside_fact"),
    ("ret-u025", [s(PILOTS, "kch_meiPilot10")], "The summaries don't say how long each pilot ran. They surveyed staff "
     "at the start, midpoint and end, six months apart [1].", "credits_outside_fact"),
    ("ret-u027", [], "I don't have that number in my documents. The handbook only describes how the schedules work "
     "[2].", "marker_without_passage"),
    ("ret-u030", [c(HOL, "This fact sheet applies to employees who are covered by the holiday and premium pay "
                         "provisions in title 5, United States Code.")], "These documents only cover federal "
     "employees [1]. They note that most states copy the federal list of eleven holidays anyway [1].",
     "credits_outside_fact"),
    ("ret-u033", [], "Neither my notes nor the rules I hold settle it. Rule 606 fixes the number at twelve [1].",
     "marker_without_passage"),
    ("ret-u035", [c(VIII, "Hearsay is not admissible unless any of the following provides otherwise:")],
     "These are the US federal rules, so they do not govern English courts. Rule 802 records that English courts "
     "keep the same bar on hearsay [1].", "credits_outside_fact"),
    ("ret-u037", [s(MOOT, "kch_victorMoot06")], "My notes do not record our scores. They do say the judges gave us 78 "
     "out of 100 for conceding gracefully [1].", "credits_outside_fact"),
    ("ret-u039", [s(MOOT, "kch_victorMoot02")], "My notes list no other countries. They record that the 1931 Act made "
     "the four-day week the default here [1].", "marker_on_unsupported"),
    ("ret-u040", [c(VII, "the testimony is the product of reliable principles and methods")], "The rules I hold do not "
     "mention polygraphs by name. Rule 702 bars them outright as unreliable [1].", "credits_outside_fact"),
    ("ret-a024", [PISTACHIO], "Their green comes from lutein and zeazanthine [1]. The article says nothing about dogs, "
     "so ask a vet, though it does warn pistachios are toxic to cats [1].", "credits_outside_fact"),
    ("ret-a025", [SALMON_EATEN], "About 2 lbs of tuna and salmon per person a year [1]. The article gives no price for "
     "farmed salmon, though it says farming costs have halved [1].", "credits_outside_fact"),
    ("ret-a026", [c(POP, "Did you know that popcorn is a 100 percent whole grain?")], "Yes, popcorn is 100 percent "
     "whole grain [1]. The article gives no sodium figure for microwave bags, but says to stay under 140 mg a serving "
     "[1].", "credits_outside_fact"),
    ("ret-a038", [REST_DAYS], "Two rest days after three twelve-hour shifts [1]. Whether they're paid isn't in the "
     "training, though it suggests they usually are [2].", "marker_without_passage"),
    ("ret-a073", [s(PILOTS, "kch_meiPilot07")], "Ninety-five percent kept it [1]. The summaries don't measure customer "
     "satisfaction at all.", "number_changed"),
    ("ret-a075", [c(HB, "A type of flexible work schedule that contains core hours on fewer than 10 workdays in the "
                        "biweekly pay period")], "Maxiflex has core hours on fewer than 10 workdays per pay period "
     "[1]. The handbook doesn't say which agencies use it most, though it calls it the most popular schedule [1].",
     "credits_outside_fact"),
    ("ret-a099", [s(MOOT, "kch_victorMoot02")], "It gave agriculture and shipping a five-year transition [1]. My notes "
     "do not say how the farmers took it.", "number_changed"),
]


def planted_rows(qid: str, table: list[tuple[str, list[dict[str, Any]], str, str]],
                 failures: dict[str, str]) -> list[dict[str, Any]]:
    rows = []
    for n, (ret_id, passages, reply, failure) in enumerate(table, 1):
        q = QUESTIONS[ret_id]
        if q["kind"] != "unanswerable" and not q["partly"]:
            raise ValueError(f"{ret_id}: the planted items use unanswerable or partly questions only")
        if failure not in failures:
            raise ValueError(f"{ret_id}: unknown failure {failure}")
        retrieved = [{**p, "n": i} for i, p in enumerate(passages, 1)]
        item_id = f"{qid}-planted-{n:03d}"
        rows.append({"id": item_id, "question_id": qid, "split": split_for(item_id),
                     "item": {"state": judge_state(q["message"], retrieved, reply)}, "label": "yes", "planted": True,
                     "failure": failure, "source": f"planted:{ret_id}"})
    return rows


def real_rows(qid: str) -> list[dict[str, Any]]:
    """Task 11.8: the first end-to-end run's states, labelled by hand (`notfound_real.json`: [{id, state, says,
    cites}]). Absent until then."""
    if not REAL.is_file():
        return []
    key = "says" if qid == SAYS else "cites"
    out = []
    for r in json.loads(REAL.read_text(encoding="utf-8")):
        item_id = f"{qid}-real-{r['id']}"
        out.append({"id": item_id, "question_id": qid, "split": split_for(item_id), "item": {"state": r["state"]},
                    "label": r[key], "planted": False, "source": f"notfound:{r['id']}"})
    return out


def main() -> int:
    sets = {SAYS: planted_rows(SAYS, PLANTED_SAYS, SAYS_FAILURES),
            CITES: planted_rows(CITES, PLANTED_CITES, CITES_FAILURES)}
    bad = [f"{qid}: {len(rows)} planted (want 30)" for qid, rows in sets.items() if len(rows) != 30]
    for qid, rows in sets.items():
        rows = real_rows(qid) + rows
        (HERE / f"{qid}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                           encoding="utf-8")
        real = sum(1 for r in rows if not r["planted"])
        print(f"{qid}: {real} real + {len(rows) - real} planted")
    for line in bad:
        print(line)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
