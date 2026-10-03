// Local form pieces the kit doesn't have: a chip-list editor (traits, quirks, boundaries…) and a section frame.
// Owner: Builder B.
import { useId, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { cx } from "@/ui/cx";
import s from "./steps/steps.module.css";

export interface TagInputProps {
  label: string;
  value: string[];
  onChange: (v: string[]) => void;
  max?: number;
  min?: number;
  placeholder?: string;
  error?: string | null;
  edited?: boolean;
  hint?: ReactNode;
  /** Long items (boundaries, example lines) render as rows instead of chips. */
  rows?: boolean;
}

export function TagInput({ label, value, onChange, max = 12, min, placeholder = "Add…", error, edited, hint, rows }: TagInputProps) {
  const id = useId();
  const [draft, setDraft] = useState("");
  const full = value.length >= max;
  const commit = (text: string) => {
    const v = text.trim();
    setDraft("");
    if (!v || full || value.includes(v)) return;
    onChange([...value, v]);
  };
  const add = () => commit(draft);
  return (
    <div className={s.tagField}>
      <div className={s.tagHead}>
        <label htmlFor={id} className={s.fieldLabel}>{label}</label>
        {edited && <span className={s.editedDot} role="img" aria-label="edited" title="Edited by you" />}
        <span className={cx(s.tagCount, (min !== undefined && value.length > 0 && value.length < min) || value.length > max ? s.tagCountBad : undefined)}>
          {value.length}{min !== undefined ? ` · ${min}–${max}` : `/${max}`}
        </span>
      </div>
      <div className={cx(s.tagBox, rows && s.tagRows, error && s.tagInvalid)}>
        {value.map((t, i) => (
          <span key={`${t}-${i}`} className={cx(s.tag, rows && s.tagRow)}>
            <span className={s.tagText}>{t}</span>
            <button type="button" className={s.tagX} aria-label={`Remove ${t}`} onClick={() => onChange(value.filter((_, j) => j !== i))}>×</button>
          </span>
        ))}
        {!full && (
          <input
            id={id}
            className={s.tagInput}
            value={draft}
            placeholder={placeholder}
            onChange={(e) => {
              const v = e.target.value;
              if (!rows && v.endsWith(",")) commit(v.slice(0, -1));
              else setDraft(v);
            }}
            onBlur={add}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              } else if (e.key === "Backspace" && !draft && value.length) {
                onChange(value.slice(0, -1));
              }
            }}
          />
        )}
      </div>
      {error ? <div className={s.fieldError} role="alert">{error}</div> : hint ? <div className={s.fieldHint}>{hint}</div> : null}
    </div>
  );
}

export function Section({ title, kicker, children, className, index = 0, wide }: { title: string; kicker?: string; children: ReactNode; className?: string; index?: number; wide?: boolean }) {
  return (
    <section className={cx(s.section, wide && s.sectionWide, className)} style={{ "--i": index } as CSSProperties} aria-label={title}>
      <header className={s.sectionHead}>
        <h2 className={s.sectionTitle}>{title}</h2>
        {kicker && <span className={s.sectionKicker}>{kicker}</span>}
      </header>
      <div className={s.sectionBody}>{children}</div>
    </section>
  );
}
