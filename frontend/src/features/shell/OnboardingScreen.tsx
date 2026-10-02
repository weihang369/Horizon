// S02 Onboarding: foundation stub (Builder A replaces it). Owner: EE (stub).
import type { Route } from "../../router";
import { navigate } from "../../router";
import { setPrefs } from "../../stores/prefs";
import { Button } from "../../ui/Button";
import { StubScreen } from "../../app/stubs";

export function OnboardingScreen({ route }: { route: Extract<Route, { name: "onboarding" }> }) {
  const done = (to: Route) => {
    setPrefs({ seenOnboarding: true });
    navigate(to);
  };
  return (
    <StubScreen id="S02" name={`Onboarding · card ${route.card ?? 1}`} owner="Builder A">
      <Button onClick={() => done({ name: "worlds" })}>Explore demo first</Button>
      <Button variant="secondary" onClick={() => done({ name: "settings", tab: "connection", from: "/worlds" })}>Enter key</Button>
    </StubScreen>
  );
}
