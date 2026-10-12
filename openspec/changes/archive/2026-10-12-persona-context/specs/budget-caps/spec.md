# Spec Delta

## MODIFIED Requirements

### Requirement: Cost estimates per category
Before a paid call, the backend SHALL estimate its cost from the committed price table:
- **chat:** the stable prefix at the cached rate when the prefix is warm, otherwise at the input rate; other input at the input rate; and expected output at the output rate. Expected output is `min(max_tokens, p75 of the character's last 10 replies)`, with 220 standing in for the p75 when the character has no replies yet.
- **decision:** input tokens × the decision input rate, with output free. The state SHALL be counted once per request, plus each question's own tokens, plus a fixed 300-token allowance per request for the model's own instructions, because Jev bills the state once and adds 160–275 tokens of its own to every request.
- **image:** the per-image generation price for its kind (portrait, tweak, emotion edit, blink frame or expression sheet).
- **profile:** the profile-draft price, split evenly across the draft's tasks.
- **music:** the song price when a music model is used, and zero for the procedural theme.
- **embedding:** tokens × the embedding rate.

At peak, chat estimates SHALL be multiplied by the configured peak multiplier (2). Actual costs SHALL always come from the provider. The evaluation harness SHALL estimate decisions with the same formula.

#### Scenario: Peak chat estimate
- **WHEN** the same chat request is estimated off-peak and at peak
- **THEN** the peak estimate is twice the off-peak estimate

#### Scenario: Decision estimate
- **WHEN** a decision whose state and questions count 10,000 input tokens is estimated
- **THEN** the estimate is $0.0004326 (10,300 tokens at $0.042 per million)

#### Scenario: State counted once
- **WHEN** one decision asks 8 short questions about a 600-token state
- **THEN** the estimate counts the state's tokens once, plus each question's tokens, plus the 300-token allowance once

#### Scenario: Emotion edit estimate
- **WHEN** one emotion edit is estimated with the shipped price table
- **THEN** the estimate is $0.018
