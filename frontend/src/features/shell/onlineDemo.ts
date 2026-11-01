// The mock build (the public demo on Vercel, and `npm run dev:mock`) runs on recorded data in the browser. It has no
// backend: nothing calls an AI and no key is ever used, so wherever the HTTP build asks for a key, the demo says so
// instead and points at running Horizon locally (the user's decision, 2026-10-20). Settings → Connection and the key
// prompt (O05) share these strings.
import { client } from "../../client";

export const NO_BACKEND = client.kind === "mock";
/** README "Run it locally" on GitHub. */
export const RUN_LOCALLY_URL = "https://github.com/weihang369/Horizon#run-it-locally";
export const RUN_LOCALLY_LABEL = "How to run it locally ↗";
export const ONLINE_DEMO_NOTICE =
  "This online demo never uses a key: everything here was recorded. To use real AI, run Horizon on your own computer " +
  "with your own OpenRouter key.";
