// S14 Settings: foundation stub (Builder A replaces it). Owner: EE (stub).
import type { Route } from "../../router";
import { StubScreen } from "../../app/stubs";

export function SettingsScreen({ route }: { route: Extract<Route, { name: "settings" }> }) {
  return <StubScreen id="S14" name="Settings" owner="Builder A" links={[{ label: "Worlds", to: { name: "worlds" } }]}><code>{JSON.stringify(route)}</code></StubScreen>;
}
