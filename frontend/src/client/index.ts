// The app's one client instance. Owner: EE + SWE.
// `VITE_HORIZON_CLIENT=http` (`vite --mode http`, frontend/.env.http) talks to the local backend through the Vite
// proxy; anything else, including the Vercel build, stays on the MockClient (D-73). The value is a build-time
// constant, so the unused client is dropped from the bundle.
import { MockClient } from "../mock/MockClient";
import type { MockDevApi } from "../mock/MockClient";
import type { HorizonClient } from "./HorizonClient";
import { HttpClient } from "./http/HttpClient";

const impl: HorizonClient = import.meta.env.VITE_HORIZON_CLIENT === "http" ? new HttpClient({ baseUrl: "/api/v1" }) : new MockClient();

export const client: HorizonClient = impl;
/** Dev controls (O18); null under the HttpClient. */
export const mockDev: MockDevApi | null = impl instanceof MockClient ? impl.dev : null;
export type { HorizonClient } from "./HorizonClient";
