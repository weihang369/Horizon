# Security policy

## Reporting a vulnerability

Please report security problems privately, not in a public issue: on GitHub, open the repository's **Security** tab
and choose **Report a vulnerability**. Include what you found, how to reproduce it, and what an attacker could do with
it. You'll get a reply within a week. Once a fix is released, you're welcome to be credited.

## What counts

Horizon is a local app: the backend binds to `127.0.0.1` and refuses any other address, and your OpenRouter key stays
on your machine. Reports we especially want:

- the API key leaking: into logs, error messages, exports, the cost ledger, the browser or a model call;
- the backend becoming reachable from another machine, or a web page making it act for someone else;
- an uploaded document, image or text escaping its folder under `data/` or running code;
- content that gets around the safety checks in a way the checks should catch;
- spending past the budget caps you set.

Out of scope: what OpenRouter and its model providers do with the requests they receive (see
[Privacy](README.md#privacy)), and the public demo, which runs on a mock client with no backend and no key.

## Supported versions

Fixes go into the latest release on `main` and into `dev`.
