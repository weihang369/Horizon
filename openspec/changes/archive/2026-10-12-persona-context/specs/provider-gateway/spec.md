# Spec Delta

## MODIFIED Requirements

### Requirement: Canned responses per purpose in test mode
The fake provider SHALL answer chat requests for a purpose with that purpose's selected canned responses, in turn, in the requested streaming or complete form, with real-shaped usage. A purpose with no selection SHALL keep the default answer. The committed canned sets SHALL include group A's 20 real profile drafts and real rolling summaries recorded by M8's summary suite.

#### Scenario: Canned drafts
- **WHEN** the `profile-drafts` set is selected for purpose `profile` and a naive draft job runs
- **THEN** the drafter receives the first recorded draft, and the draft validates

#### Scenario: Canned rolling summaries
- **WHEN** the rolling-summary set is selected for purpose `rolling_summary` and a test session's window drops
- **THEN** the summary task receives the first recorded summary, and a `rolling` row with that text is written

## ADDED Requirements

### Requirement: Rolling summaries are labelled as summary spend
A rolling summary call SHALL carry purpose `rolling_summary` in ledger category `summary`, separate from watch's episode summary. It SHALL be labelled by the same purpose factory as every other call, so it never drains energy.

#### Scenario: Ledger row
- **WHEN** a naive session's summary call completes
- **THEN** its ledger row has `category: "summary"`, `purpose: "rolling_summary"`, the session's ID and no message ID
