## ADDED Requirements

### Requirement: Naive edits need a raster base
With the naive image generator, `jobs.start` for an `emotion_set`, `emotion_regenerate` or `portrait_tweak` job SHALL reject with `validation`, before anything is stored or reserved, when the character has no locked base (`details.reason: "no_base"`) or when its base is a vector placeholder (`details.reason: "base_not_raster"`). The client SHALL show `base_not_raster` as "Generate a portrait first", with an action that opens the character's portrait step.

#### Scenario: SVG base under the naive generator
- **WHEN** the naive image generator is selected and an `emotion_set` job is started for a seed character whose base portrait is an SVG
- **THEN** the call rejects with `validation` and `details.reason: "base_not_raster"`, no job row exists, and nothing is reserved

#### Scenario: Client offers the portrait step
- **WHEN** starting an emotion edit fails with `base_not_raster`
- **THEN** the user sees "Generate a portrait first" with a button, and pressing it opens the portrait step for that character (in edit mode for an approved character)

#### Scenario: Scripted generator edits an SVG base
- **WHEN** the scripted image generator is selected and an `emotion_set` job is started for a character whose base portrait is an SVG
- **THEN** the job starts normally
