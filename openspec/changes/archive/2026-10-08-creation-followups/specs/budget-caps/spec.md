## ADDED Requirements

### Requirement: No setting pre-authorises generation spend
Paid generation SHALL start only from an explicit user action. The app SHALL NOT offer a setting that starts paid generation in the background: the stored `autoGenerateMissingEmotions` setting SHALL stay readable and writable through the API, but the settings screen SHALL NOT show it, and nothing SHALL start a job because of it.

#### Scenario: Setting is hidden
- **WHEN** the user opens the Cost tab in Settings
- **THEN** no "Auto-generate missing emotions" control is shown

#### Scenario: Stored value has no effect
- **WHEN** `autoGenerateMissingEmotions` is set to true through the API and a character with missing emotions is opened
- **THEN** no generation job is started and no ledger row is written
