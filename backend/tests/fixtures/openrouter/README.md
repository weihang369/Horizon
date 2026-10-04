# OpenRouter recorded responses

These are the recorded HTTP responses for the gateway's respx tests. CI makes no live calls (see the test-strategy table in doc backend/06).

## File format

- There is one file per response. Each has a `status`, optional `headers`, and either a JSON `body` or an `sse` list.
- `sse` holds the event-stream `data:` payloads in order. String entries are sent as-is, so `[DONE]` and `: comment` lines work.
- `tests/gwkit.py` turns a file into an `httpx.Response`, for example `response("chat_stream_ok")`.

## Verification

`"verified": false` means the shape was written from the OpenRouter docs or the Jev reference, not captured from the live API.

The manual live run (`backend/tests/live/`, M2 task 13) checks each shape. After that run:

- set `"verified": true` only on shapes the run confirmed;
- if the run finds a difference, fix the parser and the file in the same change.

## Keys

These files must never contain a real key. The only key-like values allowed are obviously fake ones starting `sk-or-test-`, and a test enforces this.
