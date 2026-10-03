# Reducer fixtures

These fixtures pin the session reducer. Sessions are event-sourced (D-79): messages and session state are **derived** from `session_events`. The TypeScript reducer (`frontend/src/engine/sessionReducer.ts`) and its Python port (`backend/horizon/domain/reducer.py`, M1b) must reduce every case here to the same result.

## Case format

```json
{
  "schemaVersion": 1, "name": "…", "description": "…",
  "session": { /* Session before the first event */ },
  "events":  [ /* SessionEvent[], seq 1..n */ ],
  "expected": { "session": { /* Session after reduce */ }, "messages": [ /* Message[] ordered by seq */ ] }
}
```

- **Run:** start from `session` with no messages, apply `events` in order, then deep-compare `expected.session` and `expected.messages`. A key that is missing means "absent" (`undefined`/`None`), never `null`.
- **Scope:** runtime-only UI state (typing indicator, held emotions, energy floats) is not part of the contract and isn't compared.
- **The big equivalence test** is still every seed session (`seed/sessions/*/events.json` → `messages.json`). These small cases isolate one rule each: insight replacement, regenerate variants, stop, manual emotion, `session.state` patches, and a stream-cut error.
- **Provenance:** the events were written by hand. `expected` was produced once by the TypeScript reducer, then reviewed by hand against doc 05 §6. To change a case, edit it on purpose in both languages at once.
