"""Build `debate_member.jsonl`: the debate member slice (M11, debate design D21; `evals/reviews/m11-labels.md`, "The
debate member slice").

Run from backend/: `uv run python ../evals/datasets/debate_member/build.py`. Deterministic. Labels were written blind
under m11-labels.md (committed first), from each cut alone, before any Jev answer.

- **Natural slots:** every rebuttal and closing slot of the committed histories (`evals/debates/*.json`) with two or
  more eligible members, cut with the live debate plan's request and state (`horizon.evals.debate_suites`). A slot
  is an item only when `LABELS` has it: a slot where any member would do equally is not written.
- **Written variants:** a natural slot whose last opposing argument is rewritten so that it plainly falls in one
  member's field (single-answer by construction). The non-English items are variants written in that language.
- **Labels:** the acceptable members (one or two), `single` (only one fits), and `fixed`, the fixed-order answer
  (the first eligible member). The fixed order is never a reason by itself.
- **Splits:** M9's hash rule with M10's id-prefix search for at least 30 test items (V11).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

from horizon.evals import debate_suites as ds  # noqa: E402
from horizon.evals.datachecks import split_for  # noqa: E402

TESTS = 30
SIDE_LABEL = {"prop": "Proposition", "opp": "Opposition"}

# "<debate>#<slot seq>": (acceptable character ids, single). Written in task 10.3, blind, from each cut alone (the
# debate before the slot). A slot where any member would do equally has no item: d10#16, d13#9, d13#13, d13#14,
# and every two-candidate slot where both are equally placed (accepting both measures nothing; the review pass,
# evals/reviews/m11-review.md). Two members are acceptable only where a third candidate is not.
LABELS: dict[str, tuple[list[str], bool]] = {
    # d01 (ban private cars): Sofia planner, Amara physician | Victor litigator, Mei economist
    "d01#7": (["chr_evalSofia"], True),                       # Mei attacks Sofia's pilot and asks for cordon metrics
    "d01#12": (["chr_evalSofia"], True),                      # Mei's cordon design, against Sofia's pilot
    # d02 (school day at ten): Daniel head, Amara physician | Mei economist, Sofia planner
    "d02#7": (["chr_evalDaniel"], True),                      # Sofia's catchment, buses and Year 9s: the school's day
    "d02#12": (["chr_evalDaniel"], True),                     # Sofia's school pilot names Daniel's earliest buses
    "d02#13": (["chr_evalSofia"], True),                      # Daniel's closing takes on Sofia's pilot
    # d03 (four-day week): Mei economist, Daniel head | Victor litigator, Sofia planner
    "d03#7": (["chr_seedMei"], True),                         # Sofia: "Mei's own numbers make my case"
    # d04 (sugary drinks tax): Amara physician, Mei economist | Victor litigator, Daniel head
    "d04#12": (["chr_seedMei"], True),                        # Daniel attacks Mei's substitution point
    # d05 (smartphones in primary schools): Aiko nurse, Takeshi train engineer | Rin game design, Hana florist
    "d05#7": (["chr_evalAiko"], True),                        # Hana answers Aiko's worried grandmother
    "d05#12": (["chr_seedTakeshi"], True),                    # Hana attacks Takeshi's documented lane, in train terms
    # d06 (high street closed at weekends): Hana florist, Aiko nurse | Takeshi train engineer, Bram farmer
    "d06#7": (["chr_seedHana"], True),                        # Bram names Hana; a small business's margins
    "d06#12": (["chr_evalAiko"], True),                       # Bram: "Aiko says design it first"
    # d07 (reopen the branch railway): Takeshi train engineer, Bram farmer | Rin game design, Hana florist
    "d07#7": (["chr_seedTakeshi"], True),                     # Hana: Takeshi's heartstrings; signals, subsidy, ridership
    "d07#12": (["chr_evalBram"], True),                       # Hana attacks Bram's co-op volume and road bill
    # d08 (school meals from local farms): Bram farmer, Hana florist | Rin game design, Aiko nurse
    "d08#7": (["chr_evalBram"], True),                        # Aiko: failed crops and fixed prices, Bram's case
    # d09 (compulsory voting, 3 v 2): Victor, Mei, Daniel | Amara physician, Sofia planner
    "d09#8": (["chr_seedVictor"], True),                      # Sofia: "Victor, you've just handed me my own objection"
    "d09#10": (["chr_seedMei"], True),                        # Amara: equalising would show in policy outcomes (Mei's claim)
    "d09#14": (["chr_evalDaniel"], True),                     # Sofia attacks Daniel's 31 % and his parents' evening
    "d09#16": (["chr_evalDaniel"], True),                     # Amara: Daniel "has answered his own question"
    # d10 (video games ban, 3 v 2): Aiko nurse, Takeshi train engineer, Bram farmer | Rin game design, Hana florist
    "d10#8": (["chr_evalAiko"], True),                        # Hana answers Aiko's boy on the hill
    "d10#9": (["chr_seedRin"], True),                         # Aiko: "I hear you, Rin"; forbidden fruit, age twelve
    "d10#10": (["chr_evalBram"], True),                       # Rin turns Bram's broken fence against his side
    "d10#14": (["chr_evalAiko", "chr_evalBram"], False),      # Hana answers Aiko's seatbelt and Bram's question
    "d10#15": (["chr_seedRin"], True),                        # Aiko answers Rin's padlock, controls and sleep-mode
    # d11 (abolish homework, quick): Daniel head, Amara physician | Mei economist, Victor litigator
    "d11#7": (["chr_evalDaniel"], True),                      # Victor asks Daniel directly
    "d11#8": (["chr_seedVictor"], True),                      # Daniel answers Victor twice (terms, amputation)
    # d12 (fireworks ban, quick): Aiko nurse, Bram farmer | Hana florist, Rin game design
    "d12#7": (["chr_evalAiko"], True),                        # Rin answers Aiko's Mrs Kellerman
    "d12#8": (["chr_seedRin"], True),                         # Aiko answers Rin's quiet zone and nine o'clock show
    # d13 (panel: hospital or clinics): Amara, Mei, Victor, Sofia
    "d13#7": (["chr_seedAmara"], True),                       # Sofia asks for ambulance times and acute capacity
    "d13#8": (["chr_seedMei", "chr_seedVictor"], False),      # Amara uses Mei's staffing and Victor's "rather than"
    "d13#12": (["chr_seedVictor"], True),                     # Sofia: "Victor's frame isn't the only map"
}

# (debate, slot seq, the rewritten last opposing argument, the acceptable character id, language). Task 10.3:
# aimed at the second member in fixed order as often as the first; a slot holds at most one per member.
VARIANTS: list[tuple[str, int, str, str, str]] = [
    # English (29 written with the labels): the last opposing argument rewritten into one member's field
    ("d01", 8, "Sofia: Mei's labour-market worries miss the point. The pilot changes no wages and no contracts; shop "
     "staff in the core keep their shifts, and turnover in comparable cities held within a few per cent. If she wants "
     "an employment elasticity, twelve months of payroll data will give her one.", "chr_seedMei", "en"),
    ("d01", 12, "Mei: Let me press the medicine. Amara says cleaner air means fewer asthma attacks, but particulates in a "
     "two-kilometre core come mostly from the buses and vans the pilot keeps. Nobody has shown me emergency admissions "
     "for asthma or road trauma before and after. That's the weakest link in the chain.", "chr_seedAmara", "en"),
    ("d01", 13, "Sofia: On the law, the motion is sound. A traffic regulation order already lets a council restrict "
     "classes of vehicle on named streets; nobody holds a right to drive a private car through a city centre, and the "
     "exemptions are exactly what proportionality asks for. The constitutional objection is a costume.",
     "chr_seedVictor", "en"),
    ("d02", 8, "Daniel: Mei says costs shift, so let me price them. A later start frees the morning peak for commuters, "
     "the bus contracts already run off-peak fares at half nine, and parents in my catchment lose no paid hours "
     "because breakfast club covers eight to ten. The wage cost she fears is a rounding error.", "chr_seedMei", "en"),
    ("d02", 12, "Sofia: Amara's circadian evidence comes from cohorts with fixed bedtimes. Show me the clinical trials "
     "where a ten o'clock start cut anxiety or depression diagnoses, not self-reported sleep. A sleep diary isn't an "
     "outcome; a GP visit is.", "chr_seedAmara", "en"),
    ("d02", 13, "Daniel: The economics are the case. Better-rested pupils score higher, and the return to a grade at "
     "sixteen shows up in wages at thirty. Every pound the bus depot spends comes back in the labour market. Price that "
     "and the motion pays for itself.", "chr_seedMei", "en"),
    ("d03", 7, "Sofia: Look at the schools first. Teachers can't take a fifth day off: a thirty-period timetable, cover "
     "supervisors already stretched, exam classes that can't lose a day. Ask any headteacher how he'd staff a Friday "
     "and he'll show you the cover budget.", "chr_evalDaniel", "en"),
    ("d03", 8, "Mei: And on the law the mover is safe: a public servant's contract can be varied by collective "
     "agreement, the Working Time Code sets a ceiling, not a floor, and no statute requires a five-day week. 'Define "
     "your terms' has no legal teeth here.", "chr_seedVictor", "en"),
    ("d03", 12, "Sofia: Let's talk money. Four days at five days' pay is a twenty per cent rise in the hourly wage; in a "
     "labour market this tight, private employers match it within a year and the council's wage bill follows. The "
     "productivity gain has to be large just to stand still.", "chr_seedMei", "en"),
    ("d04", 7, "Daniel: Amara, the obesity numbers in my school haven't moved through ten years of healthy-eating "
     "campaigns. If liquid sugar is the driver, show me the paediatric data: insulin resistance at twelve, dental "
     "admissions. Without clinical outcomes the tax is a guess.", "chr_seedAmara", "en"),
    ("d04", 12, "Daniel: The school nurse sees the teeth. Dental extractions under general anaesthetic are the commonest "
     "reason children here go into hospital, and they come from fizzy drinks. If the tax touches that, I'd hear it "
     "from the children's ward, not the Treasury.", "chr_seedAmara", "en"),
    ("d04", 13, "Amara: And the legal objection fails. A levy on producers by sugar content is an ordinary excise duty, "
     "the kind we already set on tobacco and alcohol. No court has held a health excise disproportionate; this is a "
     "tax the constitution plainly allows.", "chr_seedVictor", "en"),
    ("d05", 7, "Hana: Phones are like a signal box: the right message at the right time. Ban them and you've ripped out "
     "the signals but left the trains running; kids still need to know when practice ends or a bus is cancelled. "
     "Nobody makes a line safer by taking out its signals.", "chr_seedTakeshi", "en"),
    ("d05", 8, "Aiko: Rin, every app on that phone is built by people whose job is to keep a child playing: streaks, "
     "loot boxes, endless feeds. That's game design aimed at a seven-year-old. Teach the skill on a school device "
     "without the hooks.", "chr_seedRin", "en"),
    ("d05", 12, "Hana: The health story runs the other way: inhalers, epilepsy alerts, glucose monitors that live on a "
     "parent's phone. Ask any nurse who visits these families at home: for them the phone is a care device.",
     "chr_evalAiko", "en"),
    ("d05", 13, "Aiko: Hana, your grandmother's rule was to keep the flowers low so people can see each other. A phone "
     "on the desk is the tallest vase in the room, and the shop that keeps its counter clear is yours.",
     "chr_seedHana", "en"),
    ("d06", 7, "Bram: And the elderly? My mother's eighty-four, uses a walker and can't manage a bus. Close the street "
     "and the people with bad hips and bad lungs can't reach the chemist. Ask a district nurse which of her patients "
     "still drive in.", "chr_evalAiko", "en"),
    ("d06", 8, "Hana: Dad, the buses can run through the closed street like a dedicated line: one route, a fixed "
     "timetable, no cars in the way. You drove thirty years on track with nothing blocking you; give the bus the same.",
     "chr_seedTakeshi", "en"),
    ("d06", 12, "Bram: Ask the shopkeepers. A flower shop lives on people stopping on the way home with buckets of "
     "tulips in the boot. Close the street and every small shop selling something bulky loses its weekend to the "
     "out-of-town centre with a car park.", "chr_seedHana", "en"),
    ("d07", 7, "Hana: Freight is a fantasy. Milk goes farm to creamery by tanker, door to door; no dairy farmer will "
     "load a churn onto a branch line and unload it again at the other end. Ask any farmer what double handling does "
     "to cold milk.", "chr_evalBram", "en"),
    ("d07", 13, "Takeshi: Hana, a station brings footfall: every shop on the square, a flower stall included, gets the "
     "commuters walking past twice a day. Small shops live on the train.", "chr_seedHana", "en"),
    ("d08", 7, "Aiko: A council contract can sink a small shop: thirty-day invoices, food-safety audits, tender "
     "paperwork. Small local suppliers go under waiting for the town to pay. Ask anyone who runs a small shop.",
     "chr_seedHana", "en"),
    ("d08", 8, "Bram: Aiko, school meals are part of the health service: the coeliac child, the diabetic lad, the girl "
     "with the nut allergy. A kitchen cooking from local farms can follow those care plans better than a frozen tray "
     "from a distributor.", "chr_evalAiko", "en"),
    ("d08", 13, "Bram: Rin wants a system, so build it like one of her games: an ordering app, each farm a player with "
     "its stock and seasons, the school kitchen choosing from what's live today.", "chr_seedRin", "en"),
    ("d09", 8, "Sofia: Look at schools. We already compel attendance, and truancy fines land on the poorest families "
     "while the head chases the same children every year. Compulsion fills registers, not classrooms.",
     "chr_evalDaniel", "en"),
    ("d09", 9, "Victor: The bus-and-buggy haul is a myth: nine homes in ten sit within eight hundred metres of a "
     "polling station, the routes run every twenty minutes, and the postal vote reaches the rest. The map defeats the "
     "convenience argument.", "chr_evalSofia", "en"),
    ("d09", 10, "Amara: Daniel, your thirty-one per cent is a school-gate number. Compulsory voting won't teach one "
     "eighteen-year-old what a councillor does; citizenship lessons and a mock election in Year 11 build turnout.",
     "chr_evalDaniel", "en"),
    ("d09", 16, "Amara: Mei's composition effect is the crux: who shows up moves the median voter and so "
     "redistribution. But that's a forecast, and the fines fall on the same low-income voters. Price the enforcement "
     "before you price the gain.", "chr_seedMei", "en"),
    ("d10", 8, "Hana: Dad, you'd never let a trainee drive the night freight unsupervised, yet you'd let the law play "
     "signalman in every child's bedroom? A signal works because someone's in the box.", "chr_seedTakeshi", "en"),
    # English, added by the review pass (m11-review.md): single-answer variants in the slots whose two-of-two labels
    # were removed, and in slots without a natural item
    ("d01", 8, "Sofia: 'Coercion' is a word, not an argument. The highway code already forbids driving on pavements, in "
     "bus lanes and through pedestrian zones; a ban on private cars in two square kilometres is the same legal "
     "instrument, and no court has found a right to through-traffic.", "chr_seedVictor", "en"),
    ("d01", 13, "Sofia: Mei, the money is the case. Congestion costs the centre's firms an hour a week per worker, "
     "deliveries run at half speed, and rents fall where traffic is heaviest. Price the lost productivity and the "
     "pilot pays for itself within a year.", "chr_seedMei", "en"),
    ("d02", 8, "Daniel: The bus map has the wrong lines on it. School buses are contracted vehicles; they run at nine as "
     "easily as seven, and the depot is empty at nine because the commuter peak is over. Draw the routes again with "
     "the timetable moved.", "chr_evalSofia", "en"),
    ("d03", 8, "Mei: The depot at 4:40 is the easy case. A four-day rota on the buses is more drivers per route, and the "
     "routes don't change; draw the network and the four-day week only adds a shift pattern to the same map.",
     "chr_evalSofia", "en"),
    ("d03", 12, "Sofia: Daniel, your supply-teacher invoices come from a school that can't staff five days already. A "
     "four-day week for teachers means a fifth day of cover in every school in the county. Tell me who teaches Year 9 "
     "on Fridays.", "chr_evalDaniel", "en"),
    ("d04", 7, "Daniel: Mei's five to twelve per cent is a price elasticity from Mexico, where a can is a bigger share "
     "of a family's budget. Here a forty-pence levy barely moves demand, and the revenue is the only thing that's "
     "certain.", "chr_seedMei", "en"),
    ("d04", 8, "Amara: Victor asks who defines 'sugary'. The law already does: the soft drinks levy schedule sets five "
     "grams per hundred millilitres, written into statute, and no challenge to it has succeeded.",
     "chr_seedVictor", "en"),
    ("d04", 13, "Amara: Daniel, schools are where this tax works hardest: the tuck shop reprices, the canteen switches "
     "to water, and the head gets a reason to end the vending contract. Ask your business manager what the machine "
     "in the corridor earns.", "chr_evalDaniel", "en"),
    ("d05", 8, "Aiko: Hana, you run a shop. You'd never wrap a bouquet while the customer talks on the phone; attention "
     "is the whole service. A classroom is the same counter.", "chr_seedHana", "en"),
    ("d05", 13, "Aiko: Rin, the apps are built to win: autoplay, streaks, a reward every ninety seconds. A seven-year-old "
     "against a team of game designers isn't a fair fight, and the ban is how a school sets the difficulty.",
     "chr_seedRin", "en"),
    ("d06", 8, "Hana: Bram, your milk truck unloads before ten like every delivery in Ghent, and a farm stall does better "
     "on a closed road: people walk past it instead of driving by.", "chr_evalBram", "en"),
    ("d06", 13, "Hana: Dad, trains run on time because the line is closed to everything else; nobody parks on a railway. "
     "A high street closed on Saturdays is a line cleared for people, with the buses running through it on time.",
     "chr_seedTakeshi", "en"),
    ("d07", 8, "Takeshi: Hana, the station square was full of shops when the trains ran: a florist, a bakery, a cafe. "
     "Every small shop on that square shut within two years of the line closing.", "chr_seedHana", "en"),
    ("d08", 12, "Aiko: Hana, a kitchen buying from six farms needs someone who knows small suppliers: who pays on time, "
     "who delivers when they say. You run a small shop; you know what a late invoice does.", "chr_seedHana", "en"),
    ("d09", 15, "Victor: Amara, the night-shift nurse is exempt. Illness, caregiving and shift work are written into "
     "every compulsory-voting statute, and emergency-department staff vote by post.", "chr_seedAmara", "en"),
    ("d11", 7, "Victor: The medicine is overstated. No clinical study shows homework causes sleep disorders; adolescent "
     "sleep loss is screens and caffeine, as any physician will tell you.", "chr_seedAmara", "en"),
    ("d11", 8, "Daniel: The economics favour us. Tutoring is a market, and homework creates its demand; abolish homework "
     "and the private tutoring industry shrinks, narrowing the gap Mei worries about.", "chr_seedMei", "en"),
    ("d12", 7, "Rin: and the animals, sure, but livestock get used to noise. it's one night a year, and farms by the "
     "airfield have cows grazing under jets.", "chr_evalBram", "en"),
    ("d12", 8, "Aiko: Hana, your shop sells more on festival night than any other, but the cleanup lands on small shops "
     "too: burnt litter outside the door, a broken window on the station road last year.", "chr_seedHana", "en"),
    ("d13", 9, "Mei: There's a legal duty here. The city must provide emergency care within a set time; spend the "
     "surplus elsewhere and a judicial review could undo it.", "chr_seedVictor", "en"),
    ("d13", 13, "Amara: The staffing market decides. Acute posts pay more, so a new hospital pulls nurses out of the "
     "clinic network through the wage gap.", "chr_seedMei", "en"),
    # Malay (5)
    ("d02", 7, "Sofia: Lukis lengkung tidur dulu sebelum peta. Kajian pediatrik menunjukkan apabila loceng sekolah "
     "dilewatkan, waktu tidur remaja turut lewat, jadi tambahan tidur tinggal beberapa minit sahaja. Jam biologi tak "
     "baca jadual waktu.", "chr_seedAmara", "ms"),
    ("d06", 13, "Hana: Pasar tani paling meriah bila jalan ditutup: gerai di tengah jalan, tiada kereta, pengunjung "
     "tiga kali ganda. Bram, pasar hujung minggu tanpa kereta akan menjual lebih banyak susu dan keju daripada mana-mana "
     "tempat letak kereta.", "chr_evalBram", "ms"),
    ("d08", 12, "Aiko: Bram, ladang tenusu tak boleh bekalkan susu ke sekolah sepanjang tahun: lembu berhenti diperah, "
     "hasil susu turun pada musim sejuk, dan harga yang ditandatangani pada bulan September takkan bertahan kalau "
     "rumput kering.", "chr_evalBram", "ms"),
    ("d09", 14, "Sofia: Victor, hak untuk tidak mengundi ialah sebahagian daripada kebebasan bersuara. Undang-undang "
     "yang memaksa rakyat hadir ke peti undi ialah ucapan yang dipaksa, dan mahkamah pernah membatalkan undang-undang "
     "yang lebih ringan.", "chr_seedVictor", "ms"),
    ("d13", 14, "Mei: Klinik hanya berguna jika orang boleh sampai ke sana: tiga kali tukar bas ke klinik terdekat di "
     "wad utara, dan tiada perkhidmatan selepas pukul enam petang.", "chr_evalSofia", "ms"),
    # Chinese (3)
    ("d03", 13, "Mei：排班其实是地理问题，不是工资问题：车库在环路上，病房在山上，凌晨四点四十的首班车需要住得近的司机。"
     "四天工作制会把交接班挪到没人规划过的路线上。先给我看路线图。", "chr_evalSofia", "zh"),
    ("d04", 8, "Amara：学校才是这项税最见效的地方：走廊里的自动售货机、小卖部、食堂的饮料，一夜之间全部涨价。"
     "跟我聊过的校长都说，最便宜的选择变成了白开水。Daniel，教室是感受得到的。", "chr_evalDaniel", "zh"),
    ("d07", 12, "Hana：爸，旧线路用的还是臂板信号机；重开需要全面更换信号系统、新的联锁装置，还有一个平交道口。"
     "铁路人都知道，真正拖垮重开计划的是这笔开销，不是铁轨。", "chr_seedTakeshi", "zh"),
    # mixed (2)
    ("d01", 7, "Mei: It depends, and here's on what: the health claims. Your side says kurang kereta means fewer asthma "
     "admissions, tapi data jabatan kecemasan shows trauma just moves to the ring road. Tanya A&E apa jadi kat simpang "
     "bypass tu.", "chr_seedAmara", "mixed"),
    ("d10", 10, "Rin: takeshi, a train has an automatic brake for a reason: 半夜三点 the driver can't be trusted, so the "
     "system stops the train. consoles should have that 安全手柄 built in, not a law.", "chr_seedTakeshi", "mixed"),
]


def id_prefix(base: str, n: int, tests: int = TESTS) -> str:
    """M10's prefix search: the first prefix whose hash split gives at least `tests` test items (ids alone)."""
    k = 0
    while True:
        pre = base if k == 0 else f"{base}{k}"
        if sum(split_for(f"{pre}-{i:03d}") == "test" for i in range(1, n + 1)) >= tests:
            return pre
        k += 1


def last_opposing_seq(h: dict[str, Any], sl: dict[str, Any]) -> int:
    """The seq of the argument `last_opposing` quotes at this slot (anyone else's in a panel)."""
    before = [x for x in h["lines"][: sl["index"]] if x["kind"] == "argument"]
    for x in reversed(before):
        if sl["side"] is None or x["side"] != sl["side"]:
            return int(x["seq"])
    raise ValueError(f"{h['id']}#{sl['seq']}: no opposing argument before the slot")


def item(h: dict[str, Any], sl: dict[str, Any], prof: dict[str, Any], acceptable: list[str], single: bool, lang: str,
         source: str, replace: dict[int, str] | None = None) -> dict[str, Any]:
    req = ds.cut_request(h, sl, prof, replace)
    state, _, qid, seed = ds.cut_state(req)
    assert qid is not None, f"{source}: one eligible member asks no member question"
    cands = list(sl["eligible"])
    return {"question_id": qid, "lang": lang, "kind": "debate",
            "item": {"state": state, "values": [{"key": c, "name": str(prof[c]["name"]),
                                                 "role": str(prof[c].get("role") or "")} for c in cands],
                     "seed": seed, "side": SIDE_LABEL.get(str(sl["side"])) if sl["side"] else None, "none": False},
            "label": {"candidates": cands, "acceptable": list(acceptable), "single": single, "fixed": cands[0]},
            "cut": {"debate": h["id"], "seq": sl["seq"], "replace": {str(k): v for k, v in (replace or {}).items()}},
            "source": source}


def build(hs: list[dict[str, Any]], prof: dict[str, Any], labels: dict[str, tuple[list[str], bool]] | None = None,
          variants: list[tuple[str, int, str, str, str]] | None = None, tests: int = TESTS) -> list[dict[str, Any]]:
    labels = LABELS if labels is None else labels
    variants = VARIANTS if variants is None else variants
    by_id = {h["id"]: h for h in hs}
    rows: list[dict[str, Any]] = []
    for h in hs:
        for sl in ds.natural_member_slots(h):
            key = f"{h['id']}#{sl['seq']}"
            if key in labels:
                ok, single = labels[key]
                rows.append(item(h, sl, prof, ok, single, h.get("language", "en"), f"debate:{key}"))
    for did, seq, text, ok_id, lang in variants:
        h = by_id[did]
        sl = next(s for s in ds.natural_member_slots(h) if s["seq"] == seq)
        rows.append(item(h, sl, prof, [ok_id], True, lang, f"debate:{did}#{seq} (written variant)",
                         {last_opposing_seq(h, sl): text}))
    pre = id_prefix("dmm", len(rows), tests) if rows else "dmm"
    out = []
    for n, r in enumerate(rows, 1):
        item_id = f"{pre}-{n:03d}"
        out.append({"id": item_id, "split": split_for(item_id), **r})
    return out


def check(rows: list[dict[str, Any]]) -> list[str]:
    """D21's counts: 90 items, at least 45 single-answer, English 80 / Malay 5 / Chinese 3 / mixed 2, ≥ 30 test."""
    problems = []
    if len(rows) != 90:
        problems.append(f"want 90 items, have {len(rows)}")
    if sum(r["label"]["single"] for r in rows) < 45:
        problems.append("fewer than 45 single-answer items")
    langs = Counter(r["lang"] for r in rows)
    if langs != Counter({"en": 80, "ms": 5, "zh": 3, "mixed": 2}):
        problems.append(f"languages {dict(langs)}")
    if sum(r["split"] == "test" for r in rows) < TESTS:
        problems.append(f"fewer than {TESTS} test items")
    for r in rows:
        lab = r["label"]
        if not 1 <= len(lab["acceptable"]) <= 2 or not set(lab["acceptable"]) <= set(lab["candidates"]):
            problems.append(f"{r['id']}: one or two acceptable members, from the candidates")
        if lab["single"] != (len(lab["acceptable"]) == 1):
            problems.append(f"{r['id']}: `single` must mean one acceptable member")
    return problems


def main() -> int:
    hs = ds.histories()
    if not hs:
        print("no committed debate histories yet (evals/debates/): run `horizon eval debate-history` first (10.1)")
        return 1
    rows = build(hs, ds.profiles())
    problems = check(rows)
    if problems:
        print("\n".join(problems))
        return 1
    (HERE / "debate_member.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                              encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} debate member items: splits {dict(Counter(r['split'] for r in rows))}, "
          f"single {sum(r['label']['single'] for r in rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
