// Wizard action bar (UXA §2.2, 80 px): ◂ Back · save state · estimate + primary on the right. Owner: Builder B.
import type { ReactNode } from "react";
import type { CreationStep } from "@/contract/types";
import { CREATION_STEPS } from "@/contract/types";
import { Button } from "@/ui";
import { useWizard } from "./context";
import s from "./wizard.module.css";

export function ActionBar({ children, backTo, backLabel, note }: { children?: ReactNode; backTo?: CreationStep | "exit" | null; backLabel?: string; note?: ReactNode }) {
  const { step, goStep, exit, work, character, edit, save } = useWizard();
  const i = CREATION_STEPS.indexOf(step);
  const prev = backTo === undefined ? (i > 1 || (i === 1 && !character) ? CREATION_STEPS[i - 1] : "exit") : backTo;
  return (
    <footer className={s.bar}>
      <div className={s.barLeft}>
        {prev && (
          <Button variant="ghost" onClick={() => (prev === "exit" ? exit() : void goStep(prev))}>
            ◂ {backLabel ?? (prev === "exit" ? (edit ? "Profile" : "Hub") : "Back")}
          </Button>
        )}
        {character && (
          <span className={s.saveState} data-dirty={work.dirty || undefined} aria-live="polite">
            {work.dirty ? "● Unsaved edits" : edit ? "✓ All changes saved" : "✓ Draft saved"}
          </span>
        )}
        {character && work.dirty && (
          <Button variant="secondary" size="sm" onClick={() => void save()}>{edit ? "Save" : "Save draft"}</Button>
        )}
      </div>
      {note && <div className={s.barNote}>{note}</div>}
      <div className={s.barRight}>{children}</div>
    </footer>
  );
}
