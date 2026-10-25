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
8. Phase 9's review (`evals/reviews/m13-review.md`) fixed three builder flaws before any paid run:
   - `judge_over_mention` paired a fact with a "new" topic that shared its subject (peonies with "your favourite
     flower"), and its replies were ungrammatical; `facts.unrelated` now picks topics sharing no subject;
   - layer 3 wrapped the fact list and repeated three pairs whole (17 distinct, counted as 20); now 20 distinct;
   - one debate stretch's language tag (`ms` on a Chinese line).
9. `recall.checkMs` from the tail: `horizon eval memory --part recall --latency` (store-bypassed, every check read to
   its end) reports the slowest landing per probe, rather than the `latency` suite D40 names: recall's checks are the
   suite's own calls, and the latency suite drives whole turns. Same measurement (store-bypassed, the real tail).
10. The comparisons run as `memory --part recall --arm …` (`search=bm25|dense`, `mmr=off`, `lambda=…`, `space=…`) and
    `horizon eval memory-compare <default> <arm>` (K3's rule per probe kind; Recall@6 for the instruction, hit@3 for
    the rest); `dupCosine` as `--part dup` (140 planted pairs, 40 the same fact).
11. Paid-run estimates from the suite's own plan (off-peak): rewrite 36 ≈ $0.077, recall 100 ≈ $0.027, layer 3 20 ≈
    $0.120, dup ≈ $0.0006 (D41: ≈ $0.05 / $0.03 / $0.12 / $0.005).
12. D28 changes one committed M12 item: `docs` `dcs-109` (debate d13#8) is late enough that M12's order dropped Victor's
    gate; D28 now trims the arguments and keeps it, so the state live sends carries Victor's titles and the cut
    arguments. Its label (Mei's documents) is unchanged; the set was rebuilt so the item stays as live asks it. The
    other 120 `docs` items, `standalone` and `english` are byte-identical.
13. e2e's "Continue live" test was flaky before M13 (the scripted line is seeded by the session's wall-clock
    `createdAt`; 2 of 6 lines open with a short sentence, and the test read the first paragraph). Fixed in the test
    (the last paragraph); 8/8 after. Recorded in m13.md §0.
14. A planted memory id must be contract-valid (`^[a-z]+_[0-9A-Za-z]{1,40}$`): `mem_ovf_f01_16` reached a reply's
    System 1 rows in the recall timing run and the messages endpoint failed its contract check (500). The suite's
    planted and synthetic ids are valid now (`mem_ovff01x16`, `mem_amara00x01`, `msg_longoneononeen0005`).
15. Check 4 and D33's timing: `horizon eval latency --part recall` (10 recall-only turns asking for an overflow
    memory, then 50 turns with both gates; the corpus loaded and each corpus character given a 50-memory overflow).
    Check 2: `horizon eval memory --part rewrite --latency --limit 10` (each writer run timed, store-bypassed).
16. Full backend suite on eb9df14 (2026-10-16, 51 min, e2e and eval runs beside it): **1979 passed, 3 failed**,
    10 deselected. (a) `test_eval_m12` gate sets: `dcs-109` under D28 (item 12, fixed in 936dbe4); (b)
    `test_decider::test_timeouts_from_config` still expected `importance` at the 3 s default (D42 gave it and
    `memory_guard` 30 s, background); the test now says so; (c) the load-sensitive keyword-search guard (p99 54.2 ms
    under load; 34–35 ms alone, passing twice), as M12 recorded.
17. Phase 10's runs approved by the user (2026-10-16, before 18:00 KL; run off-peak): decisions ≈ $0.012, rewrite
    ≈ $0.079, dup ≈ $0.001, check 2 ≈ $0.021, recall ≈ $0.027, arms ≤ $0.045, checkMs tail ≈ $0.019, check 4 + D33
    ≈ $0.047, layer 3 ≈ $0.120, the provider probe ≈ $0.0001 (with one free GET of the provider list). Total ≤ $0.37
    (D41 ≈ $0.27: the arms' fixed transcript embeddings and check 4's both-gates turns priced in full here).
18. Phase 10's first results and the maintainer's choices (2026-10-16, 19:4x KL):
    - `importance`: passes (balanced 0.88 dev / 0.87 test; within one level 0.89 / 0.89). No change.
    - `memory_guard`: the rule gave `t_keep` 0.40; but the real rewrite run showed 0.70 holding back 16 of 35
      legitimate changes (p 0.27–0.68): the set had no changed-value items, and the question didn't say a changed
      detail counts as kept. **Choice: reword the guard (v2), add changed-value items, re-run, then the rule.**
    - `earlier`: Jev's p runs low; B5's rule gives `t_gate` 0.15 (test recall 1.00, precision 0.55). **Choice: 0.15.**
    - `recall`: the rule gave 0.30, but test precision 0.75 didn't confirm it. **Choice: keep 0.50.**
    - `dupCosine`: no cosine separates a reworded fact (0.81–0.97) from an extension (0.97–0.99); at 0.92 only 34 %
      of dev hits are true duplicates. **Choice: Jev decides** ("same fact?" for an add whose nearest memory is
      at or above the cosine pre-filter), validated on the labelled pairs.
19. Runs 2026-10-16 (19:13–19:35 KL), all off-peak, folders `.keep`:
    - decisions: importance (20261016T111255, $0.0024), memory_guard v1 (111343, $0.0023), earlier (111456, $0.0030),
      recall (111559, $0.0022); memory_guard v2 (113017, $0.0031) → `t_keep` 0.35 (v3): test lossy through 0.04,
      changed 7/7 and faithful 1.00 supersede; same_fact (113154, $0.0022): "different" pairs p 0.01–0.03, rewordings
      0.25–0.95, policy 121/122; the literal rule gives `t_same` 0.05 (grid bottom) — goes to the user.
    - rewrite (111302, $0.0156): 37/37 valid, no `length`; output p50 240 / max 697 tokens (35 % / 63 % of the cap);
      the 8,000-token piece ≈ 8,985 in, 294 out of 500. Rewritten, not duplicated 35/40 (88 %, 0.74–0.95); untouched
      503/503; secrets 0/6; small talk 0/6 over one line; guard kept beside 16 (v1 at 0.70).
    - rewrite again with guard v3 (113323, $0.0009: every memory-1 call served by the store): kept beside 6.
    - dup sweep (111646, $0.00002 after the empty-reword fix; the first try (111558) failed on an empty text, no
      spend): no cosine reaches 95 % precision (rewordings 0.81–0.97, extensions 0.97–0.99).
    - layer 3 (111309, $0.0416): probe use 37/40 (92 %, 0.80–0.97) ✓; 67 memories written, 0 duplicates; over-mention
      20/40 by an unvalidated judge.
    - B4 for the four new judges (113432, $0.0022; real items labelled from the states, `m13_real.json`):
      missed PASS (real 0.90), unsupported PASS (0.90), lost FAIL (0.50, n 18: it counts the conversation's own
      changes as losses), over_mention FAIL (0.63: it can't see the recent lines, and counts the character's own life).
    - Read by hand: supported 80/81 (the one real case is a perspective leak: Hana's line says the band "moved from
      Fridays", a detail only Rin's list held); lost after guard v3: 3 of 18 unique supersedes (a past event, a
      reaction's severity, the firm).
20. Recall probes (20261016T113017, $0.0099): in-session hit@3 45/60 (75 %, 0.63–0.84) by search order, Recall@6
    58/60 (97 %), kept after Jev 56/60 (93 %, 0.84–0.97) ✓. Overflow hit@3 10/40 (25 %), Recall@6 32/40 (80 %), kept
    18/40 (45 %) ✗. In 14 overflow misses the needed memory was checked and Jev ranked it far above the rest (p
    0.19–0.44 against ≈ 0.03) but under `t_recall` 0.5, so nothing was kept; at 0.30, 8 more would be (26/40, 65 %).
    The overflow probes lean on the memory indirectly, and an overflow memory is old and unimportant by construction
    (its weight ranks it below the distractors in the merge). BM25-only arm (113719, $0): in-session Recall@6 15/60,
    overflow 11/40: the dense half earns its place.
21. The comparisons (memory-compare, K3's rule): `search=dense` wins in-session (hit@3 97 % vs 75 %; dev +17.1 points,
    +7.3 to +29.3; test +31.6) and loses on overflow (−17.9); `search=bm25` loses (in-session −61.0); `mmr=off` and
    `lambda=0.5` tie. All four arms cost $0 (the store served every embedding).
22. The user's second round of choices (2026-10-16, ≈ 19:45 KL): dense-only search for the session's lines (BM25 only
    as the fallback without a vector; overflow stays hybrid); a relative keep rule (when nothing passes `t_recall`,
    keep the top candidate if p ≥ 0.25 and ≥ 3× the runner-up); keep `t_keep` 0.35 and fix memory-1's perspective
    leak; reword `judge_memory_lost` and `judge_over_mention` (v2), re-validate and re-judge the saved outputs.
23. Round 2 built (uncommitted runs pending): memory-2 (the perspective rule), `recall.linesDense` / `standoutP` 0.25 /
    `standoutRatio` 3, judge_memory_lost v2 and judge_over_mention v2 (sees `quoted_recent`). Instruction arm
    (113847, $0.00003): the old instruction ties or loses → default stays (K3). B4 for the v2 judges (114550,
    $0.0025): lost PASS (real 0.94, n 18), over_mention PASS (real 0.90).
24. NEXT (all already approved): re-judge the saved rewrite (lost) and layer-3 (over-mention, with recent lines)
    outputs (needs a small `--part rejudge` reading results/judge_states, ≈ $0.003); re-run recall probes (dense
    lines + standout, ≈ $0.01) and the rewrite suite (memory-2, ≈ $0.02); then the timing runs ALONE: check 2
    (`memory --part rewrite --latency --limit 10`), the checkMs tail (`memory --part recall --set dev --latency`),
    check 4 (`latency --part recall`), and `embed-probe --set Nebius,DeepInfra,SiliconFlow`. Open choice: `t_same`
    (rule gives 0.05; recommend keeping 0.50). Then doc 09 M12/M13 notes, doc 13 W6/W12, m13.md, phase 12.
    Paid spend so far today ≈ $0.088.
25. Done 2026-10-16 (20:35–21:05 KL, off-peak): `--part rejudge` built (saved states, the judges' current versions,
    over-mention gains its turn's recent lines) and run ($0.0003); recall round 2 ($0.0027); rewrite on memory-2
    ($0.0140); check 2 ($0.0039); the checkMs tail ($0.0068); check 4 + D33 ($0.0355); the provider probe ($0.00002).
    Found: the rewrite call writes `"about": 0` for the user and D13 dropped those lines (8 a memory-1 run, all 5 of
    memory-2's long piece). The user's third round: `t_same` 0.50; `checkMs` 1,500; D33's 939 ms tail accepted;
    over-mention accepted; lost details and leaks accepted; overflow recall carried to M14; an `about` naming no one
    present reads as the user (built, rewrite re-run $0.0006). Total M13 spend $0.1518 over 26 runs. Written up in
    m13.md (phase 10, the choices, "What M13 found", "What M14 inherits").
