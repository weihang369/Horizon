# M10 per-item results

Copied from M10's paid runs (gitignored under `data/evals/`, where these folders are marked `.keep`), so every answer
can be re-scored later at no cost. Decision rows have Jev's choice, its `confidence` and the full `probabilities` next
to the item's label; the figures they back are in [../m10.md](../m10.md).

| File | Run | What it is |
|---|---|---|
| `who-speaks.jsonl` | `20261013T121715-decisions-d25795` | 10.3, `who_first` 60, `who_second` 90, `who_scene`'s first 60 |
| `who-scene-100.jsonl` | `20261013T122924-decisions-bc5510` | 10.3 after G11's growth: `who_scene`'s 100 (the first 60 from the store) |
| `talk-finished.jsonl` | `20261013T123602-decisions-3423ee` | 10.4, 120 items |
| `emotion-watch.jsonl` | `20261013T124526-decisions-108ce1` | 10.5, the 40-item watch slice (`emw-*`); M9's rows are in `../m9/` |
| `recaps-episode-1.jsonl` | `20261013T124938-summary-6b883b` | 10.6 on `episode-1` (the wrong languages; scored with the misused judge) |
| `recaps-episode-2.jsonl` | `20261013T125733-summary-fba377` | 10.6 on `episode-2`, scored without it (the recaps of `…125543-57f40b`, from the store) |
| `recaps-episode-3.jsonl` | `20261013T125958-summary-7e6e49` | 10.6 on `episode-3`, what shipped |
| `follow-timing.jsonl` | `20261013T130109-latency-3aa410` | 10.7, 50 follow-plan requests: `S` and `L` per request (a miss is `S + L > F + 400`, F = 12.3 ms) |
| `watch-timing.jsonl` | `20261013T131319-latency-59ca73` | 10.8, per scene (the timings are in the run's database and m10.md) |
| `freerun-watch.jsonl`, `freerun-group.jsonl` | `…131638-freerun-038af2`, `…132035-freerun-869ac7` | 10.9, per run (the steered lines are quoted in m10.md) |

The recap rows leave out their input lines, which rebuild exactly from the committed histories in `evals/watch/`
(`recap_context`). The watch histories themselves (10.1 and G11's growth) are committed there, not copied here. The
raw provider responses stay in the local response store (`data/cache/`, W10), keyed by request.
