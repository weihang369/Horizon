"""Atomic file writes (doc 02 §2, generation-jobs design D7): `*.tmp` in the same folder → fsync → `os.replace`.

A reader never sees a partial file. A crash between the write and the replace leaves only the `.tmp`, which the
startup sweeper removes. On Windows a reader (an antivirus scan, a file being served) can hold the target open for a
moment, so the replace retries briefly on `PermissionError`.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

REPLACE_ATTEMPTS = 6
REPLACE_DELAY_S = 0.05


def tmp_path(path: Path) -> Path:
    """A unique temp name next to `path` (two writers never share one); the `.tmp` suffix is what the sweeper removes."""
    return path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tmp_path(path)
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    replace(tmp, path)


def replace(tmp: Path, path: Path) -> None:
    for i in range(REPLACE_ATTEMPTS):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(REPLACE_DELAY_S * (i + 1))


def copy_atomic(src: Path, dst: Path) -> None:
    write_atomic(dst, src.read_bytes())
