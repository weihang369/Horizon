// S05 Character Wizard: foundation stub (Builder B replaces it). Owner: EE (stub).
import type { Route } from "../../router";
import { StubScreen } from "../../app/stubs";

export function WizardScreen({ route }: { route: Extract<Route, { name: "wizard" }> }) {
  return <StubScreen id="S05" name="Character Wizard" owner="Builder B" links={[]}><code>{JSON.stringify(route)}</code></StubScreen>;
}
