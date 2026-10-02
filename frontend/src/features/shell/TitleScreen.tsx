// S01 Title: foundation stub (Builder A replaces it). Owner: EE (stub).
// Any key or click unlocks audio and goes to Onboarding (first run) or World Select (APP-01 AC2).
import { useEffect } from "react";
import { audio } from "../../audio/engine";
import { navigate } from "../../router";
import { prefs } from "../../stores/prefs";
import { StubScreen } from "../../app/stubs";

export function TitleScreen() {
  useEffect(() => {
    const go = (e: Event) => {
      if (e instanceof KeyboardEvent && (e.ctrlKey || e.altKey || e.metaKey)) return;
      void audio.unlock();
      navigate(prefs.getState().seenOnboarding ? { name: "worlds" } : { name: "onboarding" });
    };
    window.addEventListener("keydown", go, { once: true });
    window.addEventListener("pointerdown", go, { once: true });
    return () => {
      window.removeEventListener("keydown", go);
      window.removeEventListener("pointerdown", go);
    };
  }, []);
  return <StubScreen id="S01" name="Horizon · Press any key" owner="Builder A" />;
}
