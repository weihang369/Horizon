# Spike (b): FTS/vec triggers on FK-cascade deletes

**Question.** When a parent row is deleted and the child rows go by `ON DELETE CASCADE`, do the child's `AFTER DELETE` triggers fire so that the external-content FTS5 table and the vec0 table are cleaned (doc 02 §3.9)?

**Result: yes.**
- With `foreign_keys=ON`, deleting a parent fires the child's `AFTER DELETE` trigger once per cascaded row.
- The FTS `'delete'` command with the **old** values and `delete from vec where rid = old.rid` both run.
- After `VACUUM`, FTS hits still join back to the right rows through the explicit `rid INTEGER PRIMARY KEY`.
- No `recursive_triggers` pragma is needed.
- Test: `tests/spikes/test_cascade_triggers.py`.

**Consequence.** D3/D4 stand as designed: the repositories never delete index rows by hand.
