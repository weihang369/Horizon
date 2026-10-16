# Spec Delta

## ADDED Requirements

### Requirement: Leave and end start a pause run
`sessions.leave` on an active non-seed session, and `sessions.end`, SHALL request the session's memory pause run (see `long-term-memory`). A reply still streaming SHALL be read by a run requested again at its `turn.end`.

#### Scenario: End during a reply
- **WHEN** a 1:1 session is ended while a reply streams
- **THEN** a run reads the lines before the reply, and once the reply ends a second run reads the reply

### Requirement: A fork starts its memory checkpoint at the copied history
A fork, including "Continue live" from a recording, SHALL set its memory checkpoint to the highest message number it copied, in the transaction that creates it, and SHALL copy the indexed lines and their vectors of the messages it copies.

#### Scenario: Continue live
- **WHEN** a seed recording is continued live and the user sends one message, and the session pauses
- **THEN** the run reads only the new message and its reply, and earlier lines of the recording are found by recall without any embedding call

### Requirement: Deletes cancel memory work
Deleting a session SHALL cancel its pause run and zero its indexed lines' vectors before they are deleted. Deleting a character or a world SHALL cancel every run that character or world is part of.

#### Scenario: Delete a character mid-run
- **WHEN** Amara is deleted while a group run with Amara and Mei is in flight
- **THEN** the run writes nothing for either, and its calls are recorded `cancelled`
