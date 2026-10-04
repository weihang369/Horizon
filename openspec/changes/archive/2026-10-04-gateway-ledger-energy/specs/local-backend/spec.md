# Spec Delta

## MODIFIED Requirements

### Requirement: The API key never leaks
The OpenRouter key SHALL NOT appear in any response, log line, database row, error message, event, export or ledger entry. Every component that writes text out of the process SHALL redact with one shared rule: any `sk-or-` token followed by one or more of `[A-Za-z0-9_-]` becomes `sk-or-***`. That covers the log filter, the exception formatter, error envelopes, the ledger writer and the call observer hook. The rule SHALL match every key that `PUT /settings/key` accepts.

#### Scenario: Redacted log line
- **WHEN** code logs a message containing `sk-or-v1-abc123`
- **THEN** the log file contains `sk-or-***` in its place and never the original string

#### Scenario: Short test key is redacted too
- **WHEN** code logs a message containing `sk-or-good`
- **THEN** the log line contains `sk-or-***`

#### Scenario: Leak sweep
- **WHEN** a test sets a key, runs a connection test, a model probe, a 401, a 500 with the key echoed in its body, and a top-up, then reads the logs, every error response, every ledger row, `GET /usage`, the global SSE stream and every file under `data/` except `secrets.local.json`
- **THEN** none of them contains the key

## ADDED Requirements

### Requirement: Committed environment template
The repository SHALL include `.env.example` at the root. It SHALL list `OPENROUTER_API_KEY` and the `HORIZON_*` variables with blank or default values, and it SHALL never contain a real key. `.env` SHALL stay git-ignored.

#### Scenario: Template has no key
- **WHEN** `.env.example` is read
- **THEN** `OPENROUTER_API_KEY=` has an empty value, and `.env` is matched by `.gitignore`
