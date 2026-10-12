"""The history window cut by tokens (conversation-context "History windows per mode", "The window is cut after the
reply"; docs/ai/05 X2, X3; persona-context D8, D10; tasks 4.2–4.3)."""

from __future__ import annotations

from horizon.ai.contexts import MessageView
from horizon.ai.naive.window import ceiling, plan_window, summary_lines
from horizon.domain.pricing import count_tokens


def mv(seq: int, content: str, author: str = "user", name: str = "user") -> MessageView:
    return MessageView(id=f"m{seq}", seq=seq, author_type=author, name=name, kind="chat", content=content,
                       character_id="chr_a" if author == "character" else None)


def hundred(seq: int) -> MessageView:
    return mv(seq, "x" * 300)   # 300 bytes = 100 tokens


def test_under_the_size_nothing_drops() -> None:
    p = plan_window([hundred(i) for i in range(1, 11)], 0, 1000)
    assert p.upto_seq is None and len(p.window) == 10


def test_a_drop_keeps_the_newest_half_by_tokens() -> None:
    msgs = [hundred(i) for i in range(1, 62)]            # 6,100 tokens against 6,000
    p = plan_window(msgs, 0, 6000)
    assert sum(count_tokens(m.content) for m in p.window) <= 3000 and len(p.window) == 30
    assert p.upto_seq == 31 and [m.seq for m in p.dropped] == list(range(1, 32))


def test_after_the_boundary_only() -> None:
    p = plan_window([hundred(i) for i in range(1, 62)], 50, 6000)
    assert p.upto_seq is None and [m.seq for m in p.window] == list(range(51, 62))


def test_one_huge_message_settles_in_one_step() -> None:
    msgs = [hundred(1), mv(2, "y" * 60000), hundred(3), hundred(4)]   # message 2 alone is 20,000 tokens
    p = plan_window(msgs, 0, 6000)
    assert [m.seq for m in p.window] == [3, 4] and p.upto_seq == 2       # at least the newest two stay


def test_ceiling_keeps_the_newest_within_twice_the_window() -> None:
    msgs = [hundred(i) for i in range(1, 151)]           # 15,000 tokens
    shown = ceiling(msgs, 12000)
    assert len(shown) == 120 and shown[-1].seq == 150 and sum(count_tokens(m.content) for m in shown) <= 12000
    assert [m.seq for m in ceiling([mv(1, "z" * 90000), mv(2, "z" * 90000)], 100)] == [1, 2]


def test_summary_lines_split_bubbles_and_name_the_user() -> None:
    out = summary_lines([mv(1, "hi"), mv(2, "Morning!\nCoffee?", "character", "Hana Morisaki"),
                         MessageView(id="n", seq=3, author_type="system", name="system", kind="system_note",
                                     content="Rin joined")], "Kai")
    assert out == ["Kai: hi", "Hana Morisaki: Morning!", "Hana Morisaki: Coffee?", "[system note] Rin joined"]
