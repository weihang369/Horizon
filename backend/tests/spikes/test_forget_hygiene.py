"""Spikes for Forget's byte-level hygiene (knowledge-memory-storage design D16, task 1.1).

(a) a vec0 UPDATE writes zeros into the packed vector chunk in place, so zero-then-delete leaves no vector bytes;
(b) FTS5 `secure-delete` removes a deleted row's terms from the index segments;
(c) `PRAGMA secure_delete = ON` + `wal_checkpoint(TRUNCATE)` leave a deleted row's text in neither file;
(d) a TRUNCATE checkpoint reports busy while a reader holds a snapshot, and succeeds once it is gone.
"""

from __future__ import annotations

import sqlite3
import struct
from pathlib import Path

import sqlite_vec

WORD = "zorbleflaxion"
TEXT = f"Hana's secret word is {WORD} and nobody else knows it."
VEC = [1234.5, -6789.25, 4321.125, 9876.5]


def _open(path: Path, *, secure: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA journal_mode=WAL")
    if secure:
        conn.execute("PRAGMA secure_delete=ON")
    return conn


def _bytes(path: Path) -> bytes:
    out = path.read_bytes()
    wal = path.with_name(path.name + "-wal")
    if wal.exists():
        out += wal.read_bytes()
    return out


def _schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE items (rid INTEGER PRIMARY KEY, text TEXT NOT NULL);
        CREATE VIRTUAL TABLE items_fts USING fts5(text, content='items', content_rowid='rid', tokenize='porter unicode61');
        CREATE TRIGGER items_ai AFTER INSERT ON items BEGIN INSERT INTO items_fts(rowid, text) VALUES (new.rid, new.text); END;
        CREATE TRIGGER items_ad AFTER DELETE ON items BEGIN
          INSERT INTO items_fts(items_fts, rowid, text) VALUES ('delete', old.rid, old.text); END;
        CREATE VIRTUAL TABLE items_vec USING vec0(rid INTEGER PRIMARY KEY, character_id TEXT PARTITION KEY,
          embedding FLOAT[4] distance_metric=cosine);
    """)


def _fill(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN")
    for i in range(1, 40):
        conn.execute("INSERT INTO items(rid, text) VALUES (?, ?)", (i, f"ordinary memory number {i} about tea"))
        conn.execute("INSERT INTO items_vec(rid, character_id, embedding) VALUES (?, 'c', ?)",
                     (i, sqlite_vec.serialize_float32([float(i), 1.0, 2.0, 3.0])))
    conn.execute("INSERT INTO items(rid, text) VALUES (100, ?)", (TEXT,))
    conn.execute("INSERT INTO items_vec(rid, character_id, embedding) VALUES (100, 'c', ?)",
                 (sqlite_vec.serialize_float32(VEC),))
    conn.execute("COMMIT")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _forget(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN")
    conn.execute("UPDATE items_vec SET embedding = ? WHERE rid = 100", (sqlite_vec.serialize_float32([0.0] * 4),))
    conn.execute("DELETE FROM items_vec WHERE rid = 100")
    conn.execute("DELETE FROM items WHERE rid = 100")
    conn.execute("COMMIT")


def test_a_vec0_update_zeroes_the_packed_vector(tmp_path: Path) -> None:
    db = tmp_path / "a.db"
    conn = _open(db)
    _schema(conn)
    _fill(conn)
    packed = struct.pack("<4f", *VEC)
    assert packed in _bytes(db)
    _forget(conn)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert packed not in _bytes(db)
    assert conn.execute("SELECT count(*) FROM items_vec WHERE rid = 100").fetchone()[0] == 0
    conn.close()


def test_a_vec0_delete_alone_also_clears_the_bytes_in_0_1_9(tmp_path: Path) -> None:
    """Observed with sqlite-vec 0.1.9: a delete zeroes the slot too. Forget still zeroes first (D16), so an upgrade that
    only clears the validity bit stays safe; this test flags such an upgrade."""
    db = tmp_path / "a2.db"
    conn = _open(db)
    _schema(conn)
    _fill(conn)
    conn.execute("DELETE FROM items_vec WHERE rid = 100")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert struct.pack("<4f", *VEC) not in _bytes(db)
    conn.close()


def test_b_fts5_secure_delete_drops_terms(tmp_path: Path) -> None:
    db = tmp_path / "b.db"
    conn = _open(db)
    _schema(conn)
    conn.execute("INSERT INTO items_fts(items_fts, rank) VALUES ('secure-delete', 1)")
    _fill(conn)
    assert WORD.encode() in _bytes(db)
    _forget(conn)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert conn.execute("SELECT count(*) FROM items_fts WHERE items_fts MATCH ?", (WORD,)).fetchone()[0] == 0
    data = _bytes(db)
    assert WORD.encode() not in data
    assert TEXT.encode() not in data
    conn.close()


def test_b_without_fts_secure_delete_the_term_lingers_until_optimize(tmp_path: Path) -> None:
    """Why the setting matters: a plain FTS5 delete appends a tombstone and keeps the term (the fallback optimizes)."""
    db = tmp_path / "b2.db"
    conn = _open(db)
    _schema(conn)
    _fill(conn)
    _forget(conn)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    lingered = WORD.encode() in _bytes(db)
    conn.execute("INSERT INTO items_fts(items_fts) VALUES ('optimize')")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert WORD.encode() not in _bytes(db)
    conn.close()
    assert lingered  # documents the failure mode the fallback exists for


def test_c_secure_delete_and_truncate_leave_no_text(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    conn = _open(db)
    _schema(conn)
    conn.execute("INSERT INTO items_fts(items_fts, rank) VALUES ('secure-delete', 1)")
    _fill(conn)
    _forget(conn)
    busy, _log, _done = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    assert busy == 0
    wal = db.with_name(db.name + "-wal")
    assert not wal.exists() or wal.stat().st_size == 0
    assert TEXT.encode() not in db.read_bytes()
    conn.close()


def test_d_truncate_is_busy_while_a_reader_holds_a_snapshot(tmp_path: Path) -> None:
    db = tmp_path / "d.db"
    w = _open(db)
    _schema(w)
    _fill(w)
    r = _open(db, secure=False)
    r.execute("BEGIN")
    r.execute("SELECT count(*) FROM items").fetchone()  # the snapshot starts at the first read
    _forget(w)
    busy, _log, _done = w.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    assert busy == 1
    r.execute("COMMIT")
    busy, _log, _done = w.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    assert busy == 0
    r.close()
    w.close()
