# Spec Delta

<!-- CONDITIONAL (design D2, D16): applies only if the user switches at the gate task. If they keep jev-1.13, this
     file is deleted before archive. The id and price below are the expected candidate's; task 0.3 replaces them with
     the verified values if they differ. -->

## MODIFIED Requirements

### Requirement: Seed models and prices match the decision log
The seed SHALL record the following:
- **Image model:** `bytedance-seed/seedream-5-0-flash` at $0.018 per image, for every image generation price (D-61).
- **Decision model:** `typesafe/jev-1.14` at $0.042 per million input tokens, $0 output.
- **Embedding model:** a model with its price per million tokens.

#### Scenario: Pricing file
- **WHEN** `seed/pricing.json` is read
- **THEN** `decision.model` is `typesafe/jev-1.14`, `decision.inputPerM` is `0.042`, `decision.outputPerM` is `0`, each image price is `0.018`, and an `embedding` entry exists

#### Scenario: Settings models
- **WHEN** `seed/settings.json` is read
- **THEN** `models.decision` is `typesafe/jev-1.14`, `models.image` is `bytedance-seed/seedream-5-0-flash` and `models.embedding` is set
