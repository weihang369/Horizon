// S08 Session Setup: foundation stub (Builder D replaces it). Owner: EE (stub).
import type { Route } from "../../router";
import { StubScreen } from "../../app/stubs";

export function SetupScreen({ route }: { route: Extract<Route, { name: "setup" }> }) {
  return <StubScreen id="S08" name="Session Setup" owner="Builder D" links={[]}><code>{JSON.stringify(route)}</code></StubScreen>;
}
