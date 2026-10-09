## MODIFIED Requirements

### Requirement: A blocked reply is scrubbed
When the output guardrail blocks a reply after it has streamed, the backend SHALL end the turn with `status: "error"` and `content_refused`. It SHALL remove the reply's text from the stored message and from its stored `token` events, and SHALL exclude the reply from memory: the reply SHALL NOT be passed to the memory writer, and any memory derived from it SHALL be forgotten in the same way as a user Forget.

#### Scenario: Blocked after streaming
- **WHEN** the output guardrail blocks a completed reply
- **THEN** `turn.end` has `status: "error"`, the `error` event has `content_refused`, and neither the message content nor any stored `token` event contains the reply's text

#### Scenario: Blocked reply leaves no memory
- **WHEN** a memory writer that would remember every reply is attached and the output guardrail blocks a reply
- **THEN** the memory writer is not called for that reply, and no memory has that message as its source
