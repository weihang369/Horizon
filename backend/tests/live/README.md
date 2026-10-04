# Live OpenRouter check (manual, ≤ $0.05)

This one test talks to the real OpenRouter API through the real gateway. It confirms the response shapes that the recorded fixtures in `tests/fixtures/openrouter/` assume (M2 design OQ-C).

- CI never runs it.
- A normal `uv run pytest` deselects it.
- It is skipped unless you opt in.

## What it checks

- **Key, credits and models:** the shapes of `/key` and `/credits`, and whether `/models` lists the image and music models.
- **Chat:** a 1-token DeepSeek completion. It also checks whether `logprobs` combined with `require_parameters` moves the call off DeepSeek.
- **Streaming:** that the generation ID stays the same on every chunk, and that usage arrives on the last one.
- **Cost lookup:** the `/generation?id=` lookup, and whether it agrees with the reported cost.
- **Jev:** one call that asks a choice, a yes/no and a score question.
- **Embeddings:** one embedding, recording the vector length.
- **Spend:** the total in the ledger must stay ≤ $0.05.

## Run it

1. Put your key in the repo-root `.env` yourself, as `OPENROUTER_API_KEY=…`. That file is git-ignored. Never paste the key into chat or code.
2. From `backend/`, run the line for your shell.

   PowerShell:

   ```
   $env:HORIZON_LIVE=1; uv run pytest -m live -s
   ```

   bash:

   ```
   HORIZON_LIVE=1 uv run pytest -m live -s
   ```

3. Read the redacted report the run prints. A copy is saved as `data/live-report.json`, which is git-ignored. The report holds only keys, types and flags: no content, and never the key.
4. For each shape the report confirms, set `"verified": true` in the matching file under `tests/fixtures/openrouter/`. Where the report shows a difference, fix the parser and the fixture together.
