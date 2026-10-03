"""IDs: `prefix_ULID` (doc 02 §1). A ULID is 26 Crockford base32 characters, which fits the contract's
`^<prefix>_[0-9A-Za-z]{1,40}$`. Seed IDs stay readable (e.g. `chr_seedHana`)."""

from __future__ import annotations

import re

from ulid import ULID

PREFIXES = frozenset({
    "wld", "chr", "emo", "cand", "song", "trk", "pal", "ses", "msg", "evt", "var", "job", "task", "use", "mem",
    "kno", "kch", "ksec", "cmd",
})


def new_id(prefix: str) -> str:
    if prefix not in PREFIXES:
        raise ValueError(f"unknown id prefix {prefix!r}")
    return f"{prefix}_{ULID()}"


def id_pattern(prefix: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(prefix)}_[0-9A-Za-z]{{1,40}}$")


def has_prefix(value: str, prefix: str) -> bool:
    return bool(id_pattern(prefix).match(value))
