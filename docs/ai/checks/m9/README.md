# M9 per-item results

Copied from M9's paid runs (gitignored under `data/evals/`, where these folders are marked `.keep`), so every
answer can be re-scored later at no cost. Each row has Jev's choice, its `confidence` and the full `probabilities`
(they sum to 1), next to the item's label. The figures they back are in [../m9.md](../m9.md).

| File | Run | What it is |
|---|---|---|
| `emotion.jsonl` | `20261012T110639-decisions-dbad0b` | 9.1, emotion_reply / emotion_greeting, 100 items |
| `reactions-1-face-in-state.jsonl` | `20261012T110831-decisions-55fc27` | 9.2 first run (Jev anchored on the listener's face) |
| `reactions-2-no-face.jsonl` | `20261012T111257-decisions-1e32fc` | 9.2 re-run without the face (D37) |
| `reactions-3-blind-set.jsonl` | `20261012T111933-decisions-02c007` | 9.2 the fresh blind set `rea2-*`, what shipped (D39) |
| `judges-v1.jsonl`, `judges-v2.jsonl` | `…112229-20a8cf`, `…112449-0f69cc` | 9.4 judge validation |
| `moodline.jsonl` | `20261012T112608-moodline-6db138` | 9.5 mood line on/off, 34 items |
| `latency.jsonl` | `…114001-3b782c`, `…121016-fd7be4` | 9.6 per turn: face source, face − first word (ms), Jev `turn_plan` ms and outcome |

The raw provider responses stay in the local response store (`data/cache/`, W10), keyed by request.
