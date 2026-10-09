"""The runtime retrieval step (knowledge-memory-storage task 7.3; ai-ports "Context round-trips through JSON";
retrieval "Retrieved hits are in the context", "Retrieval stays in the speaker's scope"; design D10)."""

from __future__ import annotations

from horizon.ai.contexts import (
    CharacterView,
    KnowledgeHit,
    LineHint,
    MemoryHit,
    ParticipantView,
    SessionContext,
    TurnContext,
    WorldView,
)
from tests.conftest import Api
from tests.knowledge.kit import RecordingEngine, owners
from tests.sessions.kit import chars, command, create, messages

MERIDIAN = "wld_seedMeridian"
AMARA = "chr_seedAmara"
TRIO = ["chr_seedAmara", "chr_seedVictor", "chr_seedMei"]


def test_context_with_hits_round_trips_through_json() -> None:
    s = SessionContext(session_id="ses_x1", world=WorldView(id=MERIDIAN, name="Meridian Council"), mode="one_on_one",
                       title="Chat", participants=[ParticipantView(character_id=AMARA, name="Amara Okafor", role="speaker",
                                                                   energy={"current": 500, "max": 1000})],
                       recent=[], history_tokens=12)
    ctx = TurnContext(session=s, speaker=CharacterView(id=AMARA, name="Amara Okafor", profile={"name": "Amara"}),
                      message_id="msg_x1", prompt="burnout?", line=LineHint(kind="chat"), turn_index=1,
                      knowledge=[KnowledgeHit(chunk_id="kch_1", source_id="kno_1", title="Review", type="pdf",
                                              locator="p. 3", text="Burnout rose.", section_text="Burnout rose. More.",
                                              score=0.9)],
                      memory=[MemoryHit(id="mem_1", kind="fact", text="Amara runs at dawn.", source_session_id=None,
                                        score=0.95)],
                      query="burnout?")
    again = TurnContext.model_validate_json(ctx.model_dump_json())
    assert again == ctx and again.knowledge[0].locator == "p. 3" and again.memory[0].kind == "fact"


async def test_retrieved_hits_are_in_the_context(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    eng = RecordingEngine(api)
    api.rt.ai.override("turn", eng)
    await command(api, sid, "send", {"text": "What does the review say about burnout?"})
    await api.drive(8000)
    assert chars(await messages(api, sid))[-1]["content"] == "Noted."
    [ctx] = eng.seen
    assert ctx.query == "What does the review say about burnout?"
    assert ctx.knowledge and any("burnout" in h.text.lower() for h in ctx.knowledge) and len(ctx.knowledge) <= 5
    assert ctx.memory and len(ctx.memory) <= 3
    assert await owners(api, [h.source_id for h in ctx.knowledge], "knowledge_sources") == {(MERIDIAN, AMARA)}
    assert await owners(api, [m.id for m in ctx.memory], "memory_items") == {(MERIDIAN, AMARA)}


async def test_each_speaker_sees_only_their_own_scope(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "group", TRIO))["session"]["id"]
    eng = RecordingEngine(api)
    api.rt.ai.override("turn", eng)
    await command(api, sid, "set-responder-policy", {"policy": "everyone"})
    await command(api, sid, "send", {"text": "Tell me about burnout, the review, sleep and your work."})
    await api.drive(40000)
    speakers = {c.speaker.id for c in eng.seen}
    assert speakers == set(TRIO)
    for ctx in eng.seen:
        assert ctx.session.world.id == MERIDIAN
        mine = {(MERIDIAN, ctx.speaker.id)}
        assert await owners(api, [h.source_id for h in ctx.knowledge], "knowledge_sources") <= mine
        assert await owners(api, [m.id for m in ctx.memory], "memory_items") <= mine
    assert any(c.knowledge for c in eng.seen) and any(c.memory for c in eng.seen)


async def test_debate_turn_with_no_prompt_retrieves_from_the_motion(api: Api) -> None:
    await api.set_key()
    eng = RecordingEngine(api)
    api.rt.ai.override("turn", eng)
    config = {"motion": "Burnout reviews should be published", "format": "two_sided",
              "sides": {"prop": ["chr_seedAmara"], "opp": ["chr_seedVictor"]}, "roundsPreset": "quick",
              "phases": ["opening", "closing"], "turnLength": "short", "moderator": "user", "verdictBy": "arbiter",
              "rubric": [], "autoAdvance": True, "pauseMs": 1500}
    await create(api, "debate", ["chr_seedAmara", "chr_seedVictor"], config=config)
    await api.drive(20000)
    assert eng.seen
    first = eng.seen[0]
    assert first.query and first.speaker.id in ("chr_seedAmara", "chr_seedVictor")
    if not first.prompt.strip():
        assert first.query == "Burnout reviews should be published" or first.session.recent
    assert await owners(api, [h.source_id for h in first.knowledge], "knowledge_sources") <= {(MERIDIAN, first.speaker.id)}
