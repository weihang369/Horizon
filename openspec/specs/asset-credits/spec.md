# asset-credits Specification

## Purpose

Keeps a complete, checked record of where every shipped asset comes from, so that Settings → About can point to it and no AI-generated or library asset ships without provenance or credit.

## Requirements

### Requirement: ASSETS.md records every shipped asset
The repository root SHALL hold `ASSETS.md`. It SHALL contain one machine-readable table that covers every shipped asset:
- every file under `seed/assets/` and `frontend/public/`;
- every bundled font package;
- every system track in `seed/system-tracks.json`.

Each row SHALL give a pattern, a kind, a source (`procedural`, `ai`, `library` or `font`), a credit or provenance, and an SPDX licence identifier. User-generated assets under `data/` and files under `docs/` are not shipped and SHALL NOT be required.

#### Scenario: Placeholder portraits are covered
- **WHEN** `ASSETS.md` is read
- **THEN** a `procedural` row covers the placeholder portraits under `seed/assets/placeholder/portraits/`, with its generator as the credit and its licence

#### Scenario: Fonts are credited
- **WHEN** `frontend/package.json` depends on five font packages
- **THEN** `ASSETS.md` has a `font` row for each, with the font's author and its licence (e.g. `OFL-1.1`)

### Requirement: AI and library assets carry full provenance
A row whose source is `ai` SHALL name the model, the generation date, a prompt reference and the technique. A row whose source is `library` or `font` SHALL name the credit line and a valid SPDX licence. A system-track row's licence SHALL equal the licence in `seed/system-tracks.json`.

#### Scenario: AI portrait without a model
- **WHEN** an `ai` row lacks the model name
- **THEN** the asset check fails and names the row and the missing field

#### Scenario: Track licence disagrees
- **WHEN** `seed/system-tracks.json` gives `CC0-1.0` for the main theme and `ASSETS.md` gives `CC-BY-4.0`
- **THEN** the asset check fails and names the track

### Requirement: An offline check keeps ASSETS.md complete
`npm run assets:check` SHALL compare the shipped asset inventory with the `ASSETS.md` table without network access. It SHALL fail when:
- a shipped asset is matched by no row;
- a row matches no shipped asset;
- a row lacks a required field.

It SHALL produce the same result on Windows and Linux, and it SHALL run in CI.

#### Scenario: New asset without a row
- **WHEN** a new image is added under `frontend/public/` and `ASSETS.md` is unchanged
- **THEN** `npm run assets:check` fails and names the file

#### Scenario: Stale row
- **WHEN** an asset is deleted but its row stays in `ASSETS.md`
- **THEN** `npm run assets:check` fails and names the row

#### Scenario: Complete record
- **WHEN** every shipped asset is covered and every row is complete
- **THEN** `npm run assets:check` exits 0 and prints the number of assets and rows it checked

### Requirement: ASSETS.md names the music terms and the watermark
`ASSETS.md` SHALL hold a "Generated music" section, outside the machine-readable table. It SHALL record:
- Google's terms for Lyria through the API, as read (who owns the output, any use restriction, any attribution duty), with the date read and the source URL;
- that every Lyria clip carries Google's inaudible SynthID watermark;
- that songs a user generates are under those terms;
- that the seed themes stay procedural until real seed songs are committed, each with an `ai` row.

#### Scenario: The section is present
- **WHEN** `ASSETS.md` is read
- **THEN** it names SynthID, states the terms with the date they were read and their URL, and says the seed themes are procedural until Lyria seed songs are committed

#### Scenario: The check ignores the prose
- **WHEN** `npm run assets:check` runs after the section is added
- **THEN** it passes with the same rows as before
