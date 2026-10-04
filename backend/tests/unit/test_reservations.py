"""Reservation book (task 6.1, budget-caps "Calls in flight are reserved")."""

from __future__ import annotations

import pytest

from horizon.domain.budget import exceeds_daily
from horizon.gateway.reservations import ReservationBook


def test_two_in_flight_block_a_third() -> None:
    book = ReservationBook()
    spent, cap = 0.30, 1.00
    holds = []
    for _ in range(2):
        assert not exceeds_daily(spent, book.total(), 0.30, cap)
        holds.append(book.reserve(0.30))
    assert exceeds_daily(spent, book.total(), 0.30, cap)
    book.release(holds[0])
    assert not exceeds_daily(spent, book.total(), 0.30, cap)


def test_release_is_idempotent_and_none_safe() -> None:
    book = ReservationBook()
    h = book.reserve(0.1)
    book.release(h)
    book.release(h)
    book.release(None)
    assert book.total() == 0


def test_job_wide_reservation() -> None:
    book = ReservationBook()
    book.reserve_job("job_1", 0.09, character_id="chr_1", creation=True)
    for _ in range(2):
        moved = book.take_from_job("job_1", 0.018)
        book.release(book.reserve(moved, character_id="chr_1", creation=True))  # the step runs and settles
    assert book.job_remaining("job_1") == pytest.approx(3 * 0.018)
    assert book.reserved_for("chr_1") == pytest.approx(0.054)
    book.release_job("job_1")
    assert book.total() == 0


def test_creation_holds_are_per_character() -> None:
    book = ReservationBook()
    book.reserve(0.2, character_id="chr_a", creation=True)
    book.reserve(0.5, character_id="chr_a", creation=False)
    book.reserve(0.3, character_id="chr_b", creation=True)
    assert book.reserved_for("chr_a") == pytest.approx(0.2)
    assert book.total() == pytest.approx(1.0)
