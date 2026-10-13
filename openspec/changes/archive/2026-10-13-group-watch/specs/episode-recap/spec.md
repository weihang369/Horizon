# Spec Delta

## Purpose

Watch's Summarise writes a real recap of the scene for the viewer: one DeepSeek call in `naive` and `agent`, a canned
recap only in the scripted demo, and a plain note instead of a fake recap when the call fails.

## ADDED Requirements

### Requirement: Summarise is one DeepSeek call
Under `naive` and `agent` with a key, `watch.summarise` SHALL make one non-streamed chat call with the `episode` settings row, purpose `episode_summary` (ledger category `summary`), and a 30-second limit (`timeoutsMs.episode`). Its input SHALL be the premise, the cast's names and roles, the rolling summary when one exists, and the history window as `Name: line` lines. It SHALL never drain a character's energy.

#### Scenario: Ledger row
- **WHEN** a `naive` watch is summarised with a key
- **THEN** one ledger row has `purpose: "episode_summary"`, `category: "summary"` and the session's ID, and no character's energy changes

### Requirement: The recap's form
The recap SHALL be posted as one `note` message of kind `summary`, at most 120 words: longer output is cut at a sentence end. An empty output SHALL count as a failure.

#### Scenario: Over-long recap
- **WHEN** the model returns 160 words
- **THEN** the posted recap has at most 120 words and ends at a sentence end

### Requirement: A failed recap leaves a note, never a fake recap
A provider error, timeout, refusal or empty output SHALL post a system note "The recap couldn't be written this time. Try Summarise again." and no `summary` message. A daily-cap refusal SHALL pause the session as any capped call does.

#### Scenario: Timeout
- **WHEN** the recap call passes its 30-second limit
- **THEN** the session gains that system note, and no `summary` message

### Requirement: The scripted recap
The `scripted` profile and the MockClient SHALL keep the canned recap, and record one simulated call with purpose `episode_summary`. `naive` and `agent` SHALL never record a simulated recap call.

#### Scenario: No fake row under naive
- **WHEN** a `naive` watch with a key is summarised
- **THEN** the ledger has no simulated recap row, only the real call's row
