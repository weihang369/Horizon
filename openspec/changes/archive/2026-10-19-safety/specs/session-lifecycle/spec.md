## MODIFIED Requirements

### Requirement: Create a session
`sessions.create` SHALL need a usable key and SHALL validate:
- the cast size by mode (1:1 exactly 1; group, debate and watch 2–5);
- every participant `approved`;
- every participant in the session's world;
- under `agent`, for debate and watch, the motion or premise passes the motion check (see `content-safety`).

A cast-size violation SHALL reject with `validation` and `details { field: "characterIds", min, max, got }`. A character from another world SHALL reject with `not_found`. A non-approved character SHALL reject with `validation`. A refused motion or premise SHALL reject with `content_refused`, and no session SHALL be written.

#### Scenario: Wrong cast size
- **WHEN** a 1:1 session is created with two characters
- **THEN** it rejects with `validation` and `details` containing `min: 1` and `max: 1`

#### Scenario: Character from another world
- **WHEN** a session in `wld_seedMeridian` is created with `chr_seedHana` from `wld_seedSunnyHollow`
- **THEN** it rejects with `not_found`, and no session row is written

#### Scenario: A refused premise
- **WHEN** an `agent` watch is created with a premise Jev answers p 0.85 for the motion check
- **THEN** it rejects with `content_refused`, and no session row is written

#### Scenario: Jev down lets it start
- **WHEN** the motion check's request fails for a new debate
- **THEN** the session is created, and a warning is logged
