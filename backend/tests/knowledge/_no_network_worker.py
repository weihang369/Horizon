"""The conversion worker with the network cut off (knowledge-memory-storage task 5.4, document-conversion "offline").

Run as `python tests/knowledge/_no_network_worker.py <worker args>`: every socket connect raises before the real
`horizon.ai.docling_worker` runs, so a conversion that tried to reach the network would fail (and say so on stderr).
"""

from __future__ import annotations

import socket
import sys
from typing import Any


def _refuse(*_a: Any, **_k: Any) -> Any:
    print("network access attempted during conversion", file=sys.stderr, flush=True)
    raise OSError("network access is blocked during conversion")


socket.socket.connect = _refuse  # type: ignore[method-assign]
socket.socket.connect_ex = _refuse  # type: ignore[method-assign]
socket.create_connection = _refuse

if __name__ == "__main__":
    from horizon.ai.docling_worker import main

    sys.exit(main(sys.argv[1:]))
