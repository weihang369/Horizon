## ADDED Requirements

### Requirement: Contract revision 1.4 is additive
Rev 1.4 SHALL add one optional field, `TurnTrace.system1`, with the shape in the `system1-trace` capability, to `types.ts`, the schemas and the exported `schema.json`. `SCHEMA_VERSION` SHALL stay `1`. Every rev 1.3 entity and event SHALL still validate. Any other contract change SHALL need its own approval.

#### Scenario: Old trace validates
- **WHEN** a stored rev 1.3 trace without `system1` is validated against the rev 1.4 schema
- **THEN** it passes

#### Scenario: Row limit in the schema
- **WHEN** a trace with 65 `system1` question rows is validated
- **THEN** validation fails

#### Scenario: Scripted and mock rows validate
- **WHEN** the scripted backend and the MockClient each produce a group turn's trace
- **THEN** both traces' `system1` sections pass the exported schema, and the schema-export and fixture checks pass
