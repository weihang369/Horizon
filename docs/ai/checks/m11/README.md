# M11 per-item results

Copied from M11's paid runs (gitignored under `data/evals/`, where these folders are marked `.keep`), so every answer
can be re-scored later at no cost. Decision rows have Jev's choice, its `confidence` and the full `probabilities` next
to the item's label; the figures they back are in [../m11.md](../m11.md).

| File | Run | What it is |
|---|---|---|
| `debate-histories.jsonl` | `20261014T100033-debate-history-de436c` | 10.1, one row per script; the histories themselves are committed in `evals/debates/` |
| `judges.jsonl` | `20261014T104638-decisions-140e4d` | 10.4, the four judge validations (240 items) |
| `engages-plants-1.jsonl` … `-4.jsonl` | `…110753-a58983`, `…111213-f5bbaa`, `…111604-962705`, `…111757-24798d` | 10.4 (D31.2), the rebuilt `judge_engages` plants per instruction; their text is in `evals/debates/planted/engages.json` |
| `judge-engages-revalidated.jsonl` | `20261014T111907-decisions-f82569` | 10.4, `judge_engages` on the rebuilt plants (60) |
| `debate-member.jsonl` | `20261014T104957-decisions-ace67c` | 10.5, the member slice (90) |
| `emotion-debate.jsonl` | `20261014T105923-decisions-711697` | 10.6, the emotion set with the debate slice (80 rows; `…105615-8619c8` stopped at its cap before writing any) |
| `debate-timing.jsonl` | `20261014T112102-latency-176f0b` | 10.7, 30 plans, 10 bridges and 5 verdicts: `S` and `L` per request |
| `debate-suite.jsonl` | `20261014T113208-debate-193d74` | 10.8, the 12 debates each way (48 rows: the rubric bars and means per side) |
| `debate-quality.jsonl` | `20261014T114256-debate-quality-d72973` | 10.9, both judges over every argument of the 13 histories (242) |
| `freerun-debate.jsonl`, `freerun-watch.jsonl` | `…114520-freerun-300748`, `…114756-freerun-c95999` | 10.10, per run; the watch scenes are committed as `evals/watch/freerun_m11_{0,1,2}.json` |
| `talk-finished.jsonl` | `20261014T115815-decisions-aedfc0` | 10.11, `talk_finished` v3 (120) |
| `emotion-watch.jsonl` | `20261014T115930-decisions-f05312` | 10.11, the watch emotion slice with its growth (120 rows) |
| `recaps.jsonl` | `20261014T115959-summary-34b3c9` | 10.11, the 10 recaps re-scored with the premise |
| `who-speaks.jsonl` | `20261014T120018-decisions-a03223` | 10.11, `who_first`, `who_second`, `who_scene` v3 (140) and `who_next` (40) |
| `emotion-line-v3.jsonl` | `20261014T120946-decisions-e701bf` | 10.11 after D33, `emotion_line` v3 from the store ($0) |

**10.2's plant run is gone:** `20261014T102813-debate-plant-ae0f85` was pruned by the runner's keep-the-newest-20 rule
before its folder was marked. The 46 rewrites it made are committed in `evals/debates/planted/d01..d12.json`, and its
amount is in `data/evals/spend.jsonl`.

The recap rows leave out their input lines, which rebuild exactly from the committed histories in `evals/watch/`
(`recap_context`). The raw provider responses stay in the local response store (`data/cache/`, W10), keyed by request.
