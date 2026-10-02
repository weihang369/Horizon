// S04 World Hub (+ S13 Sessions tab): foundation stub (Builder A replaces it). Owner: EE (stub).
import { useCharacters, useSessions, useWorld } from "../../client/hooks";
import type { Route } from "../../router";
import { navigate } from "../../router";
import { Button } from "../../ui/Button";
import { StubScreen } from "../../app/stubs";
import s from "../../app/App.module.css";

export function WorldHubScreen({ route }: { route: Extract<Route, { name: "hub" }> }) {
  const { worldId } = route;
  const world = useWorld(worldId).data;
  const chars = useCharacters(worldId, { includeArchived: true }).data;
  const sessions = useSessions(worldId).data;
  const tab = route.tab ?? "roster";
  return (
    <StubScreen
      id="S04"
      name={world?.name ?? "World Hub"}
      owner="Builder A"
      links={[
        { label: "Roster", to: { name: "hub", worldId, tab: "roster" } },
        { label: "Sessions (S13)", to: { name: "hub", worldId, tab: "sessions" } },
        { label: "+ New Character", to: { name: "wizard", worldId } },
        { label: "Start Session", to: { name: "setup", worldId } },
      ]}
    >
      <ul className={s.stubList}>
        {tab === "roster" && chars?.map((c) => (
          <li key={c.id}>
            <Button variant="ghost" size="sm" onClick={() => navigate({ name: "profile", worldId, characterId: c.id })}>
              {c.profile.name || "(draft)"} · {c.status}
            </Button>
          </li>
        ))}
        {tab === "sessions" && sessions?.map((x) => (
          <li key={x.id}>
            <Button variant="ghost" size="sm" onClick={() => navigate({ name: "session", worldId, sessionId: x.id, replay: true })}>
              ▶ {x.title} · {x.mode} · {x.status}
            </Button>
          </li>
        ))}
      </ul>
    </StubScreen>
  );
}
