// Settings layout atoms: a titled section and a label/control row. Owner: Builder A.
import { useCallback, useState } from "react";
import type { ReactNode } from "react";
import { toast } from "../../app/layers";
import { client } from "../../client";
import type { DeepPartial } from "../../client/HorizonClient";
import type { HorizonErrorShape } from "../../contract/errors";
import type { AppSettings } from "../../contract/types";
import s from "./Settings.module.css";

export function Section({ title, desc, children, aside }: { title: string; desc?: ReactNode; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className={s.section} aria-label={title}>
      <header className={s.sectionHead}>
        <h3 className={s.sectionTitle}>{title}</h3>
        {aside}
      </header>
      {desc && <p className={s.sectionDesc}>{desc}</p>}
      <div className={s.sectionBody}>{children}</div>
    </section>
  );
}

export function Row({ label, desc, children, htmlFor }: { label: ReactNode; desc?: ReactNode; children: ReactNode; htmlFor?: string }) {
  return (
    <div className={s.row}>
      <div className={s.rowText}>
        {htmlFor ? <label htmlFor={htmlFor} className={s.rowLabel}>{label}</label> : <span className={s.rowLabel}>{label}</span>}
        {desc && <span className={s.rowDesc}>{desc}</span>}
      </div>
      <div className={s.rowControl}>{children}</div>
    </div>
  );
}

/** Persist a settings patch through the client (entity.changed refreshes useSettings). */
export function useSettingsPatch(): { save: (patch: DeepPartial<AppSettings>, ok?: string) => Promise<void>; saving: boolean } {
  const [saving, setSaving] = useState(false);
  const save = useCallback(async (patch: DeepPartial<AppSettings>, ok?: string) => {
    setSaving(true);
    try {
      await client.settings.update(patch);
      if (ok) toast({ variant: "success", text: ok });
    } catch (e) {
      toast({ variant: "error", text: (e as HorizonErrorShape)?.message ?? "Couldn't save that setting." });
    } finally {
      setSaving(false);
    }
  }, []);
  return { save, saving };
}
