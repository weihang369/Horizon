# Manual checks

Scripts that need something a normal test run must never touch: real money or local Docling models. They sit outside
pytest's test paths (`backend/tests/`), so `uv run pytest` and CI never collect them, and nothing is skipped or
deselected. Run each one on purpose, from `backend/`.

| Folder | What it checks | Needs | Run |
|---|---|---|---|
| [`live/`](live/README.md) | The real OpenRouter API through the real gateway: response shapes the recorded fixtures assume, a reply, Jev, embeddings, a portrait and a song job, a live session | `HORIZON_LIVE=1` and your key in the repo-root `.env`; spends ≤ $0.05 (the jobs file a little more, as its docstrings say) | `HORIZON_LIVE=1 uv run pytest manual/live -s` |
| `docling/` | Real document conversions with Docling: PDF and DOCX, page limits, the no-network worker | `npm run setup:docling` and `uv run horizon models fetch` once | `uv run pytest manual/docling` |

In PowerShell, set the variable first: `$env:HORIZON_LIVE=1; uv run pytest manual/live -s`.

Run them before a release (the live checks confirm the providers still answer in the shapes Horizon expects) and
after changing the converter (the Docling checks).
