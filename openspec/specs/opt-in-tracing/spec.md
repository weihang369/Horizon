# opt-in-tracing Specification

## Purpose

Opt-in tracing lets a developer send traced AI steps to LangSmith with their own key. It is off by default and guarded, so no variable left in a shell can send data by accident, and it is the one documented exception to "no telemetry".

## Requirements

### Requirement: Tracing is forced off unless opted in
Unless `HORIZON_LANGSMITH=1`, every entry point (the server, the CLI and the test suite) SHALL set `LANGSMITH_TRACING_V2`, `LANGCHAIN_TRACING_V2`, `LANGSMITH_TRACING` and `LANGCHAIN_TRACING` to `false` before any tracing library is imported. Every graph SHALL run inside a context that disables tracing.

#### Scenario: Stray shell variable
- **WHEN** the backend starts with `LANGCHAIN_TRACING_V2=true` in the environment and `HORIZON_LANGSMITH` unset
- **THEN** the process environment reads `false` for all four variables, and nothing is traced

### Requirement: Opting in
With `HORIZON_LANGSMITH=1`, a `LANGSMITH_API_KEY` and the optional tracing install, the gateway's paid calls SHALL appear as traced steps. The key SHALL be passed to the tracing client explicitly. Start-up SHALL log a warning that chat and document text are sent to LangSmith. If the key or the install is missing, start-up SHALL log an error and tracing SHALL stay off.

#### Scenario: Missing install
- **WHEN** `HORIZON_LANGSMITH=1` is set without the tracing install
- **THEN** start-up logs an error naming the install step, and the backend runs untraced

### Requirement: The OpenRouter key is never traced
Traced inputs SHALL be the redacted request bodies and Jev states, never HTTP headers.

#### Scenario: Traced reply
- **WHEN** a reply is traced with a stub tracing client
- **THEN** no traced input contains the OpenRouter key or an `Authorization` header

### Requirement: Known variables
`HORIZON_LANGSMITH`, `LANGSMITH_API_KEY` and `HORIZON_CAPTURE_AI_CALLS` SHALL be read from the environment and `.env`, and SHALL be listed in `.env.example` with a comment on what each sends or stores.

#### Scenario: From .env
- **WHEN** `.env` sets `HORIZON_CAPTURE_AI_CALLS=1`
- **THEN** capture is on at start-up
