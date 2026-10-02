// O20 Keyboard shortcuts sheet (APP-10, doc 03 §6). `?` opens it (outside text fields). Owner: Builder A.
import type { ReactNode } from "react";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { Button } from "../../ui/Button";
import { Kbd } from "../../ui/Kbd";
import { Modal } from "../../ui/Panels";
import s from "./Overlays.module.css";

const k = (...keys: string[]): ReactNode => keys.map((x, i) => <span key={x}>{i > 0 && " + "}<Kbd>{x}</Kbd></span>);

const GROUPS: { title: string; rows: [ReactNode, string][] }[] = [
  {
    title: "Anywhere",
    rows: [
      [k("Esc"), "Pause menu · close the top overlay"],
      [k("?"), "This sheet"],
      [k("Ctrl", "Shift", "D"), "Mock State Switcher (UI preview)"],
    ],
  },
  {
    title: "Sessions",
    rows: [
      [k("I"), "Insight drawer"],
      [k("L"), "Backlog (full log)"],
      [k("Space"), "Pause / resume (debate, watch, replay)"],
      [k("→"), "Next turn / step"],
      [k("Alt", "1…7"), "Set the face (MANUAL) · works while typing"],
    ],
  },
  {
    title: "Composer",
    rows: [
      [k("Enter"), "Send"],
      [k("Shift", "Enter"), "New line"],
      [k("Ctrl", "Enter"), "Send (alias)"],
      [k("@"), "Mention picker"],
    ],
  },
];

export function ShortcutsSheet({ close }: OverlayComponentProps<"O20">) {
  return (
    <Modal title="Keyboard shortcuts" tape="CONTROLS" size="lg" onClose={close} actions={<Button onClick={close} autoFocus>Got it</Button>}>
      <p className={s.sheetNote}>Single keys (I, L, ?, Space, →) only fire when you're not typing in a field.</p>
      <div className={s.sheet}>
        {GROUPS.map((g) => (
          <section key={g.title} className={s.sheetGroup} aria-label={g.title}>
            <h3 className={s.sheetTitle}>{g.title}</h3>
            <dl className={s.sheetList}>
              {g.rows.map(([keys, what], i) => (
                <div key={i} className={s.sheetRow}>
                  <dt>{keys}</dt>
                  <dd>{what}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
    </Modal>
  );
}
