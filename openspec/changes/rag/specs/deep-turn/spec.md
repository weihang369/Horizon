# Spec Delta

## Purpose

Defines an `agent` reply that uses the speaker's own documents: how a gate's yes becomes a query, how the candidate
passages are checked by Jev and kept by code, what the reply is told for each outcome, and how its citations and trace
are built.

## ADDED Requirements

### Requirement: A turn goes deep only on its gate
Under `agent`, a reply SHALL search its speaker's documents only when the speaker's own "needs documents?" answer in
its plan is at or above `t_gate`. A late, failed or refused gate, a dropped gate, or a speaker with no searchable
source SHALL give a quick reply with no search, no embedding and no `deep_check` call.

#### Scenario: Gate below threshold
- **WHEN** Amara's `docs` answer is p 0.2 with `t_gate` 0.35
- **THEN** her reply is quick: no `query_embed`, `query_rewrite` or `deep_check` ledger row is written for it

#### Scenario: Gate late
- **WHEN** the plan holding Amara's `docs` question falls back on its deadline
- **THEN** her reply is quick, and her `docs` System 1 row has `result: "fallback"`

### Requirement: The query is built at the gate, in parallel
When a turn goes deep, keyword search over the message's terms, the message's embedding (only if the speaker has an `indexed` source in the active space) and, in 1:1 and group, the rewrite (only when the message is not standalone or not English) SHALL all start together. A rewrite that lands in time SHALL be searched together with the message: its words join the keyword terms and it is embedded.

In 1:1 and when a group message is answered (the cast plan and the follow plan), the user message's embedding SHALL start with the plan's Jev request, for the first candidate with an `indexed` source, before the gate answers (the user's choice of 2026-10-15, after the query embedding measured ≈ 1.1 s at the median). The deep path's own request for the same text SHALL join it, so one `query_embed` row exists per message. The search SHALL wait for each vector at most `retrieval.agent.queryEmbedWaitMs` (800 ms) from when it needs it; a late vector means keywords only for that text.

#### Scenario: Follow-up rewritten
- **WHEN** Kai asks Amara "and nights?" after a question about long shift blocks, with `standalone` p 0.06
- **THEN** one `query_rewrite` call is made, and the search uses both the rewrite and the message

#### Scenario: Standalone English question
- **WHEN** a deep 1:1 message is standalone and in English
- **THEN** no `query_rewrite` call is made, and the message is searched as written

#### Scenario: Keyword-only speaker
- **WHEN** a deep turn's speaker has only `keyword_only` sources
- **THEN** no `query_embed` row is written and the search uses keywords only

#### Scenario: The embedding starts with the plan
- **WHEN** Kai sends Hana, who has an `indexed` source, a message whose `docs` gate comes back at 0.1
- **THEN** the reply is quick, and exactly one `query_embed` row exists, linked to Kai's message

#### Scenario: A deep turn joins the early embedding
- **WHEN** the same message's gate comes back at 0.8 and the turn goes deep
- **THEN** still exactly one `query_embed` row exists for the message text

### Requirement: The rewrite is checked, bounded and reused
A rewrite SHALL be used only if it is one line, at most 30 words, mostly Latin script and not empty. It SHALL be abandoned after `rewriteMs`. An accepted rewrite SHALL be stored for that user message and speaker, reused on regenerate with no new call, and never used by another speaker. Debate and watch turns SHALL NOT rewrite.

#### Scenario: Regenerate reuses the rewrite
- **WHEN** a reply that used a rewrite is regenerated and goes deep again
- **THEN** no new `query_rewrite` call is made, and the same rewrite is searched

#### Scenario: Group repliers rewrite apart
- **WHEN** both replies to a group message go deep and need a rewrite
- **THEN** each speaker gets its own `query_rewrite` call, and one `query_embed` row exists for the message text

#### Scenario: Rewrite rejected
- **WHEN** the rewrite comes back as two lines
- **THEN** it is not used, and the search uses the message plus its two earlier lines, marked as a fallback query

### Requirement: Each candidate passage is checked by Jev
A deep turn SHALL ask Jev one `deep_check` question per candidate passage (at most 8), all sent at once, each answered on three levels (answers it, partly, doesn't help) by `deepCheckMs`. When no passage answers it but two or more are usable, one more `deep_check` request SHALL ask whether the usable passages answer it together.

#### Scenario: Eight requests
- **WHEN** a deep turn's search returns 8 candidates
- **THEN** 8 `deep_check` decision rows are written, each linked to the reply's message

#### Scenario: Set check
- **WHEN** no candidate reaches `t_found` and two are usable
- **THEN** one more `deep_check` request is made over those two

### Requirement: Code keeps the passages by rule
A passage SHALL be usable when p(answers) + p(partly) ≥ `t_keep`, and found when p(answers) ≥ `t_found`. The outcome SHALL be:
- found: a found passage, or a set check that said yes;
- partly: no found passage, but a usable one;
- not found: no usable passage with every request back.

At most k usable passages SHALL be kept, best first (3 in 1:1, 2 otherwise).

#### Scenario: Group keeps two
- **WHEN** a group reply's check finds three usable passages
- **THEN** the two with the highest weighted scores are kept

#### Scenario: Not found needs every answer
- **WHEN** 6 of 8 checks return "doesn't help" and 2 are late
- **THEN** the outcome is the fallback, not "not found"

### Requirement: What each outcome does
On found, the reply SHALL get the kept passages at the deep length. On partly, it SHALL get the passages, plus the partly line when abstaining is allowed. On not found with abstaining allowed, it SHALL get the not-found line at the quick length and no passages; otherwise a quick reply. Abstaining SHALL be allowed only for a reply to a user message in 1:1 or group with p(needs documents) ≥ `t_confident`.

#### Scenario: Confident not found in 1:1
- **WHEN** a 1:1 question's gate is p 0.9 and no passage is usable
- **THEN** the reply carries no citation, its request holds the not-found line, and its reply cap is the quick one

#### Scenario: Debate never abstains
- **WHEN** a debate argument's check finds nothing usable
- **THEN** the argument is a quick reply with no not-found line

### Requirement: Jev call 2 failures fall back to the search order
When Jev call 2 fails, or some answers are missing and none of the returned ones is found, the reply SHALL keep the top k candidates in search order with no outcome and no scores. Its citations SHALL carry no `score`, and its `deep_check` entry in `trace.calls` SHALL have `fallback: true`.

#### Scenario: Rate limited
- **WHEN** every `deep_check` request returns HTTP 429
- **THEN** the reply cites from the top k search results, no citation has a `score`, and the trace marks the fallback

### Requirement: The deep work starts as early as each mode allows
The deep work SHALL start once the speaker is known and its gate said yes:
- in 1:1 inside the plan;
- in group when the cast or follow plan lands;
- in watch when the plan made ahead lands;
- in debate when the member is fixed and its gate answer is in, or when an opening's prefetch starts.

It SHALL be cancelled with the turn or the plan it belongs to.

#### Scenario: Watch plan made ahead
- **WHEN** a watch plan made during the pause picks Mei and her gate says yes
- **THEN** Mei's `deep_check` requests are sent before her turn's `turn.next`

#### Scenario: Stop during the checks
- **WHEN** Stop lands while a deep turn's `deep_check` requests are in flight
- **THEN** no reply is written, every held request is recorded `cancelled`, and the session accepts a new message

### Requirement: Citations come from the kept list
The kept passages SHALL be numbered [1] to [k] before the reply request. A citation SHALL be built only for a number the reply wrote that is on the list, from the stored passage, never from the reply's text. Its quote SHALL be the run of whole sentences, within 400 characters, that shares the most words with the query, and the passage's start when nothing overlaps.

#### Scenario: Invented marker
- **WHEN** a reply with two kept passages writes [1] and [3]
- **THEN** only passage 1 becomes a citation, and "[3]" stays in the text

#### Scenario: Quote holds the fact
- **WHEN** a 1,500-character passage answers the question in its fourth sentence
- **THEN** the citation's quote includes that sentence

### Requirement: The deep turn's trace
`trace.knowledge` SHALL hold the query searched (at most 120 characters), `trigger: "gated"`, and the checked candidates, each with its score, whether it was cited, and its number when kept. On not found, the candidates SHALL be listed with none cited. `context.used.knowledge` SHALL count the documents block.

#### Scenario: Rewritten query shown
- **WHEN** a deep reply searched a rewrite
- **THEN** `trace.knowledge.query` is the rewrite, and `trace.knowledge.trigger` is "gated"

### Requirement: A deep turn replays without new calls
The passages a deep turn kept, its outcome, its candidates and its query SHALL be frozen into the turn's plan. Serialising the turn context to JSON and loading it again SHALL rebuild the same reply request with no Jev, embedding or rewrite call.

#### Scenario: Replay
- **WHEN** a deep 1:1 turn's context is serialised and loaded again
- **THEN** the reply request is byte-identical, and no decision, embedding or chat request is made before it

### Requirement: The rewrite's storage is derived data
A stored rewrite SHALL live with the user message it answers, outside the session's events. Forking a session SHALL copy the stored rewrites of the messages it copies. Deleting a message SHALL delete its stored rewrites.

#### Scenario: Fork keeps the rewrite
- **WHEN** a session whose message has a stored rewrite is forked after that message, and the copy's reply is regenerated
- **THEN** the copy reuses the rewrite with no `query_rewrite` call
