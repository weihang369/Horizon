# M13 findings log (for docs/ai/checks/m13.md)

## Baselines
- 6ceb366 (M12) backend suite: 1842 passed, 10 deselected (44 min). Frontend: typecheck clean, lint warnings only,
  542 unit, 62 http; e2e not valid in the gate worktree (node_modules symlink → Vite 403 on fonts), run in main tree.

## Found while building
1. vec0 refuses `UPDATE … WHERE rid IN (…)` on a partitioned table ("UPDATE on partition key columns are not supported
   yet", sqlite-vec 0.1.9). Forget's vector zeroing (M5) failed for any memory with a vector (only no-key memories
   had been tested). Fixed: one row per statement. Same rule in the index's zeroing.
2. Virtual clock: two parallel children of one task each "gave up" the task's single activity token (the Jev wait and a
   parked embedding), so the count went negative and never settled. `asyncio.gather` also leaves children running
   after the parent is cancelled. Added `vclock.together` (a TaskGroup; each child holds its own token from creation;
   the last child hands the parent's back). The memory writer and the deep graph's two branches use it.
3. The 1:1 query rewrite's prefix must stay byte-identical to the reply's: the plan's cast view needed the memory list
   too (system message 1 now holds it under agent).
4. D24: X1's fixed-blocks cap (1,720) already included the 1,000-token list; the knob replaces that share.
5. D27: an `earlier` question is 227 tokens as sent (wording, examples, the S6 sentence), not ≈ 90. Every grown request
   stays far under the size check (largest budget 925 of 30,000 in the offline cases); Jev bills ≈ $0.00001 per
   candidate per plan. Build time +0.1–0.2 ms.
   - 1:1 +227 (3→4 questions, budget 417); group of 5 +1,135 (6→11, 925); watch +681 (3→6, 686);
     follow +908 (3→7, 776); debate 3 members +681 (3→6, 773).
6. D28 on M11's 90 committed debate states (193 member gates, every member gated with M12's ten titles):
   M12's order keeps 167 (10 states lose some); D28's keeps 193 (none lose any). Short states unchanged byte for byte.
7. A lone regenerated reply is below the run minimum (one character line, no user line): it is re-read with the next
   run that has a user line. The re-read id waits in `memory_reread` meanwhile.
