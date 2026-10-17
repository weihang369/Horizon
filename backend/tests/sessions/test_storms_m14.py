"""Cancel storms on the paths M14 adds (safety design D2; session-runtime "New cancel paths leave the writer free").

Every new cancel path is stormed while it writes (`storm_during_write`) or cut while it waits on a held call
(`storm_during_call`). Afterwards the writer is free, the clock settles and the log reduces.

Task 0.2 lists each path of D2's table as a strict xfail naming the phase that builds it. Each phase replaces its
placeholder with the real storm, so no path is forgotten.
"""

from __future__ import annotations

import pytest


def _placeholder(phase: int) -> None:
    pytest.fail(f"built in phase {phase}")


@pytest.mark.xfail(strict=True, reason="phase 2: the safety nouls inside a plan request")
async def test_the_nouls_in_a_plan_cut_by_stop_or_a_superseding_send() -> None:
    _placeholder(2)


@pytest.mark.xfail(strict=True, reason="phase 2: the message_ai_meta.safety write")
async def test_the_safety_write_cut_by_a_cancelled_turn_a_delete_or_a_fork() -> None:
    _placeholder(2)


@pytest.mark.xfail(strict=True, reason="phase 3: the output check in flight")
async def test_the_output_check_cut_by_stop_end_cap_pause_leave_delete_and_reset() -> None:
    _placeholder(3)


@pytest.mark.xfail(strict=True, reason="phase 3: a finished prefetch held for its check")
async def test_a_prefetch_held_for_its_check_cut_by_stop_leave_and_cap_pause() -> None:
    _placeholder(3)


@pytest.mark.xfail(strict=True, reason="phase 3: a host line or verdict prose held for its check")
async def test_a_host_line_or_verdict_held_for_its_check_cut_by_extend_skip_and_clear() -> None:
    _placeholder(3)


@pytest.mark.xfail(strict=True, reason="phase 3: the reducer clear")
async def test_the_reducer_clear_survives_a_reconnect_between_error_and_turn_end() -> None:
    _placeholder(3)


@pytest.mark.xfail(strict=True, reason="phase 4: the motion check")
async def test_the_motion_check_cut_by_an_abandoned_request() -> None:
    _placeholder(4)


@pytest.mark.xfail(strict=True, reason="phase 5: the instruction noul fails in a pause run")
async def test_a_failed_instruction_noul_makes_the_piece_a_failed_try() -> None:
    _placeholder(5)


@pytest.mark.xfail(strict=True, reason="phase 6: check_prompt at job start")
async def test_check_prompt_at_job_start_cut_by_a_character_delete() -> None:
    _placeholder(6)


@pytest.mark.xfail(strict=True, reason="phase 6: check_prompt in the song task")
async def test_check_prompt_in_the_song_task_cut_by_cancel_and_deletes() -> None:
    _placeholder(6)
