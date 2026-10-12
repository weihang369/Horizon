"""`naive-3` over the in-process fake (llm-parameters "Length target in the prompt, cap as a safety net", "Stop
sequences keep the speaker to their own lines", "A history never ends on the speaker's own line without a cue", "An
empty reply is retried once before anything shows"; session-runtime "The reply cap is chosen after the plan";
ai-foundation design D14–D17; tasks 3.3–3.5, 3.7)."""

from __future__ import annotations

from typing import Any

from horizon.ai.contexts import CharacterView, LineHint, MessageView, ParticipantView, SessionContext, TurnContext, WorldView
from horizon.ai.naive.prompt import TRAILING_CUE, length_line, system_prompt
from horizon.ai.naive.turn import NaiveTurnEngine, stop_sequences
from horizon.ai.naive.window import render_history
from tests.conftest import Api
from tests.sessions.kit import API, chars, command, create, events, ledger, messages
from tests.sessions.test_naive import _naive, chat_bodies, sse

HANA, RIN, MEI = "chr_seedHana", "chr_seedRin", "chr_seedMei"


def group_ctx(last_is_speaker: bool = False, mode: str = "group", **cfg: Any) -> TurnContext:
    recent = [MessageView(id="msg_u1", seq=1, author_type="user", name="Kai", kind="chat", content="Dinner?"),
              MessageView(id="msg_c1", seq=2, author_type="character", character_id=HANA, name="Hana", kind="chat",
                          content="Ramen!"),
              MessageView(id="msg_h1", seq=3, author_type="host", name="Host", kind="narration", content="Round two.")]
    if last_is_speaker:
        recent.append(MessageView(id="msg_c2", seq=4, author_type="character", character_id=MEI, name="Mei",
                                  kind="chat", content="I'm in."))
    s = SessionContext(session_id="ses_g", world=WorldView(id="wld_seedSunnyHollow", name="Sunny Hollow",
                                                           you={"displayName": "Kai"}),
                       mode=mode, title="Group", config=cfg or None,
                       participants=[ParticipantView(character_id=c, name=n, role="speaker", energy={"current": 500, "max": 1000})
                                     for c, n in ((MEI, "Mei"), (HANA, "Hana"), (RIN, "Rin"))],
                       recent=recent)
    return TurnContext(session=s, speaker=CharacterView(id=MEI, name="Mei", profile={"name": "Mei"}), message_id="msg_x",
                       line=LineHint(kind="chat"), max_tokens=150)


def engine(api: Api) -> NaiveTurnEngine:
    eng: NaiveTurnEngine = api.rt.ai._build("turn", "naive")
    return eng


# ── 3.4: the length line ──
def test_length_lines_per_mode() -> None:
    assert length_line("one_on_one") == "Write 1–3 short messages, each on its own line, about 70 words in all."
    assert length_line("group") == "Write 1–2 short messages, each on its own line, about 50 words in all."
    assert length_line("watch") == "Write 1–2 short lines, each on its own line, about 50 words in all."
    assert [length_line("debate", x) for x in ("short", "medium", "long")] == [
        f"Write one paragraph, no line breaks, about {n} words." for n in (80, 140, 220)]
    p = system_prompt(group_ctx())
    assert p.endswith("Write 1–2 short messages, each on its own line, about 50 words in all.")
    assert "briefly" not in p and "in plain text" in p


# ── 3.5: stop sequences ──
async def test_group_stop_list(api: Api) -> None:
    req, _ = engine(api).request(group_ctx())
    assert req.stop == ["\nHana:", "\nRin:", "\nKai:", "\n[narration]"]
    assert "\nMei:" not in (req.stop or []) and "\n[" not in (req.stop or [])
    assert req.temperature == 1.0 and req.reasoning == {"enabled": False} and req.max_tokens == 150


async def test_debate_uses_the_debate_row(api: Api) -> None:
    req, _ = engine(api).request(group_ctx(mode="debate", turnLength="short"))
    assert req.temperature == 1.0
    assert "about 80 words" in req.messages[0]["content"]


# ── 3.7: the trailing cue ──
async def test_trailing_cue_when_the_speaker_spoke_last(api: Api) -> None:
    req, _ = engine(api).request(group_ctx(last_is_speaker=True))
    assert req.messages[-1] == {"role": "system", "content": TRAILING_CUE}
    req2, _ = engine(api).request(group_ctx())
    assert req2.messages[-1]["content"] != TRAILING_CUE


# ── 3.7: an empty reply is retried once before anything shows ──
async def test_empty_then_reply(api: Api) -> None:
    assert api.rt.fake is not None
    api.rt.fake.queued.extend([sse([], gid="gen-empty-1"), sse(["<e:happy>", "Hi"], gid="gen-ok-2")])
    sid = await _naive(api)
    (m,) = chars(await messages(api, sid))
    assert m["content"] == "Hi" and m["emotion"] == "happy" and m["status"] == "complete"
    assert len([r for r in await ledger(api) if r["message_id"] == m["id"] and r["purpose"] == "reply"]) == 2
    emotions = [e for e in await events(api, sid) if e["type"] == "emotion" and e["payload"].get("messageId") == m["id"]]
    assert len(emotions) == 1                        # the face is emitted once, never flipped
    bodies = chat_bodies(api)
    assert bodies[-1]["messages"][-1]["content"] in (TRAILING_CUE, bodies[-2]["messages"][-1]["content"])


async def test_empty_twice_is_a_retryable_error_and_no_message(api: Api) -> None:
    assert api.rt.fake is not None
    api.rt.fake.queued.extend([sse([], gid="gen-empty-1"), sse([], gid="gen-empty-2")])
    sid = await _naive(api)
    assert chars(await messages(api, sid)) == []
    errors = [e for e in await events(api, sid) if e["type"] == "error"]
    assert errors and errors[-1]["payload"]["code"] == "provider_error" and errors[-1]["payload"]["retryable"]
    assert len([r for r in await ledger(api) if r["purpose"] == "reply"]) == 2


async def test_own_name_is_stripped_on_a_live_reply(api: Api) -> None:
    assert api.rt.fake is not None
    api.rt.fake.queued.append(sse(["Amara: <e:happy>", "Hello there."]))
    sid = await _naive(api)
    (m,) = chars(await messages(api, sid))
    assert m["content"] == "Hello there." and m["emotion"] == "happy"



def test_five_cast_stop_list_exact() -> None:
    """D16: everyone but the speaker, then the user, deduplicated, never a bare "\n[" (a citation can start a line)."""
    cast = [("chr_a", "Ana"), ("chr_b", "Ben"), ("chr_c", "Cy"), ("chr_d", "Dee"), ("chr_e", "Eli")]
    s = SessionContext(session_id="ses_5", world=WorldView(id="w", name="W", you={"displayName": "Kai"}), mode="group",
                       title="Five", participants=[ParticipantView(character_id=c, name=n, role="speaker",
                                                                   energy={"current": 1, "max": 1}) for c, n in cast],
                       recent=[MessageView(id="m1", seq=1, author_type="user", name="Kai", kind="chat", content="[1] hi")])
    c = TurnContext(session=s, speaker=CharacterView(id="chr_c", name="Cy", profile={"name": "Cy"}), message_id="m",
                    line=LineHint(kind="chat"), max_tokens=150)
    assert stop_sequences(c, "Kai", render_history(s.recent, "chr_c", "Kai")) == [
        "\nAna:", "\nBen:", "\nDee:", "\nEli:", "\nKai:"]


def test_host_line_kinds_become_stops() -> None:
    c = group_ctx()
    c.session.recent.append(MessageView(id="msg_h2", seq=5, author_type="host", name="Host", kind="direction",
                                        content="Wrap it up."))
    c.session.recent.append(MessageView(id="msg_s1", seq=6, author_type="system", name="System", kind="system_note",
                                        content="Rin joined."))
    stops = stop_sequences(c, "Kai", render_history(c.session.recent, MEI, "Kai"))
    assert stops[-3:] == ["\n[narration]", "\n[direction]", "\n[system note]"] and "\n[" not in stops


# ── 3.3: the cap is chosen after the plan, per mode, on the live path ──
async def _profile_naive(api: Api) -> None:
    await api.set_key()
    r = await api.post(f"{API}/_test/ai-profile", {"profile": "scripted", "overrides": {"turn": "naive"}})
    assert r.status_code == 204


async def test_group_reply_cap_is_150(api: Api) -> None:
    await _profile_naive(api)
    sid = (await create(api, "group", ["chr_seedAmara", "chr_seedVictor", "chr_seedMei"]))["session"]["id"]
    await command(api, sid, "everyone-answer")
    await api.drive(40000)
    caps = {b["max_tokens"] for b in chat_bodies(api) if b.get("stream")}
    assert caps == {150}


async def test_prefetched_short_debate_opening_cap_is_200(api: Api) -> None:
    await _profile_naive(api)
    await create(api, "debate", ["chr_seedAmara", "chr_seedVictor"], config={
        "motion": "This house would tax sugary drinks", "format": "two_sided",
        "sides": {"prop": ["chr_seedAmara"], "opp": ["chr_seedVictor"]}, "roundsPreset": "quick",
        "phases": ["opening", "closing"], "turnLength": "short", "moderator": "user", "verdictBy": "arbiter",
        "rubric": [], "autoAdvance": True, "pauseMs": 1500})
    await api.drive(20000)
    replies = [b for b in chat_bodies(api) if b.get("stream")]
    assert len(replies) >= 2                         # Amara's opening and Victor's prefetched one
    assert {b["max_tokens"] for b in replies} == {200} and all(b["temperature"] == 1.0 for b in replies)
