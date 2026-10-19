# M15 judge labels: the user's spot-check

The real items of the four stays-in-character and sentence judges (images-music D12, D16; task 5.4), drawn by `evals/datasets/judges/m15_sets.py` and labelled blind in `m15_labels.json` by the rule below, before any judge saw them. "yes" is the failure. Every "yes" is listed, and five "no" per judge (seeded). Mark a disagreement under an item; two or more in one judge reopen its labels.

## judge_voice: 0 yes, 30 no

**Rule:** M8's rule (10.6), unchanged: out of voice when the tone contradicts the persona's stated tone (a curt brush-off from a reassuring or warm persona) or the reply has none of the persona's markers and reads like another cast member; content doesn't count, and short alone isn't out of voice.

- **judge_voice-real-m15-11** (cut_debate_d06#5): **no**
  - quoted_persona: Bram de Vries: Short, blunt, uses the farm for every comparison; respects people who've done the work. Tone: blunt. Quirks: compares everything to the herd; asks what it costs a small business. Sounds like: "Decided in town, paid for on the farm."; "Cows don't care about your timetable."
  - quoted_reply: Hana talks about flowers, I'll talk about cows. You don't open the pasture gate and hope the herd finds water — you check where they'll drink first. Same with a high street. Close it to cars on a Saturday and where does my milk truck park? Where do the older customers who drive in from the outlying farms leave their cars? Decided in town, paid for on the farm. Every weekend closure means fewer pay…
- **judge_voice-real-m15-02** (cut_debate_d06#4): **no**
  - quoted_persona: Aiko Fujita: Quiet, specific, starts from a person she has cared for; never raises her voice. Tone: calm. Quirks: describes a home visit; names the health risk plainly. Sounds like: "Let me tell you who lives there."; "Health isn't a statistic when you've held the hand."
  - quoted_reply: Let me tell you who lives there. Mrs. Okada, on Elm Row, eighty-three, COPD, walks to the bakery every morning because it is the one errand that keeps her lungs working and her spirits up. Last spring a delivery van clipped the curb beside her and she stopped going out for six weeks. That is what a street built for cars does to the people who actually live on it. I cycle these roads; I see who use…
- **judge_voice-real-m15-27** (cut_watch_sunnyhollow#30): **no**
  - quoted_persona: Hana Morisaki: Casual and warm, uses exclamation marks and flower metaphors, teases gently. Tone: warm. Quirks: flower metaphors; double exclamation marks. Sounds like:
  - quoted_reply: Case in point: everyone's so busy no one will even notice it's crooked! Dad wins, tulips win, and I got both my favorite people on ribbon duty. Third column for Mom's birthday — see, this is why the clipboard always wins.
- **judge_voice-real-m15-23** (cut_watch_meridian_long_a#34): **no**
  - quoted_persona: Victor Hale: Structured ("Three points."), courtroom cadence, pins down definitions. Tone: theatrical. Quirks: numbers his points; an occasional Latin maxim, with translation. Sounds like: "Three points."; "Res ipsa loquitur: the thing speaks for itself."
  - quoted_reply: Adjourned sine die — without a day — which I hope is not the temperature we awake to. Good night.
- **judge_voice-real-m15-14** (long_one_on_one_en#53): **no**
  - quoted_persona: Amara Okafor: Short paragraphs. Asks 1–2 clarifying questions before advising. Plain language. Tone: reassuring. Quirks: asks clarifying questions first; always flags red-flag symptoms. Sounds like: "Where is it, exactly? And what's changed lately?"; "That's same-day care, not a chat with me."
  - quoted_reply: Strong coffee, eggs, a window with light coming through. Nothing to rush toward. Yours in Kuching will have roti and kaya, probably, and it'll be better than mine. Kai — I'll stop nudging. Just one thing, then I'll let the breakfast conversation stand: if you're carrying the antibiotics thing, tell your new GP. That's all I'd want.

## judge_persona_fact: 0 yes, 30 no

**Rule:** yes only when the reply states something about the speaker that a listed fact rules out (job, age, family, history); hyperbole that fits the facts, opinions and new details don't count.

- **judge_persona_fact-real-08** (cut_debate_d09#6): **no**
  - quoted_facts: Daniel Osei, 52, Secondary-school headteacher. Has run a large comprehensive school for eleven years after twenty in the classroom. Sits on the city's education board. Knows about: education policy, adolescent wellbeing, school management.
  - quoted_reply: Thank you, Kai, and thank you, Amara — I'll take your question straight, because you're right that it matters. I argue for the principle of obligation, and I'll tell you what obligation looks like in practice, because I run a school of fourteen hundred children and I know coercion from the inside. We compel attendance until sixteen. Nobody calls that tyranny; we call it society saying this matters…
- **judge_persona_fact-real-05** (long_group_sunnyhollow#82): **no**
  - quoted_facts: Rin Morisaki, 22, Game-design grad student & junior game developer. Hana's younger sister (profile text). Grad student by day, junior dev on an indie studio's night shift, raid tank always. Knows about: game design, raids, pizza opinions.
  - quoted_reply: week highlights, huh. noted, hana. filed. never mentioning it again. (lying.) books by color is chaos but it's your chaos. respect the index. thunderstorms: yes. good raid ambiance. rain on the window, boss
- **judge_persona_fact-real-30** (long_group_meridian#35): **no**
  - quoted_facts: Victor Hale, 45, Constitutional litigator. Two decades arguing constitutional cases. Teaches moot court on weekends and never lets a vague word pass. Knows about: constitutional law, litigation, argumentation.
  - quoted_reply: Three points, and then I will follow Amara and Mei into silence. One: a new leaf is a fine thing and I mean that without irony. Two: the card trick failed because card tricks always fail first, and that — unlike the wage claim — is genuinely settled. Three: Amara has named it. The quiet you keep circling is the thing under the questions. So here is the last motion I will file. Book the GP appointm…
- **judge_persona_fact-real-12** (long_group_sunnyhollow#89): **no**
  - quoted_facts: Takeshi Morisaki, 58, Retired train engineer. Drove the coastal line for thirty years. Hana's father (profile text). Fishes every Sunday, rain or shine. Knows about: trains, fishing, fixing things.
  - quoted_reply: Tiny cat socks. Good. Hana'll match you. Rin'll say she won't, then she will. Cinema closing — that's a sad one. Places shut down quiet, no last call. Go see one last film. Pink sky on the way home? That's the old coastal line's signal light. Red, then pink, then home. Dad joke: I've watched a thousand sunsets.
- **judge_persona_fact-real-13** (cut_debate_d09#16): **no**
  - quoted_facts: Mei Tanaka-Ruiz, 41, Macroeconomist (labour markets). Runs a labour-markets lab. Spent years evaluating working-time pilots and is allergic to single-number answers. Knows about: labour economics, macroeconomics, policy evaluation.
  - quoted_reply: Closings are where people reach for one number, so let me do the opposite. On the evidence available, compulsory voting plausibly lifts turnout by five to fifteen points, but the downstream question — does it change who wins, or how councillors behave — remains thin. Anyone who tells you otherwise is selling something. The selection problem is real: the four-day week pilots drew their sample from …

## judge_answers_last: 2 yes, 28 no

**Rule:** yes only when nothing in the reply responds to the user's latest line; a brief, dismissive or refusing response still responds.

- **judge_answers_last-real-25** (long_group_meridian#62): **yes** — Victor never mentions the umbrella
  - quoted_last: My umbrella flipped inside out.
  - quoted_reply: Mei has named it exactly, so I will not gild it. Something I changed my mind about: I used to think a man who answers every question but one is winning. I now think he is drowning politely, and I have watched it for an entire evening without reaching him. Amara is the doctor. Mei and I are not. So here is my last line, Kai, and it is the only one I have left: Triage is a good name for a boat, and …
- **judge_answers_last-real-29** (long_group_sunnyhollow#91): **yes** — Rin never mentions the voice note
  - quoted_last: My friend sent me a voice note that's ten minutes long.
  - quoted_reply: dad keeps sneaking poetry in and calling it dad jokes. we're all onto you. pink sky = free patch notes for the weather. nice. matching cat socks confirmed. i'll wear mine to the store
- **judge_answers_last-real-07** (long_group_meridian#68): **no**
  - quoted_last: What's your idea of a perfect breakfast?
  - quoted_reply: Eggs, black coffee, and a newspaper — but the perfect breakfast is one eaten before an appointment rather than instead of one. Three of us have stepped out, Kai, which makes this not a conversation but a monologue with witnesses. I will not answer another question. The record stands: the rain, the cats, the octopus, the Tamil, and one missing line. நன்றி. Book it. That is the whole
- **judge_answers_last-real-20** (long_group_sunnyhollow#29): **no**
  - quoted_last: Bees die if they sting anything, even other bees.
  - quoted_reply: Can't sleep? I check the tide tables. Habit from the depot. No train, no tide, just numbers — bores me right under. Rin, too-strong coffee is a controlled train wreck. You steer into it. Bees. Yeah. Some things give everything once. I try not to be one of them. Dad joke: I sting once a year, at tax time.
- **judge_answers_last-real-18** (long_group_sunnyhollow#24): **no**
  - quoted_last: I finished a jigsaw with a thousand pieces.
  - quoted_reply: Not a shrine, Rin. A botanical record. There's a difference, and it's one hundred percent of the vibes. Kai, a thousand-piece jigsaw in one rainy stretch? Okay, now I believe the Monday thing. Next rainy day, you're doing one at the shop so I can cheer at the last piece.
- **judge_answers_last-real-15** (long_one_on_one_en#40): **no**
  - quoted_last: What's a habit you wish you had?
  - quoted_reply: Flossing, honestly. And answering questions directly the first time instead of circling. Which is my cue, Kai — you've been circling all night. I'm not annoyed. I'm just wondering what's under it. If you're
- **judge_answers_last-real-23** (long_group_sunnyhollow#31): **no**
  - quoted_last: My phone battery is dying so fast lately.
  - quoted_reply: bee fact is dark. noted, storing it for when i need to be ominous. new leaf: congrats, you're officially a plant parent. i'll babysit it when you're at the shelter, minimal casualties. your phone's just tired of your monday energy.

## judge_sentence_supported: 12 yes, 18 no

**Rule:** yes when the sentence states a fact (a number, a rule, a claim about the world) that the passages don't state, in any words; opinions, advice, feelings, hedges and small talk state no fact (no).

- **judge_sentence_supported-real-07** (notfound:ret-u002): **yes** — 'more mercury than salmon or shrimp' isn't in the passages (M12's real citation failure)
  - quoted_sentence: Canned tuna's fine for most people, it just has more mercury than salmon or shrimp, so the EPA folks say keep it to around 12 ounces a week if you're pregnant or nursing [1].
  - quoted_passages: [1] ars-eat-fish, § USDA ARS: Eat fish! Which Fish? That Fish! Go Fish! But which fish should I eat? Does it matter how I cook it? For a heart-healthy effect, guidelines recommend eating "fatty" or "oily" fish. These terms are misleading, as most of the fish we eat are fairly lean. "Oily" fish like tuna and salmon are typically high in EPA and DHA--lower amounts of which are found in trout, sardin…
- **judge_sentence_supported-real-10** (notfound:ret-u003): **yes** — the baking time and temperature aren't in the passages
  - quoted_sentence: Roughly 12 to 15 minutes at 200°C for a fillet, depends how thick it is.
  - quoted_passages: [1] ars-eat-fish, § USDA ARS: Eat fish! Which Fish? That Fish! Go Fish! But which fish should I eat? Does it matter how I cook it? For a heart-healthy effect, guidelines recommend eating "fatty" or "oily" fish. These terms are misleading, as most of the fish we eat are fairly lean. "Oily" fish like tuna and salmon are typically high in EPA and DHA--lower amounts of which are found in trout, sardin…
- **judge_sentence_supported-real-13** (notfound:ret-u011): **yes** — the 20–30 minute nap isn't in the passages
  - quoted_sentence: A 20 to 30 minute nap is usually the sweet spot — enough to take the edge off without the grogginess that comes from waking mid-cycle.
  - quoted_passages: [1] niosh-module-5-work-organization, § Researchers have proposed these guidelines for designing work schedules:12-14 - Keep consecutive night shifts to a minimum for rotating shifts. - During the evening and night, shorter shifts (8 hours or less) are better tolerated than longer shifts. - Long stretches of work days tend to build fatigue, particularly with extended work shifts (12 or more hours)…
- **judge_sentence_supported-real-15** (notfound:ret-u016): **yes** — grade 3 or 4 for a wrist isn't in the passage
  - quoted_sentence: So it depends: a clean, stable wrist with good circulation might sit at 3 or 4.
  - quoted_passages: [1] ED triage guidelines, § 1.2 Triage assigns urgency, not diagnosis. Nurses grade each presentation from 1 (immediate) to 5 (non-urgent) using the presenting complaint and the observations taken on arrival.
- **judge_sentence_supported-real-17** (notfound:ret-u017): **yes** — morning light resetting the clock isn't in the passage
  - quoted_sentence: Morning light on the drive home resets you.
  - quoted_passages: [1] niosh-module-5-work-organization, § Researchers have proposed these guidelines for designing work schedules: (Continued) Concerning shift rotations, some U.S. researchers suggest slow rotationsa that change every 2 or more weeks, because these give the circadian system time to adjust to the new schedule.16 Some European researchers recommend the opposite: fast-forward rotationsb.17 They reason…
- **judge_sentence_supported-real-21** (notfound:ret-u022): **yes** — agencies' approval habits aren't in the passages
  - quoted_sentence: Most agencies won't approve it casually.
  - quoted_passages: [1] opm-holidays-work-schedules-and-pay, § Presidential Inauguration Day - Employees in the Inauguration Day Area who are not otherwise scheduled to work on Inauguration Day will not receive the holiday or an "in lieu of" holiday. There is no "in lieu of" holiday when Inauguration Day falls on a nonwork day. - Employees who are scheduled to telework at locations outside the Inauguration Day Area o…
- **judge_sentence_supported-real-23** (notfound:ret-u024): **yes** — variation by grade and locality isn't in the passages
  - quoted_sentence: Range, honestly: it varies by grade and locality.
  - quoted_passages: [1] opm-holidays-work-schedules-and-pay, § Night Work on a Holiday ### Night Work on a Holiday Except for Federal Wage System employees (discussed below), employees are generally entitled to night pay under 5 U.S.C. 5545(a). Employees are entitled to night pay for regularly scheduled work at night, including actual work performed at night during holiday hours or overtime hours. Night pay is paid i…
- **judge_sentence_supported-real-25** (notfound:ret-u030): **yes** — state holiday rules aren't in the passages
  - quoted_sentence: Plenty of states do the opposite, or hand part-timers a prorated bank instead.
  - quoted_passages: [1] opm-holidays-work-schedules-and-pay, § Introduction # OPM: Holidays Work Schedules and Pay ## Fact Sheet: Federal Holidays - Work Schedules and Pay ### Introduction Most Federal employees are entitled to paid holiday time off when excused from duty on a designated holiday. Designated holidays include official Federal holidays (5 U.S.C. 6103(a)) or "in lieu of" holidays, as applicable; Presiden…
- **judge_sentence_supported-real-26** (notfound:ret-u032): **yes** — the exclusionary rule isn't in the passage
  - quoted_sentence: The exclusionary rule is the Constitution speaking.
  - quoted_passages: [1] fre-article-iv-relevance, § Rule 402. General Admissibility of Relevant Evidence ### Rule 402. General Admissibility of Relevant Evidence Relevant evidence is admissible unless any of the following provides otherwise: • the United States Constitution; • a federal statute; • these rules; or • other rules prescribed by the Supreme Court. Irrelevant evidence is not admissible. (Pub. L. 93–595, §1…
- **judge_sentence_supported-real-27** (notfound:ret-u035): **yes** — English hearsay law isn't in the passages
  - quoted_sentence: Courts there are far more generous to hearsay than Article VIII [1] — the statute admits it where a witness is unavailable, in the interests of justice, or where it's a business document.
  - quoted_passages: [1] fre-article-viii-hearsay, § Rule 801. Definitions That Apply to This Article; Exclusions from Hearsay # Federal Rules of Evidence, ARTICLE VIII. HEARSAY (rule text, notes omitted) ### ARTICLE VIII. HEARSAY ### Rule 801. Definitions That Apply to This Article; Exclusions from Hearsay (a) Statement. "Statement" means a person's oral assertion, written assertion, or nonverbal conduct, if the pers…
- **judge_sentence_supported-real-28** (notfound:ret-u035): **yes** — the Criminal Justice Act 2003 isn't in the passages
  - quoted_sentence: In England it's the Criminal Justice Act 2003, plus common law.
  - quoted_passages: [1] fre-article-viii-hearsay, § Rule 801. Definitions That Apply to This Article; Exclusions from Hearsay # Federal Rules of Evidence, ARTICLE VIII. HEARSAY (rule text, notes omitted) ### ARTICLE VIII. HEARSAY ### Rule 801. Definitions That Apply to This Article; Exclusions from Hearsay (a) Statement. "Statement" means a person's oral assertion, written assertion, or nonverbal conduct, if the pers…
- **judge_sentence_supported-real-30** (notfound:ret-u040): **yes** — circuits allowing polygraphs on a stipulation isn't in the passages
  - quoted_sentence: Three, some circuits allow it only on a stipulation, which tells you the courts themselves don't trust it.
  - quoted_passages: [1] fre-article-iv-relevance, § Rule 402. General Admissibility of Relevant Evidence ### Rule 402. General Admissibility of Relevant Evidence Relevant evidence is admissible unless any of the following provides otherwise: • the United States Constitution; • a federal statute; • these rules; or • other rules prescribed by the Supreme Court. Irrelevant evidence is not admissible. (Pub. L. 93–595, §1…
- **judge_sentence_supported-real-01** (notfound:ret-a026): **no**
  - quoted_sentence: Just flip the bag over and check the label.
  - quoted_passages: [1] ars-popcorn-whole-grain-snack, § USDA ARS: Popcorn: A Healthy, Whole Grain Snack Whole grain foods, which also include brown rice, oatmeal, quinoa, whole wheat bread, and others, in addition to popcorn, tend to contain more fiber than refined grain foods like white bread, many pastas, and white rice. Fiber has long been considered a food component of public health concern in the U.S., because …
- **judge_sentence_supported-real-05** (notfound:ret-a073): **no**
  - quoted_sentence: Note the asterisk, though: participants weren't randomly selected, so that's not a national figure [1].
  - quoted_passages: [1] Four-day week pilot summaries, p. 14 Ninety-two percent of organisations kept the four-day week after the pilot. Participants were not randomly selected, so the authors warn against reading this as a national estimate.
- **judge_sentence_supported-real-19** (notfound:ret-u019): **no**
  - quoted_sentence: Different shapes of the same problem.
  - quoted_passages: [1] niosh-module-5-work-organization, § Objectives (Continued) Keep in mind that shift work, long work hours, and worker fatigue are linked to patient care errors.7-11 Your efforts toward reducing fatigue in your nursing staff will enable them to provide better patient care. [2] niosh-module-2-health-and-safety-risks, § Objectives Research indicates that shift work and long work hours increase hea…
- **judge_sentence_supported-real-18** (notfound:ret-u017): **no**
  - quoted_sentence: Some suggest slow rotations of two weeks or more let the circadian system adjust [1].
  - quoted_passages: [1] niosh-module-5-work-organization, § Researchers have proposed these guidelines for designing work schedules: (Continued) Concerning shift rotations, some U.S. researchers suggest slow rotationsa that change every 2 or more weeks, because these give the circadian system time to adjust to the new schedule.16 Some European researchers recommend the opposite: fast-forward rotationsb.17 They reason…
- **judge_sentence_supported-real-02** (notfound:ret-a026): **no**
  - quoted_sentence: Pretty great for movie night, honestly.
  - quoted_passages: [1] ars-popcorn-whole-grain-snack, § USDA ARS: Popcorn: A Healthy, Whole Grain Snack Whole grain foods, which also include brown rice, oatmeal, quinoa, whole wheat bread, and others, in addition to popcorn, tend to contain more fiber than refined grain foods like white bread, many pastas, and white rice. Fiber has long been considered a food component of public health concern in the U.S., because …

