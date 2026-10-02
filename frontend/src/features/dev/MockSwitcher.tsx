// O18 Mock State Switcher (APP-08): Ctrl+Shift+D. Drives every scenario in mock/scenarios, demo speed, a mock key
// and Reset demo data. Hidden in Presenter Mode. Owner: EE.
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { toast } from "../../app/layers";
import { mockActions, useMock } from "../../stores/mock";
import { SCENARIOS } from "../../mock/scenarios";
import type { Scenario } from "../../mock/scenarios";
import { DEMO_SPEEDS } from "../../mock/timing.config";
import { Button } from "../../ui/Button";
import { Drawer } from "../../ui/Panels";
import s from "./dev.module.css";

const GROUPS = [...new Set(SCENARIOS.map((x) => x.group))];

export function MockSwitcher({ close }: OverlayComponentProps<"O18">) {
  const { scenario, speed, available, ready } = useMock((m) => m);
  const apply = async (sc: Scenario) => {
    await mockActions.setScenario(sc.id);
    toast({ variant: "info", text: `Scenario: ${sc.label}` });
  };
  return (
    <Drawer title="O18 · MOCK STATE" width={380} onClose={close} data-dev="" className={s.panel}>
      {!available && <p className={s.note}>The HttpClient is active: no mock controls.</p>}
      {available && (
        <>
          <section className={s.row} aria-label="Demo speed">
            <span className={s.label}>Demo speed</span>
            {DEMO_SPEEDS.map((x) => (
              <Button key={x} size="sm" variant={speed === x ? "primary" : "ghost"} onClick={() => mockActions.setSpeed(x)}>×{x}</Button>
            ))}
          </section>
          <section className={s.row}>
            <Button size="sm" variant="secondary" onClick={async () => { await mockActions.setMockKey(); toast({ variant: "success", text: "Mock key set (sk-or-mock…)." }); }}>Set mock key</Button>
            <Button size="sm" variant="danger" onClick={async () => { await mockActions.resetDemoData(); toast({ variant: "info", text: "Demo data reset." }); }}>Reset demo data</Button>
          </section>
          {!ready && <p className={s.note}>Loading seed data…</p>}
          {GROUPS.map((g) => (
            <section key={g} aria-label={g}>
              <h3 className={s.group}>{g}</h3>
              <ul className={s.list}>
                {SCENARIOS.filter((x) => x.group === g).map((x) => (
                  <li key={x.id}>
                    <button type="button" className={s.item} aria-pressed={scenario === x.id} onClick={() => void apply(x)}>
                      <strong>{x.label}</strong>
                      <span>{x.hint}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </>
      )}
    </Drawer>
  );
}
