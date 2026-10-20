## ADDED Requirements

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
