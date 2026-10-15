"""The retrieval questions, written blind (rag design D22): each names its character, its message (and, for a
follow-up, the two earlier lines), and its labels as exact quotes from the source, graded 2 (answers) or 1 (partly).
`build.py` turns them into `retrieval.jsonl`. An unanswerable question is on the same topics and has no span.

Ids: `ret-<kind letter><n>`: a answerable, u unanswerable, f follow-up, x non-English, n naming.
"""

from typing import Any

HANA_NUTS = "hana/ars-go-nuts.md"


def corpus(doc: str, quote: str, grade: int = 2) -> dict[str, Any]:
    return {"doc": doc, "quote": quote, "grade": grade}


def seed(source: str, chunk: str, quote: str, grade: int = 2) -> dict[str, Any]:
    return {"doc": f"seed:{source}", "chunk": chunk, "quote": quote, "grade": grade}


QUESTIONS: list[dict[str, Any]] = [
    # ── answerable ──
    {"id": "ret-a001", "kind": "answerable", "who": "hana",
     "message": "Which nut has more protein than the others?",
     "spans": [corpus(HANA_NUTS, "they contain more protein than any other FDA-classified nut")]},
    {"id": "ret-a002", "kind": "answerable", "who": "hana",
     "message": "How big is one serving of nuts, roughly?",
     "spans": [corpus(HANA_NUTS, "A serving of nuts is one ounce or about a small handful."),
               corpus(HANA_NUTS, "on average this provides 150-200 calories per serving", 1)]},
    {"id": "ret-a003", "kind": "answerable", "who": "hana", "seed": True,
     "message": "When does the yuzu juice go into the cake?",
     "spans": [seed("kno_seedHana1", "kch_hanaRecipe01", "The juice goes in the glaze, never the batter.")]},
    {"id": "ret-a004", "kind": "answerable", "who": "mei", "seed": True,
     "message": "By how much did burnout drop in the pilots?",
     "spans": [seed("kno_seedMei2", "kch_meiPilot03",
                    "self-reported burnout fell by an average of 32% and sick days by 21%")]},
    {"id": "ret-a005", "kind": "answerable", "who": "hana", "needs_two": True,
     "message": "Which nuts are good for vitamin E and which one is mostly polyunsaturated fat?",
     "spans": [corpus(HANA_NUTS, "unlike other nuts, contain predominantly polyunsaturated fat"),
               corpus(HANA_NUTS, "Almonds are a source of vitamin E, folic acid, calcium, and magnesium.")]},
    # ── unanswerable ──
    {"id": "ret-u001", "kind": "unanswerable", "who": "hana",
     "message": "How long can roasted cashews stay fresh in the fridge?"},
    # ── follow-ups ──
    {"id": "ret-f001", "kind": "followup", "who": "hana",
     "earlier": ["Kai: I keep a big jar of walnuts in the cupboard for months.",
                 "Hana: Months is a long time for something that oily."],
     "message": "So what should I do with them instead?",
     "spans": [corpus(HANA_NUTS, "buy small quantities to use quickly or store them in the freezer for long term use")]},
    # ── non-English ──
    {"id": "ret-x001", "kind": "non_english", "lang": "ms", "who": "hana",
     "message": "Kacang apa yang ada banyak selenium?",
     "spans": [corpus(HANA_NUTS, "Most contain large amounts of selenium, an important antioxidant nutrient")]},
    # ── naming a document ──
    {"id": "ret-n001", "kind": "naming", "who": "hana", "named": {"doc": "Go Nuts", "section": None},
     "message": "In the Go Nuts piece, what does the European Union let people claim about walnuts?",
     "spans": [corpus(HANA_NUTS, "Walnuts contribute to the improvement of the elasticity of the blood vessels.")]},
]
