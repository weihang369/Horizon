## MODIFIED Requirements

### Requirement: Suites and options
`horizon eval <suite>` SHALL accept every suite the harness defines: `canary`, `decisions`, `smoke`, `drafter`, `summary`, `long`, `transcript`, `moodline`, `latency`, `watch-history`, `freerun`, `debate-history`, `debate-plant`, `debate-quality`, `debate`, `retrieval`, `notfound`, `deep-check`, `memory`, `safety`, `embed-probe`, and from M15 `conversations`, `faithfulness` and `all`. It SHALL accept the options `--profile`, `--limit N`, `--start N`, `--set NAME`, `--max-usd`, `--yes`, `--allow-peak` and, from M15, `--probe`. An unknown suite SHALL exit non-zero and list the known ones. `--profile` SHALL keep its default of `naive`, whatever the app's default profile is.

#### Scenario: Unknown suite
- **WHEN** `horizon eval everything` is run
- **THEN** it exits non-zero, and the message lists the known suites, `conversations` and `all` among them

#### Scenario: The eval default stays naive
- **WHEN** `horizon eval decisions` is run without `--profile` on an app whose default is `agent`
- **THEN** the run's report says profile `naive`

### Requirement: The latency suite
`horizon eval latency` SHALL run real `agent` turns through the live app path in an isolated copy, with the store bypassed. It SHALL stop each turn at its first word, and report the time to the face and to the first word (p50 and p90 with order-statistic intervals) against NFR-01. It SHALL also report Jev's `turn_plan` latency distribution and how often its deadline fired. Each part SHALL run and discard its first 5 turns as warm-up. Each run SHALL record its time window (off-peak or peak, and the local clock) and the chat provider used.

#### Scenario: Never from the store
- **WHEN** the latency suite runs twice
- **THEN** both runs send every request to the provider, and neither reads or writes the store

#### Scenario: Stopped at the first word
- **WHEN** a latency turn's first token arrives
- **THEN** the suite sends Stop, and the message ends `interrupted`

#### Scenario: Warm-up is discarded
- **WHEN** a part runs 105 turns
- **THEN** the first 5 appear in the per-turn file marked warm-up, and the percentiles use the other 100

## ADDED Requirements

### Requirement: The must-pass latency run
`horizon eval latency --part blended` SHALL run, one turn at a time:
- 100 quick 1:1 turns;
- 100 deep 1:1 turns (deep forced by fixture, the rewrite decided live);
- 50 group turns;
- 50 debate turns;
- 25 deep watch turns.

It SHALL run on a database with the seed documents and memories indexed. It SHALL report NFR-01's blended p50 and p90 at a deep rate fixed before the run, NFR-02, and NFR-29.

#### Scenario: The blended figure
- **WHEN** the run ends with the conversations run's `agent` deep rate set as the blend rate
- **THEN** the report gives the blended p50 and p90 time to the first word with intervals, the quick and deep figures apart, and whether NFR-01 is met

#### Scenario: Group and debate
- **WHEN** the group and debate parts end
- **THEN** the report gives the time to the next speaker (p50, against 3 s), the share of `turn.next` within 500 ms, and how often the debate plan missed its deadline

### Requirement: The per-stage breakdown
The must-pass run SHALL break each deep turn into stages: Jev call 1, the embedding wait, the local search, Jev call 2 as the slowest of its parallel requests, DeepSeek's first token, the output check past the stream's end, and recall's check where it runs. For each stage it SHALL report p50 and p90 and the late rate against its deadline. It SHALL also report the provider cache hit and its cost. It SHALL change no setting.

#### Scenario: A stage named
- **WHEN** a deep turn misses NFR-01's p90
- **THEN** the report shows which stage's time grew, beside that stage's deadline and late rate

#### Scenario: Deadlines are reported, not changed
- **WHEN** the output check passes its 800 ms deadline on some turns
- **THEN** the report gives the late count, and `seed/pricing.json` is unchanged

### Requirement: Frozen transcripts for layer 3
`evals/transcripts/` SHALL hold 20 frozen transcripts of 8–12 turns across both seed worlds: 1:1 × 6, group × 5, debate × 4, watch × 5, four of them past one drop. Each SHALL store, per turn:
- the user lines;
- the earlier character lines;
- the rolling summary in force;
- the memory list at the start.

They SHALL hold at least 10 non-English or mixed user lines and 10 planted wrong claims, each labelled. They are split by transcript with the hash rule, once.

#### Scenario: Count and shape
- **WHEN** the transcripts are loaded
- **THEN** there are 20 with the mode counts above, each with 8–12 compared turns, and the labelled non-English and wrong-claim lines number at least 10 each

#### Scenario: Cut from a committed history
- **WHEN** a debate or watch transcript is loaded
- **THEN** it names the committed history and the window it was cut from, and its lines equal that history's lines

### Requirement: The conversations suite
`horizon eval conversations` SHALL, at each compared turn of each frozen transcript, rebuild the stored history and let `agent` and `naive` each reply through their live path, in separate isolated copies:
- `agent` with every plan, check and deep turn it would run live;
- `naive` with its router or fixed order.

Each profile picks its own speaker. The judges SHALL see each reply with its speaker's name.

#### Scenario: Same history for both
- **WHEN** one compared turn is run
- **THEN** both profiles' requests carry the same stored lines, summary and memory list, and differ only in what each profile adds

#### Scenario: A stopped run
- **WHEN** the run is stopped mid-conversation
- **THEN** every reply and judge answer already saved stays whole, and the run ends `incomplete` with no figure for the unfinished conversation

#### Scenario: Offline
- **WHEN** smoke runs `conversations --limit 1` per mode in test mode
- **THEN** it completes on the fake with canned replies and judge answers, at $0

### Requirement: Layer 3 judgements and statistics
Each compared reply SHALL get:
- stays in character (voice, persona facts, answers the last line, stays in the story; combined in code);
- the free reply-rule checks, plus the assistant-voice and flattery nouls on a 100-reply sample, language on the non-English lines and push-back on the planted claims;
- face and words agree;
- citation support where it cites;
- the pairwise judge in both orders.

The pairwise figure SHALL be the mean p(agent better) over both orders, with a paired bootstrap over whole conversations.

#### Scenario: Pairwise report
- **WHEN** the conversations suite ends
- **THEN** the report gives the mean p(agent better) with its 95 % interval, win/tie/loss counted only where both orders agree with an exact sign test, the order-disagreement rate and the win rate split by which reply was longer

#### Scenario: English first
- **WHEN** the report is written
- **THEN** each target is read on the test split for English lines first, and other languages are shown as direction only

#### Scenario: An unvalidated judge
- **WHEN** a layer-3 judge's current version has not passed B4
- **THEN** its figures are marked "NOT COUNTED", and its saved states can be re-scored after it passes without new replies

### Requirement: Free runs in the conversations suite
The conversations suite SHALL run one free conversation per mode with each profile. It SHALL also run, for `agent`: 3 watch runs of 30 turns, 3 group runs of 12 user lines, and 2 debates. From them it SHALL report the fallback and timeout rates (uncached calls only) and cost per turn, plus the repeated-opener and catchphrase rates, talk finished, the debate phases, and keeps-side and engages for `agent` beside `naive`.

#### Scenario: Debate targets
- **WHEN** the free debates end
- **THEN** the report gives `agent`'s keeps-side and engages rates against 95 % and 80 %, beside the `naive` column

### Requirement: The pairwise judge is validated on clean pairs
The pairwise judge's 30 known-winner pairs SHALL each set a real reply against a copy with one unmistakable planted defect: a reply to a different user line, the reply in assistant voice, another character's reply to the same line, or a reply that contradicts a stated persona fact. Each pair SHALL be asked in both orders, and the judge passes at 90 % or more.

#### Scenario: Rebuilt set
- **WHEN** `decisions --set judges` runs the pairwise judge's v3 set
- **THEN** 60 requests are sent (30 pairs, both orders), and the result is recorded per version

### Requirement: The store probe and `all`
`--probe` SHALL run any suite in probe mode (see `response-store`). `horizon eval all` SHALL run every suite in probe mode and print, per suite, its hits, its "would pay" items and their estimate. It SHALL never send a request. Re-running a suite that would pay SHALL need its own run and the user's OK.

#### Scenario: All is free
- **WHEN** `horizon eval all` is run
- **THEN** no provider request is sent, nothing is spent, and the table lists every suite

#### Scenario: An unchanged suite reproduces
- **WHEN** a suite the probe found all hits is run normally
- **THEN** it is served entirely from the store, spends $0 and reproduces its accepted figures

### Requirement: The naive arms of debate and memory
`horizon eval debate --profile naive` SHALL score the `naive` single-call verdict on the 12 debates, balanced and planted, with the side blocks swapped, beside the `agent` column. `horizon eval memory --profile naive` SHALL run the `naive` writer on the rewrite stretches and the two-session pairs, beside the `agent` column. `conversations` SHALL report the note-in-tag rate of `naive`'s replies, read on their raw text (the debate arm writes no argument, only verdicts, and its report says where the rate is read).

#### Scenario: Debate columns
- **WHEN** the `naive` debate arm ends
- **THEN** the report shows `naive` and `agent` side by side on the same debates, by the debate suite's own rules

### Requirement: Sentence faithfulness on two-passage questions
A sentence-faithfulness judge SHALL ask, for each factual sentence of a deep reply, whether the kept passages support it. It SHALL be validated (B4) before its figures count. It SHALL run on the retrieval suite's 10 two-passage questions as deep turns.

#### Scenario: Per-sentence result
- **WHEN** a two-passage item's reply has three factual sentences
- **THEN** three judge questions are asked, each with the kept passages and one sentence, and the item's rate is supported sentences over factual sentences

### Requirement: The emotion set grows by 40
The emotion decision set SHALL gain 40 items, labelled blind and split by the hash rule before any run, because its interval straddled the target (E8's rule). The test split SHALL be read once at the shipped floor.

#### Scenario: Grown set
- **WHEN** the emotion set is loaded
- **THEN** it holds 140 items, the 40 new ones labelled before the run that reads them

### Requirement: The Jev request manifest
`horizon eval manifest` SHALL write `evals/baselines/jev-1.13-requests.json` at no cost, sending nothing. For each Jev set (every decisions folder with the judges, the canary, deep-check, and safety's Jev parts), it SHALL record the SHA-256 of every request body (state and questions, without the model) as the suite compiles it, and how many have a stored jev-1.13 answer. It SHALL also record the bank versions and the canary fingerprint. Private items SHALL appear only as hashes. A later model comparison (`--against-manifest`) SHALL refuse any Jev body the manifest doesn't list.

#### Scenario: A body that changed
- **WHEN** a comparison run builds a request whose body hash is not in the manifest
- **THEN** it refuses to send that item and names it
