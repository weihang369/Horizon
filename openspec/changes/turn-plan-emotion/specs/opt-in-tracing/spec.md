## MODIFIED Requirements

### Requirement: Opting in
With `HORIZON_LANGSMITH=1`, a `LANGSMITH_API_KEY` and the tracing package, the gateway's paid calls SHALL appear as traced steps. The tracing package SHALL be installed with the backend from M9 on, as a dependency of the plan graph, so opting in needs only the flag and the key. Installing it SHALL never enable tracing by itself. The key SHALL be passed to the tracing client explicitly. Start-up SHALL log a warning that chat and document text are sent to LangSmith. If the key or the package is missing, start-up SHALL log an error and tracing SHALL stay off.

#### Scenario: Missing install
- **WHEN** `HORIZON_LANGSMITH=1` is set and the tracing package can't be imported
- **THEN** start-up logs an error naming the install step, and the backend runs untraced

#### Scenario: Installed but not opted in
- **WHEN** the backend starts with the tracing package installed and `HORIZON_LANGSMITH` unset
- **THEN** tracing is off, and a planned turn opens no connection to LangSmith
