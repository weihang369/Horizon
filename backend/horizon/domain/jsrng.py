"""A bit-exact port of the MockClient's PRNG (`frontend/src/mock/rng.ts`: FNV-1a seed hash + mulberry32), so ported
banks (the draft bank, generation-jobs design D9) give the same answers as the MockClient for the same seed.

JS string semantics are kept where they matter: the hash walks UTF-16 code units, like `charCodeAt`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")
M32 = 0xFFFFFFFF


def utf16_units(s: str) -> list[int]:
    raw = s.encode("utf-16-le")
    return [raw[i] | (raw[i + 1] << 8) for i in range(0, len(raw), 2)]


def js_slice(s: str, end: int) -> str:
    """`s.slice(0, end)` on UTF-16 code units (a split surrogate pair is dropped rather than kept half)."""
    units = s.encode("utf-16-le")[: end * 2]
    return units.decode("utf-16-le", errors="ignore")


def hash_string(s: str) -> int:
    h = 2166136261
    for u in utf16_units(s):
        h ^= u
        h = (h * 16777619) & M32
    return h


def _imul(a: int, b: int) -> int:
    return ((a & M32) * (b & M32)) & M32


class JsRng:
    def __init__(self, seed: str | int) -> None:
        self._a = (seed & M32) if isinstance(seed, int) else hash_string(seed)

    def next(self) -> float:
        self._a = (self._a + 0x6D2B79F5) & M32
        t = self._a
        t = _imul(t ^ (t >> 15), t | 1)
        t = (t ^ ((t + _imul(t ^ (t >> 7), t | 61)) & M32)) & M32
        return ((t ^ (t >> 14)) & M32) / 4294967296

    def range(self, lo: float, hi: float) -> float:
        return lo + (hi - lo) * self.next()

    def int(self, lo: int, hi_inclusive: int) -> int:
        return math.floor(lo + (hi_inclusive - lo + 1) * self.next())

    def pick(self, arr: Sequence[T]) -> T:
        return arr[math.floor(self.next() * len(arr)) % len(arr)]

    def chance(self, p: float) -> bool:
        return self.next() < p

    def shuffle(self, arr: Sequence[T]) -> list[T]:
        out = list(arr)
        for i in range(len(out) - 1, 0, -1):
            j = math.floor(self.next() * (i + 1))
            out[i], out[j] = out[j], out[i]
        return out
