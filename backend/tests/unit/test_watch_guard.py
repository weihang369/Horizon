"""The nobody-left-out guard and the steer cap as pure functions over the stored log (group-watch task 6.1; design
D13, D14; doc 07 G6, G7; watch-direction "Nobody is left out")."""

from __future__ import annotations

from typing import Any

from horizon.sessions.watch_plan import guard, scene_start, steered_recently

A, B, C, D = "chr_a", "chr_b", "chr_c", "chr_d"


class Log:
    def __init__(self) -> None:
        self.msgs: list[dict[str, Any]] = []

    def add(self, author: str, kind: str = "chat", cid: str | None = None, trace: dict[str, Any] | None = None) -> Log:
        m: dict[str, Any] = {"seq": len(self.msgs) + 1, "kind": kind, "author": {"type": author}, "content": "x"}
        if cid:
            m["author"]["characterId"] = cid
        if trace:
            m["trace"] = trace
        self.msgs.append(m)
        return self

    def premise(self) -> Log:
        return self.add("system", "direction")

    def says(self, *cids: str) -> Log:
        for c in cids:
            self.add("character", cid=c)
        return self


def test_too_few_lines_never_force() -> None:
    log = Log().premise().says(A, B, A, B, A)                  # 5 < 2n = 6
    assert guard(log.msgs, [A, B, C]) is None


def test_never_spoken_after_two_rounds() -> None:
    log = Log().premise().says(A, B, A, B, A, B)
    assert guard(log.msgs, [A, B, C]) == (C, 6)


def test_lines_before_the_premise_dont_count() -> None:
    log = Log().says(C, C).premise().says(A, B, A, B, A, B)
    assert scene_start(log.msgs) == 3
    assert guard(log.msgs, [A, B, C]) == (C, 6)


def test_spoken_long_ago_counts_lines_since_their_last() -> None:
    log = Log().premise().says(C, A, B, A, B, A, B, A)
    assert guard(log.msgs, [A, B, C]) == (C, 7)


def test_spoke_within_the_last_two_rounds() -> None:
    log = Log().premise().says(A, B, C, A, B, A, B)
    assert guard(log.msgs, [A, B, C]) is None


def test_a_woken_character_is_counted_in_the_round() -> None:
    """D was asleep (not in the round) while A and B talked; awake again, the round is 3 and D qualifies."""
    log = Log().premise().says(D, A, B, A, B, A, B)
    assert guard(log.msgs, [A, B]) is None                     # D asleep: n = 2, both spoke
    assert guard(log.msgs, [A, B, D]) == (D, 6)


def test_step_in_replies_count_and_directors_notes_dont() -> None:
    log = Log().premise().says(A, B)
    log.add("user", "chat")                                    # a Step in line
    log.says(A, B)                                             # its replies are character lines
    log.add("user", "direction")                               # a director's note: not a character line
    log.add("system", "system_note")
    log.says(A, B)
    assert guard(log.msgs, [A, B, C]) == (C, 6)


def test_several_qualify_the_silent_longest_goes() -> None:
    log = Log().premise().says(D, C, A, A, A, A, A, A, A, A)
    assert guard(log.msgs, [A, C, D]) == (D, 9)                # D's last line is older than C's
    log2 = Log().premise().says(A, A, A, A, A, A)
    assert guard(log2.msgs, [A, C, D]) == (C, 6)               # neither spoke: cast order


def test_the_steer_cap_reads_the_last_two_character_traces() -> None:
    steer = {"system1": {"questions": [{"id": "talk_finished", "action": "steer"}]}}
    calm = {"system1": {"questions": [{"id": "talk_finished", "action": "no steer"}]}}
    log = Log().premise()
    log.add("character", cid=A, trace=steer)
    assert steered_recently(log.msgs)
    log.add("user", "direction")
    log.add("character", cid=B, trace=calm)
    assert steered_recently(log.msgs)                          # still one of the last 2 character lines
    log.add("character", cid=C, trace=calm)
    assert not steered_recently(log.msgs)
