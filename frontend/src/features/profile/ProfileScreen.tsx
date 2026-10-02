// S06 Character Profile: foundation stub (Builder B replaces it). Owner: EE (stub).
import type { Route } from "../../router";
import { StubScreen } from "../../app/stubs";

export function ProfileScreen({ route }: { route: Extract<Route, { name: "profile" }> }) {
  return <StubScreen id="S06" name="Character Profile" owner="Builder B" links={[]}><code>{JSON.stringify(route)}</code></StubScreen>;
}
