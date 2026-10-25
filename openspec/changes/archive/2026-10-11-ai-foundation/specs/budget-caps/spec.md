## MODIFIED Requirements

### Requirement: Cost estimates per category
Before a paid call, the backend SHALL estimate its cost from the committed price table:
- **chat:** the stable prefix at the cached rate when the prefix is warm, otherwise at the input rate; other input at the input rate; and expected output at the output rate. Expected output is `min(max_tokens, p75 of the character's last 10 replies)`, with 220 standing in for the p75 when the character has no replies yet.
- **decision:** input tokens × the decision input rate, with output free. The state SHALL be counted once per request, plus each question's own tokens, because Jev bills the state once.
- **image:** the per-image generation price for its kind (portrait, tweak, emotion edit, blink frame or expression sheet).
- **profile:** the profile-draft price, split evenly across the draft's tasks.
- **music:** the song price when a music model is used, and zero for the procedural theme.
- **embedding:** tokens × the embedding rate.

At peak, chat estimates SHALL be multiplied by the configured peak multiplier (2). Actual costs SHALL always come from the provider.

#### Scenario: Peak chat estimate
- **WHEN** the same chat request is estimated off-peak and at peak
- **THEN** the peak estimate is twice the off-peak estimate

#### Scenario: Decision estimate
- **WHEN** a decision with 10,000 input tokens is estimated
- **THEN** the estimate is $0.00042

#### Scenario: State counted once
- **WHEN** one decision asks 8 short questions about a 600-token state
- **THEN** the estimate counts the state's tokens once, plus each question's tokens

#### Scenario: Emotion edit estimate
- **WHEN** one emotion edit is estimated with the shipped price table
- **THEN** the estimate is $0.018
