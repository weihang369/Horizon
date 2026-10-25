"""`horizon demo export`: copy real demo content from a running Horizon into the seed (v1 endgame).

The seed's portraits, themes, sessions, knowledge and memories were placeholders or hand-written screenplays. The real
demo is made in the app itself (every reply, image and song through the normal paid paths), then exported from the
app's public API, so this works against any running backend: the user's own (`--from`, default port 8000) after they
regenerate a portrait they dislike, or a separate demo instance.

Two outputs, both re-runnable:
- **Assets** (`--assets`): for every seed and mock character the source app knows, its active raster portraits
  (each emotion, the blink frame, and a second candidate where the fixture shows one) → `seed/assets/portraits/<id>/
  <variant>.webp`, and its Lyria theme → `seed/assets/themes/<id>.mp3`. Song metadata and image provenance go to
  `frontend/scripts/seed-build/recorded/`. A placeholder (SVG or procedural) in the source is skipped, so the seed
  keeps whatever it already has for that variant.
- **Recordings** (`--session SRC=SEED …`, `--knowledge`, `--memory`): the raw wire data of chosen sessions, the seed
  characters' knowledge sources with their chunks, and the memories those sessions produced → `recorded/*.json`. The
  seed build renames ids and shifts times (it owns the fixture keys); nothing is rewritten here.

After exporting, `npm run seed:build` (in `frontend/`) regenerates `seed/`.
"""

from __future__ import annotations

import io
import json
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from horizon.cli import LOOPBACK_HOSTS

REPO = Path(__file__).resolve().parents[2]
SEED = REPO / "seed"
RECORDED = REPO / "frontend" / "scripts" / "seed-build" / "recorded"
RASTER = (".webp", ".png", ".jpg", ".jpeg")
DEFAULT_FROM = "http://127.0.0.1:8000"

Wire = dict[str, Any]


class Source:
    """The running app's public API (read-only use)."""

    def __init__(self, base: str, client: httpx.Client | None = None) -> None:
        if client is None and httpx.URL(base).host not in LOOPBACK_HOSTS:
            raise SystemExit(f"horizon demo export: --from must be a local Horizon (loopback), not {base!r}")
        self.base = base.rstrip("/")
        self.http = client or httpx.Client(timeout=60)

    def get(self, path: str, **params: Any) -> Any:
        r = self.http.get(f"{self.base}/api/v1{path}", params=params or None)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def file(self, url: str) -> bytes:
        r = self.http.get(url if url.startswith("http") else f"{self.base}{url}")
        r.raise_for_status()
        return r.content

    def pages(self, path: str) -> list[Wire]:
        out: list[Wire] = []
        cursor: str | None = None
        while True:
            page = self.get(path, **({"cursor": cursor} if cursor else {}), limit=200)
            out += page["items"]
            cursor = page.get("nextCursor")
            if not cursor:
                return out


def seed_characters() -> dict[str, Wire]:
    """Every fixture character (shipped and `_mock`), by id."""
    out: dict[str, Wire] = {}
    for d in (SEED / "characters", SEED / "_mock" / "characters"):
        for p in sorted(d.glob("*.json")):
            c = json.loads(p.read_text(encoding="utf-8"))["data"]
            out[c["id"]] = c
    return out


def as_webp(data: bytes) -> bytes:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return data
    buf = io.BytesIO()
    Image.open(io.BytesIO(data)).save(buf, "WEBP", quality=90, method=6)
    return buf.getvalue()


def _write(path: Path, data: bytes) -> bool:
    if path.is_file() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def export_assets(src: Source, *, only: Iterable[str] | None = None, log: Any = print) -> int:
    """Copy each character's active raster portraits and Lyria theme. Returns the number of files written."""
    fixtures = seed_characters()
    wanted = set(only) if only else set(fixtures)
    songs: dict[str, Wire] = _read_json(RECORDED / "songs.json", {})
    images: dict[str, Wire] = _read_json(RECORDED / "images.json", {})
    written = 0
    for cid in sorted(wanted):
        fixture = fixtures.get(cid)
        live = src.get(f"/characters/{cid}")
        if fixture is None or live is None:
            log(f"skip {cid}: not in the {'seed' if fixture is None else 'source app'}")
            continue
        variants: dict[str, str] = {}
        for emo, ref in (live.get("emotions") or {}).items():
            if ref and fixture["emotions"].get(emo) and str(ref.get("url", "")).lower().endswith(RASTER):
                variants[emo] = ref["url"]
        blink = live.get("blink") or {}
        if fixture.get("blink") and str(blink.get("url", "")).lower().endswith(RASTER):
            variants["blink"] = blink["url"]
        if len(fixture["appearance"].get("candidates") or []) > 1:
            others = [c for c in live["appearance"].get("candidates") or []
                      if not c.get("selected") and c.get("status") == "ready" and str(c.get("url", "")).lower().endswith(RASTER)]
            if others:
                variants["cand-2"] = others[0]["url"]
        for variant, url in sorted(variants.items()):
            if _write(SEED / "assets" / "portraits" / cid / f"{variant}.webp", as_webp(src.file(url))):
                written += 1
                log(f"portrait {cid}/{variant}")
        if variants:
            images[cid] = {"variants": sorted(variants), "model": _image_model(src), "appearance": live["appearance"]["attributes"],
                           "summary": live["appearance"].get("appearanceSummary", ""), "exportedAt": _today()}
        song = src.get(f"/characters/{cid}/song") if fixture.get("themeSongId") else None
        if song and str(song.get("url", "")).lower().endswith(".mp3"):
            if _write(SEED / "assets" / "themes" / f"{cid}.mp3", src.file(song["url"])):
                written += 1
                log(f"theme {cid}")
            songs[cid] = {k: song[k] for k in ("durationSec", "bytes", "format", "generation", "licenseNote") if k in song}
            songs[cid]["exportedAt"] = _today()
    _write_json(RECORDED / "songs.json", dict(sorted(songs.items())))
    _write_json(RECORDED / "images.json", dict(sorted(images.items())))
    return written


def _image_model(src: Source) -> str:
    settings = src.get("/settings") or {}
    return str((settings.get("models") or {}).get("image", "unknown"))


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def export_session(src: Source, source_id: str, seed_id: str, *, log: Any = print) -> None:
    snap = src.get(f"/sessions/{source_id}")
    if snap is None:
        raise SystemExit(f"horizon demo export: no session {source_id} in {src.base}")
    events = src.pages(f"/sessions/{source_id}/events")
    _write_json(RECORDED / "sessions" / f"{seed_id}.json",
                {"source": source_id, "exportedAt": _today(), "session": snap["session"], "events": events,
                 "messages": snap["messages"]})
    log(f"session {source_id} → {seed_id}: {len(events)} events, {len(snap['messages'])} messages")


def export_knowledge(src: Source, character_ids: Iterable[str], *, log: Any = print) -> None:
    out: list[Wire] = []
    for cid in sorted(character_ids):
        for k in src.get(f"/characters/{cid}/knowledge") or []:
            if k.get("status") not in ("indexed", "failed") or str(k["id"]).startswith("kno_seed"):
                continue
            detail = src.get(f"/knowledge/{k['id']}")
            out.append({"source": detail["source"], "chunks": detail["chunks"]})
    _write_json(RECORDED / "knowledge.json", out)
    log(f"knowledge: {len(out)} sources, {sum(len(x['chunks']) for x in out)} chunks")


def export_memory(src: Source, character_ids: Iterable[str], session_ids: Iterable[str], *, log: Any = print) -> None:
    keep = set(session_ids)
    out: list[Wire] = []
    for cid in sorted(character_ids):
        items = src.get(f"/characters/{cid}/memory") or []
        items = items if isinstance(items, list) else items.get("items", [])
        out += [m for m in items if m.get("sourceSessionId") in keep]
    _write_json(RECORDED / "memory.json", sorted(out, key=lambda m: (m["characterId"], m["createdAt"], m["id"])))
    log(f"memory: {len(out)} items")


def export_rows(db_path: Path, session_ids: Iterable[str], *, log: Any = print) -> None:
    """D-110: what a real run writes that the public API doesn't show, read straight from the recording database
    (read-only): the seed characters' knowledge as stored (sources, sections, pieces, their vectors and original files),
    the recorded sessions' memories with their vectors, recall's line index, the stored query rewrites and safety
    answers, the ledger, and each character's energy. The seed build renames ids and moves times as for sessions."""
    import base64
    import shutil
    import sqlite3

    import sqlite_vec

    from horizon.db.spaces import message_vec_table, vec_tables

    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    def rows(q: str, *a: Any) -> list[dict[str, Any]]:
        return [dict(r) for r in db.execute(q, a).fetchall()]

    space = rows("SELECT id, dims FROM embedding_spaces WHERE status = 'active'")[0]
    mem_vec, kno_vec = vec_tables(space["id"])
    msg_vec = message_vec_table(space["id"])

    def vectors(table: str, rids: list[int]) -> dict[int, str]:
        if not rids:
            return {}
        got = db.execute(f"SELECT rid, embedding FROM {table} WHERE rid IN ({','.join('?' * len(rids))})", rids)
        return {int(r[0]): base64.b64encode(bytes(r[1])).decode() for r in got}

    def strip(r: dict[str, Any], vec: dict[int, str]) -> dict[str, Any]:
        rid = r.pop("rid")
        r.pop("is_seed", None)
        if rid in vec:
            r["vector"] = vec[rid]
        return r

    shipped = [cid for cid, c in seed_characters().items() if c.get("isSeed")]
    sids = list(session_ids)
    marks = ",".join("?" * len(sids))
    files_dir = RECORDED / "knowledge-files"
    shutil.rmtree(files_dir, ignore_errors=True)
    knowledge: list[Wire] = []
    data_dir = db_path.parent
    for src in rows(f"SELECT * FROM knowledge_sources WHERE is_seed = 0 AND character_id IN ({','.join('?' * len(shipped))}) "
                    "ORDER BY added_at", *shipped):
        src.pop("is_seed", None)
        chunks = rows("SELECT * FROM knowledge_chunks WHERE source_id = ? ORDER BY idx", src["id"])
        vec = vectors(kno_vec, [c["rid"] for c in chunks])
        folder = data_dir / "knowledge" / src["world_id"] / src["character_id"] / src["id"]
        files = []
        if folder.is_dir():
            for f in sorted(folder.iterdir()):
                if f.is_file():
                    (files_dir / src["id"]).mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, files_dir / src["id"] / f.name)
                    files.append(f.name)
        if not files and src["status"] == "indexed":   # rows read from a copied database: its files stayed behind
            log(f"WARNING: no original file for {src['id']} under {folder} (pass the live data/horizon.db)")
        knowledge.append({"source": src, "files": files,
                          "sections": rows("SELECT * FROM knowledge_sections WHERE source_id = ? ORDER BY idx", src["id"]),
                          "chunks": [strip(c, vec) for c in chunks]})
    memory = rows(f"SELECT * FROM memory_items WHERE source_session_id IN ({marks}) ORDER BY character_id, created_at, id",
                  *sids)
    mvec = vectors(mem_vec, [m["rid"] for m in memory])
    index = rows(f"SELECT * FROM message_index WHERE session_id IN ({marks}) ORDER BY session_id, seq", *sids)
    ivec = vectors(msg_vec, [m["rid"] for m in index])
    out = {
        "space": space,
        "knowledge": knowledge,
        "memory": [strip(m, mvec) for m in memory],
        "messageIndex": [strip(m, ivec) for m in index],
        "aiMeta": rows(f"SELECT a.* FROM message_ai_meta a JOIN messages m ON m.id = a.message_id "
                       f"WHERE m.session_id IN ({marks}) ORDER BY a.message_id", *sids),
        "usage": [{k: v for k, v in u.items() if k != "is_seed"}
                  for u in rows("SELECT * FROM usage_records ORDER BY at, id")],
        "energy": {r["id"]: {k: r[k] for k in ("energy_current", "energy_as_of", "energy_spent_today")}
                   for r in rows("SELECT * FROM characters WHERE is_seed = 1 ORDER BY id")},
    }
    db.close()
    _write_json(RECORDED / "rows.json", out)
    pieces = [c for k in knowledge for c in k["chunks"]]
    log(f"rows: {len(knowledge)} sources ({len(pieces)} pieces, {sum('vector' in c for c in pieces)} vectors), "
        f"{len(out['memory'])} memories ({len(mvec)} vectors), {len(index)} indexed lines, "
        f"{len(out['aiMeta'])} ai-meta rows, {len(out['usage'])} ledger rows, space {space['id']}")


def run(args: Any) -> int:
    if hasattr(sys.stdout, "reconfigure"):   # a Windows console (cp1252) can't print the progress lines' "→"
        sys.stdout.reconfigure(errors="replace")
    src = Source(args.source)
    if src.get("/health") is None:
        raise SystemExit(f"horizon demo export: no Horizon backend answering at {args.source}")
    did = False
    if args.assets:
        n = export_assets(src, only=args.character or None)
        print(f"horizon demo export: {n} asset file(s) written under seed/assets/")
        did = True
    pairs = [s.split("=", 1) for s in args.session or []]
    for source_id, seed_id in pairs:
        export_session(src, source_id, seed_id)
        did = True
    shipped = [cid for cid, c in seed_characters().items() if c.get("isSeed")]
    if args.knowledge:
        export_knowledge(src, shipped)
        did = True
    if args.memory:
        export_memory(src, seed_characters(), [s for s, _ in pairs] or _recorded_sources())
        did = True
    if args.rows:
        export_rows(Path(args.rows), [s for s, _ in pairs] or _recorded_sources())
        did = True
    if not did:
        raise SystemExit("horizon demo export: nothing to do (pass --assets, --session SRC=SEED, --knowledge, --memory "
                         "or --rows)")
    print("Next: npm run seed:build (in frontend/) to regenerate seed/.")
    return 0


def _recorded_sources() -> list[str]:
    return [json.loads(p.read_text(encoding="utf-8"))["source"] for p in sorted((RECORDED / "sessions").glob("*.json"))]


def register(sub: Any) -> None:
    d = sub.add_parser("demo", help="the real demo content (v1 endgame)")
    dsub = d.add_subparsers(dest="demo_cmd", required=True)
    e = dsub.add_parser("export", help="copy portraits, themes and recordings from a running Horizon into the seed")
    e.add_argument("--from", dest="source", default=DEFAULT_FROM, help=f"the running backend (default {DEFAULT_FROM})")
    e.add_argument("--assets", action="store_true", help="active portraits, blink frames and Lyria themes")
    e.add_argument("--character", action="append", help="limit --assets to these character ids (repeatable)")
    e.add_argument("--session", action="append", metavar="SRC=SEED", help="record a session as a seed session (repeatable)")
    e.add_argument("--knowledge", action="store_true", help="the seed characters' indexed knowledge and chunks")
    e.add_argument("--memory", action="store_true", help="the memories the recorded sessions produced")
    e.add_argument("--rows", metavar="DB", help="the source app's horizon.db (read-only): stored knowledge with vectors "
                   "and originals, memory vectors, line index, ai-meta, ledger, energy (D-110)")
    e.set_defaults(fn=run)
