"""Wire ↔ row mappers (design D1, D5): pure functions between the contract's camelCase shapes and table rows.

Rules:
- A NULL column is *omitted* on the wire, unless the contract makes the field required-and-nullable
  (`Session.config`, `Session.state`, `Character.emotions[*]`, `Character.blink`).
- Derived fields are computed by the caller and passed in (`World.characterCount`, `Character.energy`,
  `Character.emotions`/`blink`/`appearance.basePortraitUrl`/`appearance.candidates`, `KnowledgeSource.citedCount`).
- Timestamps are stored and returned in the millisecond form; seed input is normalised on the way in.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from horizon.domain.timeutil import normalise_iso

Row = Mapping[Any, Any]  # SQLAlchemy RowMapping or a plain dict
Wire = dict[str, Any]

EMOTIONS = ("neutral", "happy", "sad", "angry", "surprised", "thinking", "embarrassed")
ASSETS_PREFIX = "/assets/"


def _ts(v: Any) -> Any:
    return normalise_iso(v) if isinstance(v, str) else v


def _opt(out: Wire, key: str, value: Any) -> None:
    if value is not None:
        out[key] = value


def url_to_rel(url: str | None) -> str | None:
    """`/assets/placeholder/x.svg` → `placeholder/x.svg`. Anything else (data: URLs, absolute URLs) is kept as is."""
    if url is None:
        return None
    return url[len(ASSETS_PREFIX):] if url.startswith(ASSETS_PREFIX) else url


def rel_to_url(rel: str | None) -> str | None:
    if rel is None:
        return None
    if rel.startswith(("data:", "blob:", "http://", "https://", "/")):
        return rel
    return ASSETS_PREFIX + rel


# ── Worlds ───────────────────────────────────────────────────────────────────
def world_row(w: Wire, *, is_seed: bool) -> dict[str, Any]:
    return {
        "id": w["id"], "name": w["name"], "cover": w["cover"], "you": w.get("you"), "is_seed": is_seed,
        "created_at": _ts(w["createdAt"]), "updated_at": _ts(w["updatedAt"]), "last_active_at": _ts(w["lastActiveAt"]),
    }


def world_wire(r: Row, character_count: int) -> Wire:
    out: Wire = {"id": r["id"], "name": r["name"], "cover": r["cover"]}
    _opt(out, "you", r["you"])
    out.update(characterCount=character_count, isSeed=bool(r["is_seed"]), createdAt=r["created_at"],
               updatedAt=r["updated_at"], lastActiveAt=r["last_active_at"])
    return out


# ── Characters + their image assets ─────────────────────────────────────────
def character_rows(c: Wire, *, is_seed: bool, energy_day: Callable[[str], str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A wire Character → its `characters` row + its `image_assets` rows (emotion, blink and candidate seed batch)."""
    appearance = {k: v for k, v in c["appearance"].items() if k not in ("basePortraitUrl", "candidates")}
    e = c["energy"]
    as_of = _ts(e["asOf"])
    row = {
        "id": c["id"], "world_id": c["worldId"], "status": c["status"], "creation_step": c.get("creationStep"),
        "seed_prompt": c["seedPrompt"], "intent": c["intent"], "advisory": c["advisory"], "profile": c["profile"],
        "profile_meta": c.get("profileMeta"), "appearance": appearance, "palette_id": c["paletteId"],
        "emotion_set": c["emotionSet"], "theme_song_id": c.get("themeSongId"), "active_job_id": c.get("activeJobId"),
        "version": c["version"], "energy_max": e["max"], "energy_current": float(e["current"]), "energy_as_of": as_of,
        "energy_spent_today": float(e["spentToday"]), "energy_day": energy_day(as_of), "is_seed": is_seed,
        "created_at": _ts(c["createdAt"]), "updated_at": _ts(c["updatedAt"]), "approved_at": _ts(c.get("approvedAt")),
        "archived_at": _ts(c.get("archivedAt")), "deleted_at": _ts(c.get("deletedAt")),
    }
    created = row["created_at"]
    assets: list[dict[str, Any]] = []

    def asset(ref: Wire, *, kind: str, emotion: str | None, variant: str = "default", **extra: Any) -> dict[str, Any]:
        return {"id": ref.get("assetId") or ref["id"], "world_id": c["worldId"], "character_id": c["id"], "job_id": None,
                "kind": kind, "emotion": emotion, "variant": variant, "status": extra.pop("status", "ready"),
                "rel_path": url_to_rel(ref.get("url")), "width": None, "height": None, "format": None, "bytes": None,
                "vfx_preset": ref.get("vfxPreset", "none"), "generation": None, "version": 1,
                "is_active": extra.pop("is_active", True), "selected": extra.pop("selected", False),
                "ord": extra.pop("ord", 0), "created_at": created}

    for emotion in EMOTIONS:
        ref = c["emotions"].get(emotion)
        if ref:
            assets.append(asset(ref, kind="emotion", emotion=emotion))
    if c.get("blink"):
        assets.append(asset(c["blink"], kind="emotion", emotion="neutral", variant="blink"))
    for i, cand in enumerate(c["appearance"].get("candidates") or []):
        assets.append(asset(cand, kind="candidate", emotion=None, status=cand["status"], is_active=False,
                            selected=bool(cand["selected"]), ord=i))
    return row, assets


def _ref(a: Row) -> Wire:
    return {"assetId": a["id"], "url": rel_to_url(a["rel_path"]) or "", "vfxPreset": a["vfx_preset"]}


def character_wire(r: Row, assets: Iterable[Row], energy: Wire) -> Wire:
    """`assets`: this character's image_assets rows. Active default emotion rows → `emotions`; the active
    neutral blink row → `blink`; candidates from the latest job batch (or the seed batch) → `appearance.candidates`."""
    rows = list(assets)
    emotions: dict[str, Wire | None] = dict.fromkeys(EMOTIONS)
    blink: Wire | None = None
    for a in rows:
        if a["kind"] != "emotion" or not a["is_active"]:
            continue
        if a["variant"] == "blink":
            blink = _ref(a)
        else:
            emotions[a["emotion"]] = _ref(a)
    cands = [a for a in rows if a["kind"] == "candidate"]
    job_ids = sorted({a["job_id"] for a in cands if a["job_id"]})
    latest = max(job_ids, key=lambda j: max(a["created_at"] for a in cands if a["job_id"] == j)) if job_ids else None
    batch = sorted((a for a in cands if a["job_id"] == latest), key=lambda a: (a["ord"], a["id"]))
    appearance = dict(r["appearance"])
    neutral = emotions["neutral"]
    if neutral:
        appearance["basePortraitUrl"] = neutral["url"]
    appearance["candidates"] = [{"id": a["id"], "url": rel_to_url(a["rel_path"]) or "", "selected": bool(a["selected"]),
                                 "status": a["status"]} for a in batch]
    out: Wire = {"id": r["id"], "worldId": r["world_id"], "status": r["status"]}
    _opt(out, "creationStep", r["creation_step"])
    out.update(seedPrompt=r["seed_prompt"], intent=r["intent"], advisory=bool(r["advisory"]), profile=r["profile"])
    _opt(out, "profileMeta", r["profile_meta"])
    out.update(appearance=appearance, paletteId=r["palette_id"], emotionSet=r["emotion_set"], emotions=emotions, blink=blink)
    _opt(out, "themeSongId", r["theme_song_id"])
    out["energy"] = energy
    _opt(out, "activeJobId", r["active_job_id"])
    out.update(version=r["version"], isSeed=bool(r["is_seed"]), createdAt=r["created_at"], updatedAt=r["updated_at"])
    _opt(out, "approvedAt", r["approved_at"])
    _opt(out, "archivedAt", r["archived_at"])
    _opt(out, "deletedAt", r["deleted_at"])
    return out


def stored_energy(r: Row) -> Wire:
    """The stored (REAL) energy as an Energy-shaped dict, before the read-time derivation."""
    return {"max": r["energy_max"], "current": r["energy_current"], "asOf": r["energy_as_of"],
            "regenPerHour": r["energy_max"] / 24, "spentToday": r["energy_spent_today"]}


def emotion_asset_wire(a: Row) -> Wire:
    out: Wire = {"id": a["id"], "characterId": a["character_id"], "emotion": a["emotion"], "variant": a["variant"],
                 "status": a["status"]}
    _opt(out, "url", rel_to_url(a["rel_path"]))
    for col, key in (("width", "width"), ("height", "height"), ("format", "format"), ("bytes", "bytes")):
        _opt(out, key, a[col])
    out["vfxPreset"] = a["vfx_preset"]
    _opt(out, "generation", a["generation"])
    out.update(version=a["version"], isActive=bool(a["is_active"]))
    return out


# ── Theme songs ──────────────────────────────────────────────────────────────
def song_row(s: Wire, *, is_seed: bool, created_at: str) -> dict[str, Any]:
    return {"id": s["id"], "character_id": s["characterId"], "status": s["status"], "rel_path": url_to_rel(s.get("url")),
            "duration_sec": s.get("durationSec"), "format": s.get("format"), "bytes": s.get("bytes"), "loop": s.get("loop"),
            "gain_db": s.get("gainDb"), "brief": s["brief"], "instrumental": s["instrumental"],
            "generation": s.get("generation"), "license_note": s["licenseNote"], "version": 1, "is_seed": is_seed,
            "created_at": created_at}


def song_wire(r: Row) -> Wire:
    out: Wire = {"id": r["id"], "characterId": r["character_id"], "status": r["status"]}
    _opt(out, "url", rel_to_url(r["rel_path"]))
    dur = r["duration_sec"]
    _opt(out, "durationSec", int(dur) if isinstance(dur, float) and dur.is_integer() else dur)
    _opt(out, "format", r["format"])
    _opt(out, "bytes", r["bytes"])
    _opt(out, "loop", r["loop"])
    _opt(out, "gainDb", r["gain_db"])
    out.update(brief=r["brief"], instrumental=bool(r["instrumental"]))
    _opt(out, "generation", r["generation"])
    out["licenseNote"] = r["license_note"]
    return out


# ── Sessions, participants, messages, events ────────────────────────────────
def session_rows(s: Wire, *, is_seed: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    row = {
        "id": s["id"], "world_id": s["worldId"], "title": s["title"], "title_is_custom": s["titleIsCustom"],
        "mode": s["mode"], "status": s["status"], "paused_reason": s.get("pausedReason"), "emotion_mode": s["emotionMode"],
        "music_policy": s["musicPolicy"], "readable_mode": s["readableMode"], "config": s.get("config"),
        "state": s.get("state"), "continued_from": s.get("continuedFrom"), "is_seed": is_seed, "cost_usd": s["costUsd"],
        "message_count": s["messageCount"], "created_at": _ts(s["createdAt"]), "updated_at": _ts(s["updatedAt"]),
        "last_message_at": _ts(s.get("lastMessageAt")),
    }
    parts = [{"session_id": s["id"], "character_id": p["characterId"], "ord": i, "role": p["role"], "side": p.get("side"),
              "current_emotion": p["currentEmotion"], "muted": p["mutedByUser"]} for i, p in enumerate(s["participants"])]
    return row, parts


def participant_wire(p: Row) -> Wire:
    out: Wire = {"characterId": p["character_id"], "role": p["role"]}
    if p["role"] == "debater":
        out["side"] = p["side"]  # a debater always has a side; `null` on a panel (Participant.side?: Side | null)
    else:
        _opt(out, "side", p["side"])
    out.update(currentEmotion=p["current_emotion"], mutedByUser=bool(p["muted"]))
    return out


def session_wire(r: Row, participants: Iterable[Row]) -> Wire:
    out: Wire = {"id": r["id"], "worldId": r["world_id"], "title": r["title"], "titleIsCustom": bool(r["title_is_custom"]),
                 "mode": r["mode"], "status": r["status"]}
    _opt(out, "pausedReason", r["paused_reason"])
    out["participants"] = [participant_wire(p) for p in sorted(participants, key=lambda p: p["ord"])]
    out.update(emotionMode=r["emotion_mode"], musicPolicy=r["music_policy"], readableMode=bool(r["readable_mode"]),
               config=r["config"], state=r["state"])
    _opt(out, "continuedFrom", r["continued_from"])
    out.update(isSeed=bool(r["is_seed"]), costUsd=r["cost_usd"], messageCount=r["message_count"],
               createdAt=r["created_at"], updatedAt=r["updated_at"])
    _opt(out, "lastMessageAt", r["last_message_at"])
    return out


_MSG_OPTIONAL = (
    ("targetCharacterId", "target_character_id"), ("interruptedBy", "interrupted_by"), ("emotion", "emotion"),
    ("emotionSource", "emotion_source"), ("debate", "debate"), ("forcedSpeaker", "forced_speaker"),
    ("reactions", "reactions"), ("variants", "variants"), ("activeVariantId", "active_variant_id"), ("usage", "usage"),
    ("citations", "citations"), ("error", "error"),
)


def message_row(m: Wire) -> dict[str, Any]:
    row: dict[str, Any] = {"id": m["id"], "session_id": m["sessionId"], "seq": m["seq"], "author_type": m["author"]["type"],
                           "author_character_id": m["author"].get("characterId"), "kind": m["kind"], "content": m["content"],
                           "status": m["status"], "created_at": _ts(m["createdAt"])}
    for key, col in _MSG_OPTIONAL:
        row[col] = m.get(key)
    return row


def message_wire(r: Row, trace: Wire | None = None) -> Wire:
    author: Wire = {"type": r["author_type"]}
    _opt(author, "characterId", r["author_character_id"])
    out: Wire = {"id": r["id"], "sessionId": r["session_id"], "seq": r["seq"], "author": author, "kind": r["kind"]}
    _opt(out, "targetCharacterId", r["target_character_id"])
    out.update(content=r["content"], status=r["status"])
    for key, col in _MSG_OPTIONAL[1:]:
        v = r[col]
        _opt(out, key, bool(v) if col == "forced_speaker" and v is not None else v)
    _opt(out, "trace", trace)
    out["createdAt"] = r["created_at"]
    return out


def citation_rows(m: Wire) -> list[dict[str, Any]]:
    return [{"message_id": m["id"], "n": c["n"], "chunk_id": c["chunkId"], "source_id": c["sourceId"]}
            for c in m.get("citations") or []]


def event_message_id(e: Wire) -> str | None:
    p = e.get("payload") or {}
    mid = p.get("messageId")
    if mid is None and isinstance(p.get("message"), dict):
        mid = p["message"].get("id")
    return mid if isinstance(mid, str) else None


def event_row(e: Wire) -> dict[str, Any]:
    return {"id": e["id"], "session_id": e["sessionId"], "seq": e["seq"], "at": _ts(e["at"]), "type": e["type"],
            "message_id": event_message_id(e), "payload": e["payload"]}


def event_wire(r: Row) -> Wire:
    return {"id": r["id"], "sessionId": r["session_id"], "seq": r["seq"], "at": r["at"], "type": r["type"], "payload": r["payload"]}


# ── Memory, knowledge ───────────────────────────────────────────────────────
def memory_row(m: Wire, *, is_seed: bool, source_mode: str | None = None) -> dict[str, Any]:
    return {"id": m["id"], "character_id": m["characterId"], "world_id": m["worldId"], "kind": m["kind"], "text": m["text"],
            "importance": m["importance"], "source_session_id": m.get("sourceSessionId"),
            "source_message_id": m.get("sourceMessageId"), "source_variant_id": None, "source_mode": source_mode,
            "about_character_id": None, "created_at": _ts(m["createdAt"]), "last_recalled_at": None, "recall_count": 0,
            "superseded_by": None, "is_seed": is_seed}


def memory_wire(r: Row) -> Wire:
    out: Wire = {"id": r["id"], "characterId": r["character_id"], "worldId": r["world_id"], "kind": r["kind"],
                 "text": r["text"], "importance": r["importance"]}
    _opt(out, "sourceSessionId", r["source_session_id"])
    _opt(out, "sourceMessageId", r["source_message_id"])
    out["createdAt"] = r["created_at"]
    return out


SEED_CHUNKER = "seed@1"
SEED_TOKENIZER = "chars/4"


def knowledge_source_row(k: Wire, *, is_seed: bool, chunk_count: int) -> dict[str, Any]:
    """Seed import (doc 02 §5, OQ-1): no vectors yet, so a shipped `indexed` source is stored `keyword_only`."""
    status = "keyword_only" if k["status"] == "indexed" else ("queued" if k["status"] == "indexing" else k["status"])
    return {"id": k["id"], "character_id": k["characterId"], "world_id": k["worldId"], "title": k["title"],
            "type": k["type"], "url": k.get("url"), "mime": None, "original_name": None, "bytes": k.get("bytes"),
            "pages": k.get("pages"), "sha256": None, "status": status, "chunk_count": chunk_count,
            "extractor_version": None, "chunker_version": SEED_CHUNKER, "tokenizer": SEED_TOKENIZER,
            "embedding_space_id": None, "has_original": False,
            "error": {"message": k["error"]} if k.get("error") else None,
            "added_at": _ts(k.get("addedAt")) or "1970-01-01T00:00:00.000Z", "indexed_at": None, "is_seed": is_seed}


API_STATUS = {"queued": "indexing", "extracting": "indexing", "chunking": "indexing", "embedding": "indexing",
              "indexed": "indexed", "keyword_only": "keyword_only", "failed": "failed"}


def knowledge_source_wire(r: Row, cited_count: int) -> Wire:
    out: Wire = {"id": r["id"], "characterId": r["character_id"], "worldId": r["world_id"], "title": r["title"],
                 "type": r["type"], "status": API_STATUS[r["status"]]}
    _opt(out, "bytes", r["bytes"])
    _opt(out, "pages", r["pages"])
    readable = r["status"] in ("indexed", "keyword_only")
    if readable:  # the seed build's convention: passages and citations are counted for readable sources only
        out["chunks"] = r["chunk_count"]
    _opt(out, "url", r["url"])
    if readable:
        out["citedCount"] = cited_count
    out["addedAt"] = r["added_at"]
    err = r["error"]
    if err:
        out["error"] = err.get("message") if isinstance(err, dict) else str(err)
    return out


def chunk_rows(chunks: list[Wire], source: Wire, section_id: Callable[[Wire], str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Seed chunks have no sections: synthesise one section per chunk (parent text = child text, doc 02 §3.8)."""
    sections: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for ch in sorted(chunks, key=lambda c: c["index"]):
        sid = section_id(ch)
        text = ch["text"]
        tokens = max(1, len(text) // 4)
        sections.append({"id": sid, "source_id": source["id"], "character_id": source["characterId"],
                         "world_id": source["worldId"], "idx": ch["index"], "heading_path": ch.get("locator"),
                         "page_start": None, "page_end": None, "text": text, "token_count": tokens,
                         "char_start": 0, "char_end": len(text)})
        rows.append({"id": ch["id"], "source_id": source["id"], "section_id": sid, "character_id": source["characterId"],
                     "world_id": source["worldId"], "idx": ch["index"], "locator": ch.get("locator"),
                     "heading": ch.get("locator"), "text": text, "token_count": tokens, "char_start": 0,
                     "char_end": len(text)})
    return sections, rows


def chunk_wire(r: Row) -> Wire:
    out: Wire = {"id": r["id"], "sourceId": r["source_id"], "index": r["idx"]}
    _opt(out, "locator", r["locator"])
    out["text"] = r["text"]
    return out


# ── Ledger ───────────────────────────────────────────────────────────────────
_USAGE = (("model", "model"), ("provider", "provider"), ("pricePeriod", "price_period"), ("sessionId", "session_id"),
          ("characterId", "character_id"), ("jobId", "job_id"), ("tokensIn", "tokens_in"), ("tokensCached", "tokens_cached"),
          ("tokensOut", "tokens_out"))


def usage_row(u: Wire, *, is_seed: bool, local_day: Callable[[str], str]) -> dict[str, Any]:
    at = _ts(u["at"])
    row: dict[str, Any] = {"id": u["id"], "at": at, "local_day": local_day(at), "category": u["category"], "purpose": None,
                           "generation_id": None, "message_id": None, "cost_usd": u["costUsd"], "cost_source": "provider",
                           "estimated_cost_usd": u.get("estimatedCostUsd"), "energy_points": u.get("energyPoints"),
                           "latency_ms": u.get("latencyMs"), "counts_to_creation_cap": False, "is_seed": is_seed}
    for key, col in _USAGE:
        row[col] = u.get(key)
    return row


def usage_wire(r: Row) -> Wire:
    out: Wire = {"id": r["id"], "at": r["at"], "category": r["category"]}
    for key, col in _USAGE:
        _opt(out, key, r[col])
    out["costUsd"] = r["cost_usd"]
    _opt(out, "estimatedCostUsd", r["estimated_cost_usd"])
    ep = r["energy_points"]
    _opt(out, "energyPoints", int(ep) if isinstance(ep, float) and ep.is_integer() else ep)
    _opt(out, "latencyMs", r["latency_ms"])
    return out


# ── Jobs ─────────────────────────────────────────────────────────────────────
def job_rows(j: Wire, *, is_seed: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    created = _ts(j["createdAt"])
    row = {"id": j["id"], "character_id": j["characterId"], "kind": j["kind"], "target_field": j.get("targetField"),
           "status": j["status"], "progress": j["progress"], "estimated_cost_usd": j["estimatedCostUsd"],
           "actual_cost_usd": j["actualCostUsd"], "input": None, "error": j.get("error"), "is_seed": is_seed,
           "created_at": created, "started_at": _ts(j.get("startedAt")), "finished_at": _ts(j.get("finishedAt"))}
    tasks = [{"id": t["id"], "job_id": j["id"], "ord": i, "type": t["type"], "emotion": t.get("emotion"), "status": t["status"],
              "attempt": t["attempt"], "max_attempts": t["maxAttempts"], "idempotency_key": f"{j['id']}:{i}",
              "provider_called_at": None, "target_path": None, "result_ref": t.get("resultRef"),
              "preview_url": t.get("previewUrl"), "cost_usd": None, "error": t.get("error"), "created_at": created,
              "started_at": None, "finished_at": None} for i, t in enumerate(j["tasks"])]
    return row, tasks


def task_wire(t: Row) -> Wire:
    out: Wire = {"id": t["id"], "type": t["type"]}
    _opt(out, "emotion", t["emotion"])
    out.update(status=t["status"], attempt=t["attempt"], maxAttempts=t["max_attempts"])
    _opt(out, "resultRef", t["result_ref"])
    _opt(out, "previewUrl", t["preview_url"])
    _opt(out, "error", t["error"])
    return out


def job_wire(r: Row, tasks: Iterable[Row]) -> Wire:
    out: Wire = {"id": r["id"], "characterId": r["character_id"], "kind": r["kind"]}
    _opt(out, "targetField", r["target_field"])
    prog = r["progress"]
    out.update(status=r["status"], progress=int(prog) if isinstance(prog, float) and prog.is_integer() else prog,
               estimatedCostUsd=r["estimated_cost_usd"], actualCostUsd=r["actual_cost_usd"],
               tasks=[task_wire(t) for t in sorted(tasks, key=lambda t: t["ord"])])
    _opt(out, "error", r["error"])
    out["createdAt"] = r["created_at"]
    _opt(out, "startedAt", r["started_at"])
    _opt(out, "finishedAt", r["finished_at"])
    return out
