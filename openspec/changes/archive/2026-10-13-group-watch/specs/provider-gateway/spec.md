# Spec Delta

## MODIFIED Requirements

### Requirement: Per-purpose timeouts
The gateway SHALL apply these default timeouts, all overridable by config:

| Call | Timeout |
|---|---|
| Chat, time to first token | 20 s |
| Images | 180 s |
| Embeddings | 30 s |
| Watch episode recap (whole call) | 30 s |
| Decision `route` | 400 ms |
| Decision `turn_plan` | 700 ms |
| Decision `follow_plan` | 400 ms |
| Decision `debate_plan` | 500 ms |
| Decision `guardrail` | 700 ms |
| Decision `guardrail_prompt` | 1,500 ms |
| Decision `reaction` | 1,500 ms |
| Decision `face_check` | 1,500 ms |
| Any other decision | 3 s |

An exceeded timeout SHALL surface as `timeout`.

#### Scenario: Route decision too slow
- **WHEN** a `route` decision's recorded response is delayed past 400 ms
- **THEN** the call fails with `timeout`

#### Scenario: Removed keys
- **WHEN** the shipped price table is loaded
- **THEN** it has no `gate`, `rerank` or `emotion` decision timeout and no `fallbackModel`

#### Scenario: Recap limit
- **WHEN** the shipped price table is loaded
- **THEN** `timeoutsMs.episode` is 30000, and the MockClient's mirror holds the same value

## ADDED Requirements

### Requirement: Follow plans and recaps are labelled at the source
A follow plan SHALL carry purpose `follow_plan` in ledger category `decision`, and a watch recap SHALL carry purpose `episode_summary` in category `summary`. Both SHALL be labelled by the shared purpose factory, so neither drains energy, and both count toward the daily cap.

#### Scenario: Follow-plan row
- **WHEN** an `agent` group's follow plan is answered
- **THEN** its ledger row has `category: "decision"`, `purpose: "follow_plan"` and the session's ID, and the call is listed on the trace of the reply it explains

### Requirement: A refused follow plan pauses nothing
A daily-cap refusal of a `follow_plan` request SHALL publish the cap event without pausing live sessions, as for the after-turn purposes; the next reply's own preflight takes the pause.

#### Scenario: Cap reached at the follow plan
- **WHEN** the daily cap is reached exactly when a follow plan is requested
- **THEN** no second reply is made, no `session.paused` event comes from the follow plan, and the next reply's preflight pauses the session
