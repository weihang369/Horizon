# Spec Delta

## ADDED Requirements

### Requirement: The memory writer reads a whole stretch
The memory writer port SHALL take a session's stretch (the numbered new lines, the context lines, the header and each present character's current list) and return memory operations per character. It SHALL replace the per-reply writer. `naive` and `agent` SHALL each resolve their own writer; `scripted` SHALL write nothing.

#### Scenario: Profile with no key
- **WHEN** the `naive` profile has no key
- **THEN** pause runs are deferred rather than written by the scripted writer

### Requirement: Session recall is an agent port
`agent` SHALL recall through a session-recall port called from the deep work, over corpora the runtime binds to the speaker's world, session and character. `naive` and `scripted` SHALL keep their memory retrievers in the tail, unchanged.

#### Scenario: Naive unchanged
- **WHEN** a `naive` reply is made in a session with indexed lines
- **THEN** its memories come from the keyword memory retriever, and no recall check is made
