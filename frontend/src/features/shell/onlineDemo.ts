// The mock build (the public demo on Vercel, and `npm run dev:mock`) runs on recorded data in the browser. It has no
// backend: a key typed there is never sent anywhere (only its last 4 characters are kept, for the hint), and nothing
// calls an AI; any `sk-or-…` text unlocks the scripted live mode (R15). Settings → Connection and the key prompt say so,
// so nobody pastes a real key into a public page. Owner: SWE.
import { client } from "../../client";

export const NO_BACKEND = client.kind === "mock";
export const RUN_LOCALLY_URL = "https://github.com/weihang369/Horizon#run-locally-with-the-backend";
export const ONLINE_DEMO_NOTICE =
  "This demo runs in your browser on recorded data. It never calls an AI and never sends a key anywhere: any text " +
  "starting with sk-or- unlocks its scripted live mode, so don't paste your real key here. For real AI, run Horizon " +
  "on your own computer with your own OpenRouter key.";
