// The app's one client instance. Owner: EE.
// SWE swap (doc 05 §7): replace the next line with `const impl: HorizonClient = new HttpClient({ baseUrl: "/api" });`
import { MockClient } from "../mock/MockClient";
import type { MockDevApi } from "../mock/MockClient";
import type { HorizonClient } from "./HorizonClient";

const impl = new MockClient();

export const client: HorizonClient = impl;
/** Dev controls (O18); null once the HttpClient is in. */
export const mockDev: MockDevApi | null = impl instanceof MockClient ? impl.dev : null;
export type { HorizonClient } from "./HorizonClient";
