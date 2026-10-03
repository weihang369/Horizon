# Spike (a): sqlite-vec under aiosqlite

**Question.** Can sqlite-vec be loaded into every pooled aiosqlite connection from SQLAlchemy's `connect` event (doc 01 §3)?

**Result: yes (Windows 11, CPython 3.12.13 uv-managed, SQLite 3.53.1, sqlite-vec 0.1.9, SQLAlchemy 2.1.3, aiosqlite).**
- `dbapi_conn.run_async(fn)` gives `fn` the `aiosqlite.Connection`. Its `enable_load_extension` / `load_extension` are **coroutines**, so `fn` must be `async` and await them. A plain lambda fails with `TypeError: object NoneType can't be used in 'await' expression`.
- `vec_version()` answers, and a `vec0` table with a `partition key` and `distance_metric=cosine` returns correct KNN order.
- Test: `tests/spikes/test_vec_load.py`.

**macOS / Linux:** CI later (there is no CI workflow yet). python-build-standalone builds `sqlite3` with extension loading on every platform, so no difference is expected.
