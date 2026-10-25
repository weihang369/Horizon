"""The reply-rule code checks (evaluation-harness "Reply-rule checks"; docs/ai/04 P8, P12; persona-context D28; task 9.5)."""

from __future__ import annotations

from horizon.evals.reply_checks import Reply, check_replies, ends_with_question, has_action, step_two_rate


def r(text: str, speaker: str = "amara", mode: str = "one_on_one", catch: tuple[str, ...] = ()) -> Reply:
    return Reply(speaker=speaker, mode=mode, text=text, names=("Amara", "Amara Okafor"), catchphrases=catch)


def test_actions_tags_prefixes_bubbles_and_emoji() -> None:
    st = check_replies([r("*smiles* hi"), r("<e:happy>ok"), r("Fine.\nAmara: again"), r("a\nb\nc\nd"),
                        r("ok 😀😀", mode="group"), r("one\ntwo", mode="debate")], free_running=False)
    assert st.flagged["actions"] == [0]
    assert st.flagged["stray_tag_or_prefix"] == [1, 2]
    assert st.flagged["over_bubbles"] == [3, 5]
    assert st.flagged["emoji_over_one"] == [4]
    assert "repeated_opener" not in st.counts          # frozen transcripts: no repetition rates


def test_question_endings() -> None:
    assert ends_with_question("Where is it?") and ends_with_question('He asked "why?"')
    assert ends_with_question("为什么？") and not ends_with_question("It hurts.")
    assert not has_action("2 * 3 * 4") and has_action("*nods slowly*")


def test_repeated_opener_and_catchphrase_on_free_runs() -> None:
    replies = [r("Well, honestly that depends."), r("Well honestly, it is fine.", speaker="hana"),
               r("Well, honestly that is fine."), r("Let's figure out what's actually going on.", catch=("Let's figure out "
                                                                                                    "what's actually going on.",))]
    st = check_replies(replies, free_running=True)
    assert st.flagged["repeated_opener"] == [2]        # same speaker, first three words match an earlier reply
    assert st.flagged["catchphrase"] == [3]
    assert st.rate("catchphrase") == 0.25


def test_step_two_rate() -> None:
    assert step_two_rate([{"step2": True}, {"step2": False}, {}, {"step2": False}]) == 0.25
    assert step_two_rate([]) is None
