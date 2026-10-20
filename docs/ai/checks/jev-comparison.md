# The Jev model comparison: jev-1.13 against jev-1.14

The `jev-comparison` change (`openspec/changes/jev-comparison/`, design D1–D19). One variable changes: the Jev
decision model id. DeepSeek, every prompt, every bank question, the state builders and the judges stay as they are.
Whether to switch is the user's decision (task 8.1).

## §0 The base and the candidate's facts

### 0.1 The base (2026-10-20)

- Branch `feat/jev-comparison`, cut from local dev **33a68ec** (M15 squashed); origin/dev is still 4f696ad. The
  proposal is commit 06b84a6.
- **The baseline gates are M15's final gates** (m15.md 9.3, on the same tree). Backend: 2280 passed, 2 failed;
  one failure was fixed in M15. The other, `test_search_on_a_loaded_database_is_fast`, is this machine's known
  keyword-p99 failure, 56 ms against the test's 50 ms. Frontend: 563 passed / 63 http; e2e 66 passed, 2 skipped.
- **On the branch tip:** `ruff` clean; `mypy` clean (239 files).

### 0.2 The candidate (checked 2026-10-20)

| Fact | Value | Source |
|---|---|---|
| Newest Jev | **Jev 1.14** (`jev-1.14.0`), "the newest Jev release, available from October 14, 2026" | docs.typesafe.ai/models.md |
| OpenRouter id | `typesafe/jev-1.14` (listed beside `typesafe/jev-1.13`, `typesafe/jev-router`, `~typesafe/jev-latest`) | openrouter.ai/typesafe |
| Dated snapshot | none mentioned. OpenRouter's per-model page `openrouter.ai/typesafe/jev-1.14` returned 404 | both |
| Price | $0.042 per million input tokens; output free; **the same as 1.13** | docs.typesafe.ai/models.md |
| Limits | 64k per request and 32k per question by default, **the same as 1.13**. 262k each only with the opt-in `TypeSafe-Danger-Zone-Long-Context` header (unused). Rate limits per organisation; over a limit → 429 | docs.typesafe.ai/models.md |
| jev-1.13 | still listed under "Current models", **no end date** | docs.typesafe.ai/models.md |
| Aliases | TypeSafe's `jev-latest` → **1.13**; `jev-preview` → **1.14**. "If you have tuned confidence thresholds against one version, send that version's ID instead of the alias." | docs.typesafe.ai/models.md |
| Newer than 1.14 | none | docs.typesafe.ai/llms.txt (only a `jev-1.13` jaggedness page; no 1.14 page yet) |
| API | new in the docs since group A: a `box` primitive and image inputs (`images.md`). Neither is used by Horizon; the decisions endpoint and the three question types are unchanged in the index. The answer shape is confirmed by the parse check (6.1) | docs.typesafe.ai/llms.txt |

- **A finding for the user:** TypeSafe's own aliases still point their default (`jev-latest`) at 1.13 and call 1.14
  `preview`. Horizon pins exact ids (NFR-14), so this changes nothing in the plan. It is context for the decision
  at 8.1.
- **0.3: the expected id and price were right** (`typesafe/jev-1.14`, $0.042 per million), so the conditional
  `decider` and `demo-data` deltas stand as written, and D3's per-model price isn't needed (same price).

### 0.4 The 1.13 keys after the per-model salt (task 2.3, $0)

With the salt now taken from each model's own canary baseline (design D5), the manifest was rebuilt in memory from
`data/cache/` and `private/evals/cache/`. **3,684 of 3,684** bodies still find their stored jev-1.13 answer, and all
22 sets list the same body hashes as the committed `jev-1.13-requests.json`. Nothing paid is lost.
