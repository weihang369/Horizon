// S03 World Select: foundation stub (Builder A replaces it). Owner: EE (stub).
import { useWorlds } from "../../client/hooks";
import { navigate } from "../../router";
import { Button } from "../../ui/Button";
import { openOverlay } from "../../app/layers";
import { StubScreen } from "../../app/stubs";
import s from "../../app/App.module.css";

export function WorldSelectScreen() {
  const { data: worlds, loading, error } = useWorlds();
  return (
    <StubScreen id="S03" name="Worlds" owner="Builder A">
      {loading && <p>Loading…</p>}
      {error && <p role="alert">{error.message}</p>}
      <ul className={s.stubList}>
        {worlds?.map((w) => (
          <li key={w.id}>
            <Button onClick={(e) => navigate({ name: "hub", worldId: w.id }, { transition: "shatter", sourceEl: e.currentTarget, origin: { x: e.clientX, y: e.clientY } })}>
              {w.name} · {w.characterCount}
            </Button>
          </li>
        ))}
        {worlds?.length === 0 && <li>No worlds yet.</li>}
      </ul>
      <Button variant="secondary" onClick={() => openOverlay("O02", {})}>+ New World</Button>
    </StubScreen>
  );
}
