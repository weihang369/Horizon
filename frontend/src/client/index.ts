// The app's one client instance. Owner: EE + SWE.
// `VITE_HORIZON_CLIENT=http` (`vite --mode http`, frontend/.env.http; the root `npm run dev`) talks to the local backend
// through the Vite proxy; unset or `mock` (the root `npm run dev:mock`, the Vercel build) is the MockClient (D-73). The
// value is a build-time constant, so the unused client is dropped from the bundle. vite.config.ts refuses any other
// value, an `http` build outside `--mode http`, and `http` on Vercel (scripts/build/clientGuard.ts).
import { MockClient } from "../mock/MockClient";
import type { MockDevApi } from "../mock/MockClient";
import type { HorizonClient } from "./HorizonClient";
import { HttpClient } from "./http/HttpClient";

const impl: HorizonClient = import.meta.env.VITE_HORIZON_CLIENT === "http" ? new HttpClient({ baseUrl: "/api/v1" }) : new MockClient();

export const client: HorizonClient = impl;
/** Dev controls (O18); null under the HttpClient. */
export const mockDev: MockDevApi | null = impl instanceof MockClient ? impl.dev : null;
export type { HorizonClient } from "./HorizonClient";
