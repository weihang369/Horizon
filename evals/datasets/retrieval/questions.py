"""The retrieval questions, written blind (rag design D22): each names its character, its message (and, for a
follow-up, the two earlier lines), and its labels as exact quotes from the source, graded 2 (answers) or 1 (partly).
`build.py` turns them into `retrieval.jsonl`. An unanswerable question is on the same topics and has no span.
The rule they follow is `evals/reviews/m12-labels.md` (committed first).

Ids: `ret-<kind letter><n>`: a answerable, u unanswerable, f follow-up, x non-English, n naming.
"""

from typing import Any

# Amara
M1 = "amara/niosh-module-1-introduction.md"
M2 = "amara/niosh-module-2-health-and-safety-risks.md"
M3 = "amara/niosh-module-3.md"
M5 = "amara/niosh-module-5-work-organization.md"
FATIGUE = "kno_seedAmara1"
TRIAGE = "kno_seedAmara2"
# Hana
PLATE = "hana/ars-choose-myplate.md"
FISH = "hana/ars-eat-fish.md"
HANA_NUTS = "hana/ars-go-nuts.md"
POP = "hana/ars-popcorn-whole-grain-snack.md"
RECIPES = "kno_seedHana1"
# Mei
HB = "mei/opm-alternative-work-schedules-handbook.md"
CWS = "mei/opm-compressed-work-schedules.md"
FWS = "mei/opm-flexible-work-schedules.md"
HOL = "mei/opm-holidays-work-schedules-and-pay.md"
PILOTS = "kno_seedMei2"
# Victor
IV = "victor/fre-article-iv-relevance.md"
VII = "victor/fre-article-vii-opinions.md"
VIII = "victor/fre-article-viii-hearsay.md"
MOOT = "kno_seedVictor1"


def corpus(doc: str, quote: str, grade: int = 2) -> dict[str, Any]:
    return {"doc": doc, "quote": quote, "grade": grade}


def seed(source: str, chunk: str, quote: str, grade: int = 2) -> dict[str, Any]:
    return {"doc": f"seed:{source}", "chunk": chunk, "quote": quote, "grade": grade}


CREDIT_CARRY = [
    corpus(FWS, "The law prohibits carrying over more than 24 credit hours from one pay period to the next"),
    corpus(HB, "limits the number of credit hours an employee may carry over from a biweekly pay period to a succeeding "
               "biweekly pay period to 24 hours for a full-time employee"),
    corpus(HB, "full-time employees may not carry over more than 24 credit hours to a new biweekly pay period"),
]
CWS_NO_CREDIT = [
    corpus(CWS, "Credit hours are not permitted under a CWS program."),
    corpus(HB, "There is no legal authority for credit hours under a CWS program. The law provides for credit hours only"),
    corpus(HB, "The law provides credit hours only for flexible work schedules. There is no legal authority"),
]
ADULT_SLEEP = [
    corpus(M2, "Most adults need about 7 to 8 hours of good-quality sleep per night"),
    corpus(M2, "recommends that adults get 7 or more hours of sleep each day"),
]
HEADACHE_ESCALATE = [seed(TRIAGE, "kch_amaraTri04", "Escalate any headache that is sudden and severe (\"thunderclap\"), "
                                                    "or that comes with fever, neck stiffness, confusion, new weakness "
                                                    "or changes in vision. These patients are graded 2 or higher and "
                                                    "seen by a doctor without delay.")]
HEARSAY = [corpus(VIII, "the declarant does not make while testifying at the current trial or hearing"),
           corpus(VIII, "a party offers in evidence to prove the truth of the matter asserted in the statement")]


QUESTIONS: list[dict[str, Any]] = [
    # ══ answerable (100: 10 need two passages, 10 answered only in part) ══
    # ── Hana ──
    {"id": "ret-a001", "kind": "answerable", "who": "hana",
     "message": "Which nut has more protein than the others?",
     "spans": [corpus(HANA_NUTS, "they contain more protein than any other FDA-classified nut")]},
    {"id": "ret-a002", "kind": "answerable", "who": "hana",
     "message": "How big is one serving of nuts, roughly?",
     "spans": [corpus(HANA_NUTS, "A serving of nuts is one ounce or about a small handful."),
               corpus(HANA_NUTS, "on average this provides 150-200 calories per serving", 1)]},
    {"id": "ret-a003", "kind": "answerable", "who": "hana", "seed": True,
     "message": "When does the yuzu juice go into the cake?",
     "spans": [seed(RECIPES, "kch_hanaRecipe01", "The juice goes in the glaze, never the batter.")]},
    {"id": "ret-a004", "kind": "answerable", "who": "mei", "seed": True,
     "message": "By how much did burnout drop in the pilots?",
     "spans": [seed(PILOTS, "kch_meiPilot03",
                    "self-reported burnout fell by an average of 32% and sick days by 21%")]},
    {"id": "ret-a005", "kind": "answerable", "who": "hana", "needs_two": True,
     "message": "Which nuts are good for vitamin E and which one is mostly polyunsaturated fat?",
     "spans": [corpus(HANA_NUTS, "unlike other nuts, contain predominantly polyunsaturated fat"),
               corpus(HANA_NUTS, "Almonds are a source of vitamin E, folic acid, calcium, and magnesium.")]},
    {"id": "ret-a006", "kind": "answerable", "who": "hana",
     "message": "How much fish should I be eating each week for my heart?",
     "spans": [corpus(FISH, "recommends eating two, 3.5 oz servings of fish per week")]},
    {"id": "ret-a007", "kind": "answerable", "who": "hana",
     "message": "Which fish should a pregnant woman stay away from?",
     "spans": [corpus(FISH, "should avoid species such as shark and king mackerel"),
               corpus(FISH, "can accumulate particularly in older, large predatory fish like shark, swordfish, king "
                            "mackerel and tilefish", 1)]},
    {"id": "ret-a008", "kind": "answerable", "who": "hana",
     "message": "Is it better to fry fish or grill it?",
     "spans": [corpus(FISH, "Baking or grilling is recommended instead of frying.")]},
    {"id": "ret-a009", "kind": "answerable", "who": "hana",
     "message": "How much EPA and DHA a day is enough to make a difference?",
     "spans": [corpus(FISH, "Eating at least 250 mg of these omega 3's per day is enough to provide health benefits.")]},
    {"id": "ret-a010", "kind": "answerable", "who": "hana",
     "message": "Does farmed salmon actually raise your omega-3 levels?",
     "spans": [corpus(FISH, "eating even 4 ounces of farmed Atlantic salmon twice a week raises omega 3s to levels "
                            "associated with reduced heart disease risk")]},
    {"id": "ret-a011", "kind": "answerable", "who": "hana",
     "message": "How many calories are in a bowl of air-popped popcorn?",
     "spans": [corpus(POP, "A serving of air-popped popcorn is 3 cups and has about 100 calories before toppings.")]},
    {"id": "ret-a012", "kind": "answerable", "who": "hana",
     "message": "Which other foods are cheap ways to get whole grains?",
     "spans": [corpus(POP, "popcorn was one of the five most cost-effective sources of whole grains, along with oatmeal, "
                           "brown rice, yeast breads, and cooked grains/whole-grain pasta")]},
    {"id": "ret-a013", "kind": "answerable", "who": "hana",
     "message": "When do I put the seasoning on popcorn so it actually sticks?",
     "spans": [corpus(POP, "No matter what topping you choose, add it to the popcorn immediately after popping."),
               corpus(POP, "The moisture from the steam released during the popping process will help the seasonings "
                           "stick.", 1)]},
    {"id": "ret-a014", "kind": "answerable", "who": "hana",
     "message": "What can make popcorn taste cheesy without cheese?",
     "spans": [corpus(POP, "Nutritional yeast seasoning can add a cheesy flavor to popcorn")]},
    {"id": "ret-a015", "kind": "answerable", "who": "hana",
     "message": "Where do Brazil nuts come from?",
     "spans": [corpus(HANA_NUTS, "Brazil Nuts are from wild trees in the Amazon rainforest.")]},
    {"id": "ret-a016", "kind": "answerable", "who": "hana",
     "message": "Why do my nuts go rancid in the cupboard?",
     "spans": [corpus(HANA_NUTS, "Because of the high fat content they may become rancid if stored too long at room "
                                 "temperature.")]},
    {"id": "ret-a017", "kind": "answerable", "who": "hana",
     "message": "What's the MyPlate tool for keeping track of what I eat called?",
     "spans": [corpus(PLATE, "The website goes beyond providing general information with its interactive feature called "
                             "SuperTracker."),
               corpus(FISH, "the USDA provides a free interactive tool called SuperTracker", 1)]},
    {"id": "ret-a018", "kind": "answerable", "who": "hana",
     "message": "What is the freshman 15?",
     "spans": [corpus(PLATE, "the weight gain that many new college students experience")]},
    {"id": "ret-a019", "kind": "answerable", "who": "hana", "needs_two": True,
     "message": "Which nuts give you both copper and magnesium?",
     "spans": [corpus(HANA_NUTS, "They are an excellent source of copper and magnesium."),
               corpus(HANA_NUTS, "an excellent source of vitamin E, copper and magnesium")]},
    {"id": "ret-a020", "kind": "answerable", "who": "hana", "needs_two": True,
     "message": "How much fibre does popcorn give me, and do nuts have fibre too?",
     "spans": [corpus(POP, "One serving of air-popped popcorn contains about 15 percent of the amount of fiber most "
                           "people need every day."),
               corpus(HANA_NUTS, "Each variety of nut is high in plant based protein and fiber")]},
    {"id": "ret-a021", "kind": "answerable", "who": "hana", "seed": True,
     "message": "How do I keep sushi rice bright when the fish is rich?",
     "spans": [seed(RECIPES, "kch_hanaRecipe02", "A spoon of pineapple juice in the vinegar keeps it bright when the "
                                                 "fish is rich.")]},
    {"id": "ret-a022", "kind": "answerable", "who": "hana", "seed": True,
     "message": "How tall can the flowers on a dinner table be?",
     "spans": [seed(RECIPES, "kch_hanaRecipe04", "Flowers on the table should never be taller than your elbow.")]},
    {"id": "ret-a023", "kind": "answerable", "who": "hana", "seed": True,
     "message": "Should I salt the rice when I make onigiri?",
     "spans": [seed(RECIPES, "kch_hanaRecipe05", "Salt your hands, not the rice")]},
    {"id": "ret-a024", "kind": "answerable", "who": "hana", "partly": True,
     "message": "What makes pistachios green, and are they safe to give my dog?",
     "spans": [corpus(HANA_NUTS, "pistachios contain the antioxidants lutein and zeazanthine which give them their green "
                                 "color")]},
    {"id": "ret-a025", "kind": "answerable", "who": "hana", "partly": True,
     "message": "How much salmon does the average American eat a year, and what does farmed salmon cost per pound?",
     "spans": [corpus(FISH, "Americans consume about 4 lbs of shrimp and 2 lbs tuna and salmon per person each year.")]},
    {"id": "ret-a026", "kind": "answerable", "who": "hana", "partly": True,
     "message": "Is popcorn a whole grain, and how much sodium is in a bag of microwave popcorn?",
     "spans": [corpus(POP, "Did you know that popcorn is a 100 percent whole grain?")]},
    # ── Amara ──
    {"id": "ret-a027", "kind": "answerable", "who": "amara",
     "message": "What hours count as shift work?",
     "spans": [corpus(M1, "Shift work is any schedule outside of the period of 7 a.m. to 6 p.m.")]},
    {"id": "ret-a028", "kind": "answerable", "who": "amara",
     "message": "At what point do work hours count as long hours?",
     "spans": [corpus(M1, "Long work hours are any shift greater than 8.5 hours, or a work week greater than 40 hours.")]},
    {"id": "ret-a029", "kind": "answerable", "who": "amara",
     "message": "How much does one night of four hours' sleep knock down natural killer cells?",
     "spans": [corpus(M2, "reduced natural killer (NK) cell activity to an average of 72%")]},
    {"id": "ret-a030", "kind": "answerable", "who": "amara",
     "message": "Does short sleep make the flu jab work less well?",
     "spans": [corpus(M2, "resulted in a greater than 50% decrease in production of antibodies to influenza "
                          "vaccination")]},
    {"id": "ret-a031", "kind": "answerable", "who": "amara",
     "message": "How much sleep does an adult really need a night?",
     "spans": [*ADULT_SLEEP, corpus(M3, "sleep experts who recommend at least 7 hours of sleep a day", 1)]},
    {"id": "ret-a032", "kind": "answerable", "who": "amara",
     "message": "How can I work out how much sleep I personally need?",
     "spans": [corpus(M2, "observe the length of time you sleep toward the end of a relaxing 2-week vacation"),
               corpus(M2, "The average of the sleep times across 5 to 7 days is an estimate of your sleep-length need.",
                      1)]},
    {"id": "ret-a033", "kind": "answerable", "who": "amara",
     "message": "What share of healthcare workers get six hours of sleep or less?",
     "spans": [corpus(M2, "About 32 percent of U.S. healthcare workers report sleeping 6 hours or less a day"),
               corpus(M3, "over 50% of night shift healthcare workers reported sleeping 6 or fewer hours a day", 1)]},
    {"id": "ret-a034", "kind": "answerable", "who": "amara",
     "message": "Staying awake for a full day is like having what blood alcohol level?",
     "spans": [corpus(M3, "Being awake for 24 hours is similar to having a BAC of 0.10%.")]},
    {"id": "ret-a035", "kind": "answerable", "who": "amara",
     "message": "What exactly is a microsleep?",
     "spans": [corpus(M3, "involuntary episodes of sleep lasting a few seconds")]},
    {"id": "ret-a036", "kind": "answerable", "who": "amara",
     "message": "Do junior doctors get better at handling sleep loss as they get more experienced?",
     "spans": [corpus(M3, "did not show evidence that they adapted to sleep deprivation better as their training years "
                          "progressed")]},
    {"id": "ret-a037", "kind": "answerable", "who": "amara",
     "message": "How long a break should there be between the end of one shift and the start of the next?",
     "spans": [corpus(M5, "Knauth and Hornberger recommend at least 11 hours between two work shifts.")]},
    {"id": "ret-a038", "kind": "answerable", "who": "amara", "partly": True,
     "message": "How many days off should follow three 12-hour shifts in a row, and should those days be paid?",
     "spans": [corpus(M5, "Consider two rest days after three consecutive 12-hour shifts.")]},
    {"id": "ret-a039", "kind": "answerable", "who": "amara",
     "message": "Should a rotating rota go forwards or backwards through the shifts?",
     "spans": [corpus(M5, "forward rotations (day shift to evening shift) are easier to adjust to than backward "
                          "rotations (evening shift to day shift)")]},
    {"id": "ret-a040", "kind": "answerable", "who": "amara",
     "message": "Which speed of rotation is the hardest on people?",
     "spans": [corpus(M5, "The most difficult speed of rotation is a weekly rotation")]},
    {"id": "ret-a041", "kind": "answerable", "who": "amara",
     "message": "What limits did the Institute of Medicine suggest for nurses' hours?",
     "spans": [corpus(M5, "recommends that work hours for nurses be limited to 12 hours in any 24-hour period and 60 "
                          "hours per 7-day period")]},
    {"id": "ret-a042", "kind": "answerable", "who": "amara", "needs_two": True,
     "message": "In Bae and Fabry's review, how did long shifts compare for patient outcomes versus the nurses' own "
                "health?",
     "spans": [corpus(M5, "Five findings showed long shifts increased negative outcomes, 7 findings showed no significant "
                          "differences, and 1 finding showed decreased negative outcomes."),
               corpus(M5, "21 findings showed increased negative outcomes, 5 findings showed no significant differences, "
                          "and 3 findings showed decreased negative outcomes.")]},
    {"id": "ret-a043", "kind": "answerable", "who": "amara", "needs_two": True,
     "message": "Is a 6 a.m. start a bad idea, and should rotas give people weekends off?",
     "spans": [corpus(M5, "Early start times (6 a.m. or earlier) tend to shorten sleep"),
               corpus(M5, "experts recommend scheduling some weekends off")]},
    {"id": "ret-a044", "kind": "answerable", "who": "amara", "seed": True,
     "message": "How many staff did your fatigue review look at?",
     "spans": [seed(FATIGUE, "kch_amaraFat01", "This review covers 1,140 clinical staff across four Meridian Health "
                                               "Trust sites between January and October 2025.")]},
    {"id": "ret-a045", "kind": "answerable", "who": "amara", "seed": True,
     "message": "How much more tired were people after more than three long shifts in a row?",
     "spans": [seed(FATIGUE, "kch_amaraFat02", "reported fatigue scores 38% higher than colleagues on shorter blocks")]},
    {"id": "ret-a046", "kind": "answerable", "who": "amara", "seed": True, "partly": True,
     "message": "How many ED staff had high burnout by October, and how does that compare with other trusts?",
     "spans": [seed(FATIGUE, "kch_amaraFat03", "By October, 41% of emergency department staff met the review's "
                                               "threshold for high burnout, up from 29% in January.")]},
    {"id": "ret-a047", "kind": "answerable", "who": "amara", "seed": True,
     "message": "Did the compressed rota pilot actually help with burnout?",
     "spans": [seed(FATIGUE, "kch_amaraFat06", "After twelve weeks, burnout scores on both wards fell by roughly a "
                                               "fifth")]},
    {"id": "ret-a048", "kind": "answerable", "who": "amara", "seed": True,
     "message": "Why are nurses leaving, according to the exit interviews?",
     "spans": [seed(FATIGUE, "kch_amaraFat09", "Exit interviews named workload and unpredictable rotas as the two "
                                               "leading reasons for leaving, ahead of pay.")]},
    {"id": "ret-a049", "kind": "answerable", "who": "amara", "seed": True,
     "message": "When does a caffeine withdrawal headache start, and how long does it hang around?",
     "spans": [seed(TRIAGE, "kch_amaraTri03", "Caffeine withdrawal headache usually begins 12 to 24 hours after a sharp "
                                              "cut in intake and can last two to nine days.")]},
    {"id": "ret-a050", "kind": "answerable", "who": "amara", "seed": True,
     "message": "Which headache symptoms mean a patient needs to see a doctor straight away?",
     "spans": HEADACHE_ESCALATE},
    {"id": "ret-a051", "kind": "answerable", "who": "amara", "seed": True, "needs_two": True,
     "message": "Would rolling out the compressed rota cost much in agency hours, and does the review back extending it?",
     "spans": [seed(FATIGUE, "kch_amaraFat07", "The pilot wards needed 6% more agency hours during the transition month "
                                               "to cover handovers."),
               seed(FATIGUE, "kch_amaraFat10", "The review recommends extending the compressed-rota pilot to three "
                                               "further departments")]},
    # ── Mei ──
    {"id": "ret-a052", "kind": "answerable", "who": "mei",
     "message": "How many credit hours can a full-time federal employee carry into the next pay period?",
     "spans": CREDIT_CARRY},
    {"id": "ret-a053", "kind": "answerable", "who": "mei",
     "message": "Can someone on a compressed schedule earn credit hours?",
     "spans": CWS_NO_CREDIT},
    {"id": "ret-a054", "kind": "answerable", "who": "mei",
     "message": "What's the pay rate for a federal employee who has to work on a holiday?",
     "spans": [corpus(HOL, "double or 200 percent of their rate of basic pay"),
               corpus(CWS, "Holiday premium pay (equal to 100 percent of the rate of basic pay) is paid", 1),
               corpus(FWS, "Holiday premium pay (equal to 100 percent of the rate of basic pay) is limited", 1)]},
    {"id": "ret-a055", "kind": "answerable", "who": "mei",
     "message": "If I'm called in on a holiday for a quick job, what's the least holiday premium I get?",
     "spans": [corpus(HOL, "are entitled to a minimum of 2 hours of holiday premium pay")]},
    {"id": "ret-a056", "kind": "answerable", "who": "mei",
     "message": "What percentage is Sunday premium pay?",
     "spans": [corpus(HB, "Sunday premium pay (25 percent of the rate of basic pay) for the entire period of work up to 8 "
                          "hours"),
               corpus(HB, "(25 percent of the rate of basic pay) for the entire scheduled period of duty that day")]},
    {"id": "ret-a057", "kind": "answerable", "who": "mei",
     "message": "How long is each day on a three-day work week?",
     "spans": [corpus(HB, "A full-time employee must work 13 hours and 20 minutes a day, 40 hours a week, and 80 hours a "
                          "biweekly pay period.")]},
    {"id": "ret-a058", "kind": "answerable", "who": "mei",
     "message": "What does a 5/4-9 compressed plan actually look like?",
     "spans": [corpus(HB, "A full-time employee work eight 9-hour days and one 8-hour day for a total of 80 hours in a "
                          "biweekly pay period.")]},
    {"id": "ret-a059", "kind": "answerable", "who": "mei",
     "message": "Does an agency need OPM to sign off before it sets up flexible schedules?",
     "spans": [corpus(HB, "do not need OPM approval")]},
    {"id": "ret-a060", "kind": "answerable", "who": "mei",
     "message": "What counts as a majority in the vote on a compressed schedule?",
     "spans": [corpus(HB, "a majority is obtained when the number of affirmative votes exceeds 50 percent of the number of "
                          "employees and supervisors in the organization proposed for inclusion")]},
    {"id": "ret-a061", "kind": "answerable", "who": "mei",
     "message": "Can a worker get out of a compressed schedule because of personal hardship?",
     "spans": [corpus(CWS, "An employee may request to be excluded for a personal hardship."),
               corpus(HB, "requires that any employee for whom a compressed work schedule would impose a personal "
                          "hardship be excluded from the schedule or be reassigned"),
               corpus(HB, "An employee for whom a CWS program would impose a personal hardship may request to be "
                          "excluded from the program.")]},
    {"id": "ret-a062", "kind": "answerable", "who": "mei",
     "message": "Which employees are most likely to have a hardship case against a compressed schedule?",
     "spans": [corpus(HB, "particularly disabled employees and those who are responsible for the care of disabled family "
                          "members or dependent children")]},
    {"id": "ret-a063", "kind": "answerable", "who": "mei",
     "message": "Is Juneteenth a federal holiday?",
     "spans": [corpus(HOL, "Juneteenth National Independence Day (June 19).")]},
    {"id": "ret-a064", "kind": "answerable", "who": "mei",
     "message": "If a holiday lands on my Saturday off, which day do I get instead?",
     "spans": [corpus(HB, "except for holidays falling on a Sunday nonworkday-the employee's preceding workday"),
               corpus(HB, "if a holiday falls on a nonworkday of the employee, the employee's preceding workday"),
               corpus(HOL, "are entitled to an \"in lieu of\" holiday when a holiday falls on the employee's nonworkday",
                      1)]},
    {"id": "ret-a065", "kind": "answerable", "who": "mei",
     "message": "Is Fairfax County part of the Inauguration Day area?",
     "spans": [corpus(HOL, "Arlington and Fairfax Counties in Virginia")]},
    {"id": "ret-a066", "kind": "answerable", "who": "mei",
     "message": "When Inauguration Day falls on a Sunday, when is the holiday?",
     "spans": [corpus(HOL, "the next succeeding day (i.e., Monday, January 21st) is designated as the public observance of "
                           "the inauguration")]},
    {"id": "ret-a067", "kind": "answerable", "who": "mei", "seed": True,
     "message": "How many organisations took part in the four-day week pilots?",
     "spans": [seed(PILOTS, "kch_meiPilot01", "covering 212 organisations and about 9,800 workers")]},
    {"id": "ret-a068", "kind": "answerable", "who": "mei", "seed": True,
     "message": "What happened to resignations during the pilots?",
     "spans": [seed(PILOTS, "kch_meiPilot08", "voluntary resignations fell from 6.1% to 4.3% on average over the trial "
                                              "period")]},
    {"id": "ret-a069", "kind": "answerable", "who": "mei", "seed": True,
     "message": "Were any hospitals part of the four-day week pilots?",
     "spans": [seed(PILOTS, "kch_meiPilot05", "None of the pilots included an acute hospital, a public transport "
                                              "operator or a residential care provider.")]},
    {"id": "ret-a070", "kind": "answerable", "who": "mei", "seed": True,
     "message": "What do the pilot authors want done before any national standard?",
     "spans": [seed(PILOTS, "kch_meiPilot09", "The authors recommend sector-specific trials in health, transport and "
                                              "care, with independent measurement of output and service quality")]},
    {"id": "ret-a071", "kind": "answerable", "who": "mei", "seed": True, "needs_two": True,
     "message": "How many of the pilot firms ran shifts, and how many extra staffed hours did they need to keep cover?",
     "spans": [seed(PILOTS, "kch_meiPilot02", "Only nine provided round-the-clock or shift-based services."),
               seed(PILOTS, "kch_meiPilot06", "holding coverage constant took between 18% and 27% more staffed hours")]},
    {"id": "ret-a072", "kind": "answerable", "who": "mei", "needs_two": True,
     "message": "Can I earn credit hours while I'm travelling for work, and can my agency put me back on a fixed "
                "schedule when I travel?",
     "spans": [corpus(HB, "An employee may not earn credit hours for travel because travel in connection with Government "
                          "work is not voluntary in nature."),
               corpus(HB, "An agency may require an employee to follow a traditional fixed schedule (8 hours a day, 40 "
                          "hours a week) during pay periods he or she travels."),
               corpus(HB, "Agencies may find it advisable to establish procedures to revert employees to standard fixed "
                          "schedules when traveling.", 1)]},
    {"id": "ret-a073", "kind": "answerable", "who": "mei", "seed": True, "partly": True,
     "message": "Did most of the pilot firms keep the four-day week, and what happened to their customer satisfaction?",
     "spans": [seed(PILOTS, "kch_meiPilot07", "Ninety-two percent of organisations kept the four-day week after the "
                                              "pilot.")]},
    {"id": "ret-a074", "kind": "answerable", "who": "mei", "partly": True,
     "message": "Is Columbus Day a federal holiday, and do private employers have to give it too?",
     "spans": [corpus(HOL, "Columbus Day (Second Monday in October).")]},
    {"id": "ret-a075", "kind": "answerable", "who": "mei", "partly": True,
     "message": "What is a maxiflex schedule, and which agencies use it the most?",
     "spans": [corpus(HB, "A type of flexible work schedule that contains core hours on fewer than 10 workdays in the "
                          "biweekly pay period")]},
    {"id": "ret-a076", "kind": "answerable", "who": "mei",
     "message": "Can an agency mix flexible and compressed rules into one hybrid schedule?",
     "spans": [corpus(HB, "There is no authority to establish hybrid work schedules")]},
    # ── Victor ──
    {"id": "ret-a077", "kind": "answerable", "who": "victor",
     "message": "When is a piece of evidence relevant?",
     "spans": [corpus(IV, "it has any tendency to make a fact more or less probable than it would be without the "
                          "evidence"),
               corpus(IV, "the fact is of consequence in determining the action")]},
    {"id": "ret-a078", "kind": "answerable", "who": "victor",
     "message": "Can a judge throw out evidence even though it's relevant?",
     "spans": [corpus(IV, "The court may exclude relevant evidence if its probative value is substantially outweighed by a "
                          "danger of one or more of the following")]},
    {"id": "ret-a079", "kind": "answerable", "who": "victor",
     "message": "Can I use someone's character to show they acted that way on the day in question?",
     "spans": [corpus(IV, "Evidence of a person's character or character trait is not admissible to prove that on a "
                          "particular occasion the person acted in accordance with the character or trait.")]},
    {"id": "ret-a080", "kind": "answerable", "who": "victor",
     "message": "If the landlord fixed the stairs after my fall, can I use that to prove he was negligent?",
     "spans": [corpus(IV, "evidence of the subsequent measures is not admissible to prove")]},
    {"id": "ret-a081", "kind": "answerable", "who": "victor",
     "message": "Does it matter in court whether the driver was insured?",
     "spans": [corpus(IV, "Evidence that a person was or was not insured against liability is not admissible to prove "
                          "whether the person acted negligently or otherwise wrongfully.")]},
    {"id": "ret-a082", "kind": "answerable", "who": "victor",
     "message": "How far before trial does a Rule 412 motion have to be filed?",
     "spans": [corpus(IV, "do so at least 14 days before trial unless the court, for good cause, sets a different time")]},
    {"id": "ret-a083", "kind": "answerable", "who": "victor",
     "message": "Who counts as a child under the child-molestation rule?",
     "spans": [corpus(IV, "means a person below the age of 14")]},
    {"id": "ret-a084", "kind": "answerable", "who": "victor",
     "message": "What does an ordinary witness's opinion have to be based on?",
     "spans": [corpus(VII, "rationally based on the witness's perception")]},
    {"id": "ret-a085", "kind": "answerable", "who": "victor",
     "message": "Can an expert say whether the defendant had the mental state for the crime?",
     "spans": [corpus(VII, "In a criminal case, an expert witness must not state an opinion about whether the defendant "
                           "did or did not have a mental state or condition that constitutes an element of the crime "
                           "charged or of a defense.")]},
    {"id": "ret-a086", "kind": "answerable", "who": "victor",
     "message": "Who pays a court-appointed expert in an ordinary civil case?",
     "spans": [corpus(VII, "in any other civil case, by the parties in the proportion and at the time that the court "
                           "directs")]},
    {"id": "ret-a087", "kind": "answerable", "who": "victor",
     "message": "What is hearsay, in plain terms?",
     "spans": HEARSAY},
    {"id": "ret-a088", "kind": "answerable", "who": "victor",
     "message": "What makes something an excited utterance?",
     "spans": [corpus(VIII, "A statement relating to a startling event or condition, made while the declarant was under "
                            "the stress of excitement that it caused.")]},
    {"id": "ret-a089", "kind": "answerable", "who": "victor",
     "message": "How old does a document have to be to count as ancient?",
     "spans": [corpus(VIII, "A statement in a document that was prepared before January 1, 1998, and whose authenticity "
                            "is established.")]},
    {"id": "ret-a090", "kind": "answerable", "who": "victor",
     "message": "Can a passage from a learned treatise go to the jury room as an exhibit?",
     "spans": [corpus(VIII, "If admitted, the statement may be read into evidence but not received as an exhibit.")]},
    {"id": "ret-a091", "kind": "answerable", "who": "victor",
     "message": "Does a witness who says they can't remember count as unavailable?",
     "spans": [corpus(VIII, "testifies to not remembering the subject matter")]},
    {"id": "ret-a092", "kind": "answerable", "who": "victor",
     "message": "What notice do I have to give to use the residual hearsay exception?",
     "spans": [corpus(VIII, "The statement is admissible only if the proponent gives an adverse party reasonable notice of "
                            "the intent to offer the statement")]},
    {"id": "ret-a093", "kind": "answerable", "who": "victor", "needs_two": True,
     "message": "Can a settlement offer be used against my client, and what about his offer to pay her hospital bills?",
     "spans": [corpus(IV, "either to prove or disprove the validity or amount of a disputed claim"),
               corpus(IV, "Evidence of furnishing, promising to pay, or offering to pay medical, hospital, or similar "
                          "expenses resulting from an injury is not admissible to prove liability for the injury.")]},
    {"id": "ret-a094", "kind": "answerable", "who": "victor", "needs_two": True,
     "message": "Where's the line between a lay opinion and an expert one?",
     "spans": [corpus(VII, "not based on scientific, technical, or other specialized knowledge within the scope of Rule "
                           "702"),
               corpus(VII, "A witness who is qualified as an expert by knowledge, skill, experience, training, or "
                           "education may testify in the form of an opinion")]},
    {"id": "ret-a095", "kind": "answerable", "who": "victor", "seed": True,
     "message": "Which year made the two-day weekend the default?",
     "spans": [seed(MOOT, "kch_victorMoot02", "the Meridian Working Hours Act 1931 made the two-day weekend the "
                                              "default")]},
    {"id": "ret-a096", "kind": "answerable", "who": "victor", "seed": True,
     "message": "How do we answer them when they say the evidence base is too narrow?",
     "spans": [seed(MOOT, "kch_victorMoot01", "Concede scope early, then shift the burden: the status quo is also a "
                                              "policy and has to justify itself.")]},
    {"id": "ret-a097", "kind": "answerable", "who": "victor", "seed": True,
     "message": "Which part of the Working Time Code covers shift rules?",
     "spans": [seed(MOOT, "kch_victorMoot03", "Continuous-coverage sectors already run on shift rules under Part IV of "
                                              "the Working Time Code")]},
    {"id": "ret-a098", "kind": "answerable", "who": "victor", "seed": True,
     "message": "What tone should the closing take?",
     "spans": [seed(MOOT, "kch_victorMoot06", "Don't sound triumphant. Judges reward conceding a fair point "
                                              "gracefully.")]},
    {"id": "ret-a099", "kind": "answerable", "who": "victor", "seed": True, "partly": True,
     "message": "What transition did the 1931 Act give agriculture, and how did farmers react to it?",
     "spans": [seed(MOOT, "kch_victorMoot02", "It gave agriculture and shipping a ten-year transition and exempted "
                                              "continuous services.")]},
    {"id": "ret-a100", "kind": "answerable", "who": "victor", "partly": True,
     "message": "What notice must the prosecutor give before using other-acts evidence, and can the defence get it "
                "thrown out if the notice comes late?",
     "spans": [corpus(IV, "provide reasonable notice of any such evidence that the prosecutor intends to offer at trial, "
                          "so that the defendant has a fair opportunity to meet it"),
               corpus(IV, "if the court, for good cause, excuses lack of pretrial notice", 1)]},

    # ══ unanswerable (40, on the same topics; nothing in the character's sources answers them) ══
    {"id": "ret-u001", "kind": "unanswerable", "who": "hana",
     "message": "How long can roasted cashews stay fresh in the fridge?"},
    {"id": "ret-u002", "kind": "unanswerable", "who": "hana", "message": "How much mercury is in one can of tuna?"},
    {"id": "ret-u003", "kind": "unanswerable", "who": "hana", "message": "How long should I bake a salmon fillet for?"},
    {"id": "ret-u004", "kind": "unanswerable", "who": "hana",
     "message": "How many kernels does it take to make a cup of popped popcorn?"},
    {"id": "ret-u005", "kind": "unanswerable", "who": "hana",
     "message": "Are almonds okay for someone with a tree nut allergy?"},
    {"id": "ret-u006", "kind": "unanswerable", "who": "hana",
     "message": "How many calories a day does MyPlate say a teenage boy needs?"},
    {"id": "ret-u007", "kind": "unanswerable", "who": "hana", "message": "How much sugar goes into Grandma's yuzu cake?"},
    {"id": "ret-u008", "kind": "unanswerable", "who": "hana", "message": "Which fish is best for making sushi at home?"},
    {"id": "ret-u009", "kind": "unanswerable", "who": "hana",
     "message": "How many grams of omega-3 are in a handful of walnuts?"},
    {"id": "ret-u010", "kind": "unanswerable", "who": "hana", "message": "How much vitamin C is in Brazil nuts?"},
    {"id": "ret-u011", "kind": "unanswerable", "who": "amara",
     "message": "How long should a nap before a night shift be?"},
    {"id": "ret-u012", "kind": "unanswerable", "who": "amara",
     "message": "Does melatonin help night-shift nurses sleep during the day?"},
    {"id": "ret-u013", "kind": "unanswerable", "who": "amara",
     "message": "Do blue-light blocking glasses help after a night shift?"},
    {"id": "ret-u014", "kind": "unanswerable", "who": "amara",
     "message": "What's the legal maximum shift length for nurses in Malaysia?"},
    {"id": "ret-u015", "kind": "unanswerable", "who": "amara",
     "message": "How much extra do nurses get paid for working nights?"},
    {"id": "ret-u016", "kind": "unanswerable", "who": "amara", "message": "What triage grade does a broken wrist get?"},
    {"id": "ret-u017", "kind": "unanswerable", "who": "amara",
     "message": "How many weeks does it take the body clock to adjust to permanent nights?"},
    {"id": "ret-u018", "kind": "unanswerable", "who": "amara",
     "message": "Did your fatigue review break the results down by age?"},
    {"id": "ret-u019", "kind": "unanswerable", "who": "amara",
     "message": "Were doctors more fatigued than nurses in your review?"},
    {"id": "ret-u020", "kind": "unanswerable", "who": "amara",
     "message": "What exercise routine helps shift workers sleep better?"},
    {"id": "ret-u021", "kind": "unanswerable", "who": "mei",
     "message": "How many hours of annual leave does a federal employee earn each year?"},
    {"id": "ret-u022", "kind": "unanswerable", "who": "mei", "message": "Can a federal employee telework from abroad?"},
    {"id": "ret-u023", "kind": "unanswerable", "who": "mei", "message": "What is the GS-10, step 10 salary in dollars?"},
    {"id": "ret-u024", "kind": "unanswerable", "who": "mei",
     "message": "What percentage is the night shift differential for wage-grade workers?"},
    {"id": "ret-u025", "kind": "unanswerable", "who": "mei", "message": "How many months did each four-day week pilot run?"},
    {"id": "ret-u026", "kind": "unanswerable", "who": "mei",
     "message": "Did the pilots find any difference in burnout between men and women?"},
    {"id": "ret-u027", "kind": "unanswerable", "who": "mei",
     "message": "How many federal employees are on compressed schedules right now?"},
    {"id": "ret-u028", "kind": "unanswerable", "who": "mei",
     "message": "How many hours of sick leave does a federal employee earn each pay period?"},
    {"id": "ret-u029", "kind": "unanswerable", "who": "mei",
     "message": "How much paid parental leave do federal employees get?"},
    {"id": "ret-u030", "kind": "unanswerable", "who": "mei",
     "message": "How do state government workers' holiday rules differ from federal ones?"},
    {"id": "ret-u031", "kind": "unanswerable", "who": "victor",
     "message": "What's the standard of proof in a civil case?"},
    {"id": "ret-u032", "kind": "unanswerable", "who": "victor",
     "message": "Is evidence from an illegal search admissible?"},
    {"id": "ret-u033", "kind": "unanswerable", "who": "victor", "message": "How many jurors sit on a federal criminal jury?"},
    {"id": "ret-u034", "kind": "unanswerable", "who": "victor",
     "message": "Can a wife refuse to testify against her husband?"},
    {"id": "ret-u035", "kind": "unanswerable", "who": "victor", "message": "How does hearsay work in English courts?"},
    {"id": "ret-u036", "kind": "unanswerable", "who": "victor",
     "message": "How long does a defendant have to appeal a conviction?"},
    {"id": "ret-u037", "kind": "unanswerable", "who": "victor",
     "message": "What scores did the judges give us at the last moot?"},
    {"id": "ret-u038", "kind": "unanswerable", "who": "victor",
     "message": "What does Rule 609 say about impeaching a witness with a prior conviction?"},
    {"id": "ret-u039", "kind": "unanswerable", "who": "victor",
     "message": "Which countries already have a four-day week written into law?"},
    {"id": "ret-u040", "kind": "unanswerable", "who": "victor", "message": "Is a polygraph result admissible?"},

    # ══ follow-ups (30, with their two earlier lines) ══
    {"id": "ret-f001", "kind": "followup", "who": "hana",
     "earlier": ["Kai: I keep a big jar of walnuts in the cupboard for months.",
                 "Hana: Months is a long time for something that oily."],
     "message": "So what should I do with them instead?",
     "spans": [corpus(HANA_NUTS, "buy small quantities to use quickly or store them in the freezer for long term use")]},
    {"id": "ret-f002", "kind": "followup", "who": "hana",
     "earlier": ["Kai: I'm pregnant and craving tuna sandwiches.",
                 "Hana: Oh, congratulations! Tuna's yummy, but there's a limit, isn't there?"],
     "message": "So how much is okay each week?",
     "spans": [corpus(FISH, "limit their intakes to 12 ounces of such fish as canned tuna or salmon")]},
    {"id": "ret-f003", "kind": "followup", "who": "hana",
     "earlier": ["Kai: I'm making popcorn for movie night.", "Hana: Yay! Butter, or something fancier?"],
     "message": "Something sweet but not too naughty. Ideas?",
     "spans": [corpus(POP, "For a sweeter treat, sprinkle a few dark chocolate chips on freshly popped popcorn with a dash "
                           "of cinnamon.")]},
    {"id": "ret-f004", "kind": "followup", "who": "hana",
     "earlier": ["Kai: My little cousin is a really picky eater.", "Hana: Oh no, mealtimes must be a battle!"],
     "message": "Does that MyPlate site have anything for kids like him?",
     "spans": [corpus(PLATE, "The web page has tips for getting kids to try new foods and for developing healthy eating "
                             "habits")]},
    {"id": "ret-f005", "kind": "followup", "who": "hana", "seed": True,
     "earlier": ["Kai: It's pouring and my niece is sniffly.", "Hana: Rainy days call for Grandma's soup!"],
     "message": "What goes in it?",
     "spans": [seed(RECIPES, "kch_hanaRecipe03", "Rainy-day soup: miso, tofu and whatever greens are wilting.")]},
    {"id": "ret-f006", "kind": "followup", "who": "hana",
     "earlier": ["Kai: I bought a bag of pine nuts for pesto.", "Hana: Lovely! Fresh pesto is the best."],
     "message": "Anything I should watch out for with them?",
     "spans": [corpus(HANA_NUTS, "A variety of Asian pine nuts, recently available in the US, are associated with a mild "
                                 "allergic reaction")]},
    {"id": "ret-f007", "kind": "followup", "who": "hana",
     "earlier": ["Kai: My dad snacks on chips every single evening.", "Hana: Ah, the crunchy habit!"],
     "message": "Would swapping them for nuts actually be better?",
     "spans": [corpus(HANA_NUTS, "It is a simple switch to use nuts to replace other high calorie, nutrient poor foods "
                                 "such as chips."),
               corpus(HANA_NUTS, "which is similar to that provided by a portion of less nutritious snack chips", 1)]},
    {"id": "ret-f008", "kind": "followup", "who": "amara",
     "earlier": ["Kai: I just did three twelve-hour shifts back to back.",
                 "Amara: That's a heavy block. How are you holding up?"],
     "message": "Wrecked. How many days off should come after that?",
     "spans": [corpus(M5, "Consider two rest days after three consecutive 12-hour shifts.")]},
    {"id": "ret-f009", "kind": "followup", "who": "amara",
     "earlier": ["Kai: My manager wants me on days one week and nights the next.",
                 "Amara: Hm. That's a pattern I'd push back on."],
     "message": "Is it really the worst kind?",
     "spans": [corpus(M5, "The most difficult speed of rotation is a weekly rotation")]},
    {"id": "ret-f010", "kind": "followup", "who": "amara",
     "earlier": ["Kai: I read that staying up all night is like being drunk.",
                 "Amara: There's real research behind that comparison."],
     "message": "How drunk, after 17 hours?",
     "spans": [corpus(M3, "Being awake for 17 hours is similar to having a BAC of 0.05%.")]},
    {"id": "ret-f011", "kind": "followup", "who": "amara",
     "earlier": ["Kai: My evening shift ends at 11:30 and I'm back in at 7 the next morning.",
                 "Amara: That's what rota planners call a quick change."],
     "message": "What's the minimum gap there should be?",
     "spans": [corpus(M5, "Knauth and Hornberger recommend at least 11 hours between two work shifts.")]},
    {"id": "ret-f012", "kind": "followup", "who": "amara", "seed": True,
     "earlier": ["Kai: Did your fatigue review look at sleep at all?",
                 "Amara: It did. It was the biggest complaint by far."],
     "message": "What happened to the ones who slept under six hours?",
     "spans": [seed(FATIGUE, "kch_amaraFat04", "Staff who slept under six hours before a shift were twice as likely to "
                                               "report a near-miss medication error that week.")]},
    {"id": "ret-f013", "kind": "followup", "who": "amara", "seed": True,
     "earlier": ["Kai: My partner's had a pounding headache since she quit coffee on Monday.",
                 "Amara: Ah, the dreaded withdrawal."],
     "message": "Does she need to go to A&E for it?",
     "spans": [seed(TRIAGE, "kch_amaraTri03", "Gradual tapering, fluids and simple painkillers are usually enough; it "
                                              "rarely needs emergency care.")]},
    {"id": "ret-f014", "kind": "followup", "who": "amara",
     "earlier": ["Kai: After nights I keep forgetting the drug dose between the chart and the med room.",
                 "Amara: That's a well-known effect of sleep loss."],
     "message": "Which part of memory is it hitting?",
     "spans": [corpus(M3, "Both short-term recalla and working memoryb decline.")]},
    {"id": "ret-f015", "kind": "followup", "who": "amara",
     "earlier": ["Kai: Our unit is thinking about moving to 12-hour shifts.",
                 "Amara: They can work, but only under the right conditions."],
     "message": "Should overtime ever go on top of them?",
     "spans": [corpus(M5, "Shift overruns on extended-hour shifts are common for nurses, but severely reduce the "
                          "opportunity for sleep")]},
    {"id": "ret-f016", "kind": "followup", "who": "mei",
     "earlier": ["Kai: Our office is moving to flexible schedules.",
                 "Mei: Then you'll want to understand credit hours."],
     "message": "Can my boss in the Senior Executive Service bank them too?",
     "spans": [corpus(FWS, "OPM regulations prohibit Senior Executive Service (SES) members from accumulating credit hours "
                           "under AWS programs"),
               corpus(HB, "SES members may not accumulate credit hours")]},
    {"id": "ret-f017", "kind": "followup", "who": "mei",
     "earlier": ["Kai: I'm on a 5/4-9 flexible schedule.",
                 "Mei: Two holidays in one pay period can trip that up."],
     "message": "Why, what do I have to do then?",
     "spans": [corpus(HOL, "must make arrangements to work extra hours during other regularly scheduled workdays")]},
    {"id": "ret-f018", "kind": "followup", "who": "mei",
     "earlier": ["Kai: I'm posted overseas and our week runs Sunday to Thursday.",
                 "Mei: Then your Monday holidays behave differently."],
     "message": "Differently how?",
     "spans": [corpus(HOL, "are moved to the preceding Sunday. This applies to employees whose basic workweek is Sunday "
                           "through Thursday.")]},
    {"id": "ret-f019", "kind": "followup", "who": "mei",
     "earlier": ["Kai: My agency wants to put our unit on compressed schedules.",
                 "Mei: Do you have a union, or is the unit unorganized?"],
     "message": "We have a union. Does that change anything?",
     "spans": [corpus(CWS, "The agency must successfully negotiate a CWS program with the union for a represented group of "
                           "employees prior to implementation"),
               corpus(HB, "must negotiate the establishment and terms of the program with the exclusive representative of "
                          "the bargaining unit")]},
    {"id": "ret-f020", "kind": "followup", "who": "mei", "seed": True,
     "earlier": ["Kai: Those pilot results sound amazing.", "Mei: They do. Read the fine print on who took part."],
     "message": "Why, what's the catch?",
     "spans": [seed(PILOTS, "kch_meiPilot07", "Participants were not randomly selected, so the authors warn against "
                                              "reading this as a national estimate."),
               seed(PILOTS, "kch_meiPilot01", "Every participating organisation volunteered."),
               seed(PILOTS, "kch_meiPilot02", "Seventy-one percent of participating organisations were in professional "
                                              "services, software, marketing or the non-profit sector.", 1)]},
    {"id": "ret-f021", "kind": "followup", "who": "mei", "seed": True,
     "earlier": ["Kai: How did they collect the pilot data?", "Mei: Mostly surveys, at three points in each pilot."],
     "message": "Did people keep answering them?",
     "spans": [seed(PILOTS, "kch_meiPilot10", "Survey response fell from 74% to 58% by the final wave.")]},
    {"id": "ret-f022", "kind": "followup", "who": "mei",
     "earlier": ["Kai: I start at 7:30 and take 45 minutes at lunch.",
                 "Mei: There's a grid in the handbook for exactly that."],
     "message": "So when does my day end?",
     "spans": [corpus(HB, "| 7:30 | 4:00 | 4:05 | 4:10 | 4:15 |"),
               corpus(HB, "The point at which the Workday Starting Time row intersects the Midday Flex column is the "
                          "Ending Time for an 8-hour day.", 1)]},
    {"id": "ret-f023", "kind": "followup", "who": "mei",
     "earlier": ["Kai: The office shut for a snowstorm on my regular day off.",
                 "Mei: Ah, the old question about getting another day."],
     "message": "Do I get one?",
     "spans": [corpus(HB, "other employees who do not have a scheduled workday(s) during the office closure or furlough "
                          "may not be granted another nonworkday"),
               corpus(HB, "if the agency is closed because of weather conditions, the employees have no entitlement to an "
                          "additional day off")]},
    {"id": "ret-f024", "kind": "followup", "who": "victor",
     "earlier": ["Kai: The witness told the nurse 'my chest hurts and it started an hour ago'.",
                 "Victor: A classic hearsay question. Who's offering it?"],
     "message": "The plaintiff. Does it get in?",
     "spans": [corpus(VIII, "is made for—and is reasonably pertinent to—medical diagnosis or treatment"),
               corpus(VIII, "describes medical history; past or present symptoms or sensations; their inception; or their "
                            "general cause")]},
    {"id": "ret-f025", "kind": "followup", "who": "victor",
     "earlier": ["Kai: The defence wants to show the victim was violent.",
                 "Victor: In a homicide case, that opens a door for the prosecution."],
     "message": "What door, exactly?",
     "spans": [corpus(IV, "may offer evidence of the alleged victim's trait of peacefulness to rebut evidence that the "
                          "victim was the first aggressor")]},
    {"id": "ret-f026", "kind": "followup", "who": "victor",
     "earlier": ["Kai: I've got an old business ledger I want to put in.",
                 "Victor: Records of a regularly conducted activity, then."],
     "message": "Who has to vouch for it?",
     "spans": [corpus(VIII, "all these conditions are shown by the testimony of the custodian or another qualified witness, "
                            "or by a certification")]},
    {"id": "ret-f027", "kind": "followup", "who": "victor",
     "earlier": ["Kai: Their expert relied on reports that aren't admissible themselves.",
                 "Victor: That's allowed, within limits."],
     "message": "Can the jury hear what's in those reports?",
     "spans": [corpus(VII, "the proponent of the opinion may disclose them to the jury only if their probative value in "
                           "helping the jury evaluate the opinion substantially outweighs their prejudicial effect")]},
    {"id": "ret-f028", "kind": "followup", "who": "victor", "seed": True,
     "earlier": ["Kai: The opposition keeps saying they agree with the goal, just not this fast.",
                 "Victor: I have a note on exactly that move."],
     "message": "What does it say?",
     "spans": [seed(MOOT, "kch_victorMoot05", "Once the opposition accepts the goal, the debate is about implementation, "
                                              "and the side with a timetable wins it.")]},
    {"id": "ret-f029", "kind": "followup", "who": "victor",
     "earlier": ["Kai: My client said something in plea talks that the prosecutor now wants to use.",
                 "Victor: Did the talks end in a guilty plea?"],
     "message": "No, they fell apart. Can they use it?",
     "spans": [corpus(IV, "a statement made during plea discussions with an attorney for the prosecuting authority if the "
                          "discussions did not result in a guilty plea"),
               corpus(IV, "evidence of the following is not admissible against the defendant who made the plea or "
                          "participated in the plea discussions")]},
    {"id": "ret-f030", "kind": "followup", "who": "victor",
     "earlier": ["Kai: The dying man named his attacker.",
                 "Victor: Then we're in Rule 804 territory, if he's truly unavailable."],
     "message": "And it's a murder trial. Does that matter?",
     "spans": [corpus(VIII, "In a prosecution for homicide or in a civil case, a statement that the declarant, while "
                            "believing the declarant's death to be imminent, made about its cause or circumstances.")]},

    # ══ non-English (15: Malay 8, Chinese 7) ══
    {"id": "ret-x001", "kind": "non_english", "lang": "ms", "who": "hana",
     "message": "Kacang apa yang ada banyak selenium?",
     "spans": [corpus(HANA_NUTS, "Most contain large amounts of selenium, an important antioxidant nutrient")]},
    {"id": "ret-x002", "kind": "non_english", "lang": "ms", "who": "hana",
     "message": "Berapa kali seminggu saya patut makan ikan untuk jantung?",
     "spans": [corpus(FISH, "recommends eating two, 3.5 oz servings of fish per week")]},
    {"id": "ret-x003", "kind": "non_english", "lang": "zh", "who": "hana",
     "message": "爆米花算是全谷物吗？",
     "spans": [corpus(POP, "Did you know that popcorn is a 100 percent whole grain?")]},
    {"id": "ret-x004", "kind": "non_english", "lang": "zh", "who": "hana",
     "message": "核桃含有哪一种植物性的omega-3脂肪酸？",
     "spans": [corpus(HANA_NUTS, "They are an excellent source of alpha-linolenic acid (ALA); the plant based omega-3 "
                                 "fatty acid.")]},
    {"id": "ret-x005", "kind": "non_english", "lang": "ms", "who": "amara",
     "message": "Berapa jam tidur yang orang dewasa perlukan setiap malam?",
     "spans": ADULT_SLEEP},
    {"id": "ret-x006", "kind": "non_english", "lang": "ms", "who": "amara", "seed": True,
     "message": "Bila sakit kepala perlu terus dirujuk kepada doktor?",
     "spans": HEADACHE_ESCALATE},
    {"id": "ret-x007", "kind": "non_english", "lang": "zh", "who": "amara",
     "message": "连续上三个十二小时的班之后应该休息几天？",
     "spans": [corpus(M5, "Consider two rest days after three consecutive 12-hour shifts.")]},
    {"id": "ret-x008", "kind": "non_english", "lang": "zh", "who": "amara",
     "message": "连续清醒24小时相当于血液酒精浓度多少？",
     "spans": [corpus(M3, "Being awake for 24 hours is similar to having a BAC of 0.10%.")]},
    {"id": "ret-x009", "kind": "non_english", "lang": "ms", "who": "mei", "seed": True,
     "message": "Berapa banyak organisasi yang menyertai perintis minggu kerja empat hari?",
     "spans": [seed(PILOTS, "kch_meiPilot01", "covering 212 organisations and about 9,800 workers")]},
    {"id": "ret-x010", "kind": "non_english", "lang": "ms", "who": "mei",
     "message": "Adakah Juneteenth cuti umum persekutuan?",
     "spans": [corpus(HOL, "Juneteenth National Independence Day (June 19).")]},
    {"id": "ret-x011", "kind": "non_english", "lang": "zh", "who": "mei",
     "message": "压缩工作制的员工可以累积弹性工时吗？",
     "spans": CWS_NO_CREDIT},
    {"id": "ret-x012", "kind": "non_english", "lang": "zh", "who": "mei", "seed": True,
     "message": "试点结束后有多少机构保留了四天工作制？",
     "spans": [seed(PILOTS, "kch_meiPilot07", "Ninety-two percent of organisations kept the four-day week after the "
                                              "pilot.")]},
    {"id": "ret-x013", "kind": "non_english", "lang": "ms", "who": "victor",
     "message": "Bolehkah bukti insurans liabiliti digunakan untuk membuktikan kecuaian?",
     "spans": [corpus(IV, "Evidence that a person was or was not insured against liability is not admissible to prove "
                          "whether the person acted negligently or otherwise wrongfully.")]},
    {"id": "ret-x014", "kind": "non_english", "lang": "ms", "who": "victor",
     "message": "Apakah maksud keterangan dengar cakap di mahkamah?",
     "spans": HEARSAY},
    {"id": "ret-x015", "kind": "non_english", "lang": "zh", "who": "victor",
     "message": "专家证人可以就被告的精神状态发表意见吗？",
     "spans": [corpus(VII, "In a criminal case, an expert witness must not state an opinion about whether the defendant "
                           "did or did not have a mental state or condition that constitutes an element of the crime "
                           "charged or of a defense.")]},

    # ══ naming a document (20; 12 also name a section) ══
    {"id": "ret-n001", "kind": "naming", "who": "hana", "named": {"doc": "Go Nuts", "section": None},
     "message": "In the Go Nuts piece, what does the European Union let people claim about walnuts?",
     "spans": [corpus(HANA_NUTS, "Walnuts contribute to the improvement of the elasticity of the blood vessels.")]},
    {"id": "ret-n002", "kind": "naming", "who": "hana", "named": {"doc": "Eat fish", "section": None},
     "message": "What does the Eat Fish article say about how much tuna a pregnant woman can have?",
     "spans": [corpus(FISH, "limit their intakes to 12 ounces of such fish as canned tuna or salmon")]},
    {"id": "ret-n003", "kind": "naming", "who": "hana", "seed": True,
     "named": {"doc": "Grandma's recipe notebook", "section": "p. 11"},
     "message": "What's written on page 11 of Grandma's recipe notebook?",
     "spans": [seed(RECIPES, "kch_hanaRecipe04", "Flowers on the table should never be taller than your elbow. People want "
                                                "to see each other when they eat.")]},
    {"id": "ret-n004", "kind": "naming", "who": "hana", "seed": True,
     "named": {"doc": "Grandma's recipe notebook", "section": "p. 5"},
     "message": "What's the sushi rice tip on page 5 of Grandma's recipe notebook?",
     "spans": [seed(RECIPES, "kch_hanaRecipe02", "Sushi rice for a crowd: three cups of rice and a splash more vinegar "
                                                "than you think."),
               seed(RECIPES, "kch_hanaRecipe02", "A spoon of pineapple juice in the vinegar keeps it bright when the "
                                                "fish is rich.")]},
    {"id": "ret-n005", "kind": "naming", "who": "hana", "named": {"doc": "Choose MyPlate", "section": None},
     "message": "What does the Choose MyPlate article offer for pregnant women?",
     "spans": [corpus(PLATE, "resources on the special nutritional needs during pregnancy")]},
    {"id": "ret-n006", "kind": "naming", "who": "amara",
     "named": {"doc": "NIOSH training for nurses", "section": "Module 3"},
     "message": "In Module 3 of the NIOSH nurse training, what does it say about microsleeps and driving?",
     "spans": [corpus(M3, "Microsleep is detectible on ambulatory electroencephalograms (EEGs) and is strongly correlated "
                          "with automobile crashes.")]},
    {"id": "ret-n007", "kind": "naming", "who": "amara", "seed": True,
     "named": {"doc": "Meridian Shift Fatigue Review 2025", "section": "p. 9"},
     "message": "What does page 9 of the Shift Fatigue Review say about the pilot wards?",
     "spans": [seed(FATIGUE, "kch_amaraFat06", "After twelve weeks, burnout scores on both wards fell by roughly a fifth, "
                                               "sleep quality improved, and patient throughput stayed within normal "
                                               "variation."),
               seed(FATIGUE, "kch_amaraFat06", "Two wards piloted a compressed rota: four longer days, then three days "
                                               "off.")]},
    {"id": "ret-n008", "kind": "naming", "who": "amara",
     "named": {"doc": "NIOSH work organization module", "section": "Extended Shifts"},
     "message": "Under Extended Shifts in the work organization module, what did the 2014 systematic review conclude?",
     "spans": [corpus(M5, "more than 40 hours of work a week is associated with adverse patient care outcomes")]},
    {"id": "ret-n009", "kind": "naming", "who": "amara", "seed": True,
     "named": {"doc": "ED triage guidelines", "section": None},
     "message": "What do the ED triage guidelines say about giving advice over the phone?",
     "spans": [seed(TRIAGE, "kch_amaraTri06", "Advice given by phone or chat must say clearly that it is not an "
                                              "examination.")]},
    {"id": "ret-n010", "kind": "naming", "who": "amara",
     "named": {"doc": "NIOSH training introduction", "section": None},
     "message": "How does the introduction to the NIOSH training define a compressed schedule?",
     "spans": [corpus(M1, "A compressed schedule involves working 36-40 hours per week in fewer than 5 days.")]},
    {"id": "ret-n011", "kind": "naming", "who": "mei",
     "named": {"doc": "Handbook on Alternative Work Schedules", "section": "Appendix C"},
     "message": "In Appendix C of the Handbook on Alternative Work Schedules, how long is a day on the four-day work "
                "week?",
     "spans": [corpus(HB, "A full-time employee must work 10 hours a day, 40 hours a week, and 80 hours a biweekly pay "
                          "period.")]},
    {"id": "ret-n012", "kind": "naming", "who": "mei",
     "named": {"doc": "Federal Holidays fact sheet", "section": "New Appointments"},
     "message": "What does the federal holidays fact sheet say under New Appointments?",
     "spans": [corpus(HOL, "are entitled to paid holiday time off, if they work at least one hour on either the day before "
                           "or after the holiday")]},
    {"id": "ret-n013", "kind": "naming", "who": "mei",
     "named": {"doc": "Compressed Work Schedules fact sheet", "section": "Overtime"},
     "message": "In the compressed work schedules fact sheet, what's the overtime rule?",
     "spans": [corpus(CWS, "For full-time employees, all hours worked in excess of the established compressed work schedule "
                           "are overtime hours.")]},
    {"id": "ret-n014", "kind": "naming", "who": "mei", "seed": True,
     "named": {"doc": "Four-day week pilot summaries", "section": "p. 7"},
     "message": "On page 7 of the four-day week pilot summaries, what set the best firms apart?",
     "spans": [seed(PILOTS, "kch_meiPilot04", "Firms with the biggest gains had halved their meetings and redesigned "
                                              "workflows before the trial began.")]},
    {"id": "ret-n015", "kind": "naming", "who": "mei",
     "named": {"doc": "Flexible Work Schedules fact sheet", "section": None},
     "message": "Which kinds of flexible schedule does the Flexible Work Schedules fact sheet list?",
     "spans": [corpus(FWS, "These include flexitour, gliding, variable day, variable week, and maxiflex schedules.")]},
    {"id": "ret-n016", "kind": "naming", "who": "victor",
     "named": {"doc": "Federal Rules of Evidence, Article VIII", "section": "Rule 803(18)"},
     "message": "Under Rule 803(18) in the hearsay article, when can a statement from a treatise come in?",
     "spans": [corpus(VIII, "the statement is called to the attention of an expert witness on cross-examination or relied "
                            "on by the expert on direct examination"),
               corpus(VIII, "the publication is established as a reliable authority")]},
    {"id": "ret-n017", "kind": "naming", "who": "victor", "seed": True,
     "named": {"doc": "Moot court notes", "section": "§ 4"},
     "message": "In section 4 of my moot court notes, what's the phase-in precedent?",
     "spans": [seed(MOOT, "kch_victorMoot04", "Phase-in precedent: sector-by-sector timetables, collective agreements "
                                              "first, the public sector as model employer.")]},
    {"id": "ret-n018", "kind": "naming", "who": "victor",
     "named": {"doc": "Federal Rules of Evidence, Article IV", "section": "Rule 406"},
     "message": "Under Rule 406 in the relevance article, can habit evidence come in without an eyewitness?",
     "spans": [corpus(IV, "The court may admit this evidence regardless of whether it is corroborated or whether there was "
                          "an eyewitness.")]},
    {"id": "ret-n019", "kind": "naming", "who": "victor",
     "named": {"doc": "Federal Rules of Evidence on opinions and expert testimony", "section": None},
     "message": "What does the opinions and expert testimony article say about an expert disclosing the underlying facts?",
     "spans": [corpus(VII, "an expert may state an opinion—and give the reasons for it—without first testifying to the "
                           "underlying facts or data"),
               corpus(VII, "But the expert may be required to disclose those facts or data on cross-examination.")]},
    {"id": "ret-n020", "kind": "naming", "who": "victor",
     "named": {"doc": "Federal Rules of Evidence on relevance", "section": None},
     "message": "Does the relevance article ever let irrelevant evidence in?",
     "spans": [corpus(IV, "Irrelevant evidence is not admissible.")]},
]
