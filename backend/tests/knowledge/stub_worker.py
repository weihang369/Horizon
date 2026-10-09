"""A stand-in for `horizon.ai.docling_worker` (no Docling needed): `python stub_worker.py MODE SRC OUT PIDFILE`.

Modes: `ok` (two pages with markers), `sleep` (hangs), `crash` (exits 1 with no result), `page_limit`, `garbage`.
It writes its own PID to PIDFILE first, so a test can check the process is gone afterwards.
"""

import json
import os
import sys
import time

mode, src, out, pidfile = sys.argv[1:5]
with open(pidfile, "w", encoding="utf-8") as f:
    f.write(str(os.getpid()))
if mode == "ok":
    with open(out, "w", encoding="utf-8") as f:
        f.write("<!-- page 1 -->\nIntro line.\n\n<!-- page 2 -->\nTriage starts at the door.\n")
    print(json.dumps({"ok": True, "pages": 2}))
elif mode == "sleep":
    time.sleep(120)
elif mode == "crash":
    sys.exit(1)
elif mode == "page_limit":
    print(json.dumps({"ok": False, "reason": "page_limit", "error": "This document has 412 pages; the limit is 300."}))
    sys.exit(2)
else:
    print("not json at all")
