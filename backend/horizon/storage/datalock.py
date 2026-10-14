"""The data directory's server lock (rag design D5; local-backend "Space build while serving").

A running backend holds an OS lock on `data/server.lock` from start to stop, so an offline command that must not run
beside it (`horizon space build`) can tell. The lock is advisory: a backend that can't take it (another one already
holds it) logs a warning and carries on, as before. The OS releases it when the process dies, so a crash leaves no
stale lock behind.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import IO

NAME = "server.lock"


def _try_lock(f: IO[bytes]) -> bool:
    try:
        if sys.platform == "win32":
            import msvcrt

            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(f: IO[bytes]) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt

            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


class DataLock:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / NAME
        self._f: IO[bytes] | None = None

    def acquire(self) -> bool:
        """Take the lock; False when another process holds it (nothing is kept open then)."""
        if self._f is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        f = open(self.path, "a+b")  # held open until release()
        if not _try_lock(f):
            f.close()
            return False
        self._f = f
        return True

    def release(self) -> None:
        if self._f is not None:
            _unlock(self._f)
            self._f.close()
            self._f = None


def held_elsewhere(data_dir: Path) -> bool:
    """Whether another process (a running backend) holds `data_dir`'s lock."""
    if not (data_dir / NAME).exists():
        return False
    probe = DataLock(data_dir)
    if probe.acquire():
        probe.release()
        return False
    return True
