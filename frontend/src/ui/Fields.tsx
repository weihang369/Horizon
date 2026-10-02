// TextField, TextArea, Select, Menu (spec §3.7). Owner: VMD.
import {
  forwardRef, useEffect, useId, useRef, useState,
  type InputHTMLAttributes, type KeyboardEvent, type ReactNode, type TextareaHTMLAttributes,
} from "react";
import s from "./Fields.module.css";
import { cx } from "./cx";
import { ChevronDownIcon, RegenIcon, WarnIcon } from "./icons";

interface FieldChrome {
  label: string;
  hideLabel?: boolean;
  hint?: ReactNode;
  error?: string | null;
  /** The "edited" dot (CHR-04: fields the user changed vs the AI draft). */
  edited?: boolean;
  /** Show a counter against maxLength (or `counterMax` for soft limits). */
  counter?: boolean;
  counterMax?: number;
  /** ↻ regenerate slot (AI field regeneration). */
  onRegenerate?: () => void;
  regenerateLabel?: string;
}

function Chrome({
  id, chrome, length, max, children,
}: { id: string; chrome: FieldChrome; length: number; max?: number; children: ReactNode }) {
  const limit = chrome.counterMax ?? max;
  return (
    <div className={s.field}>
      <div className={cx(s.labelRow, chrome.hideLabel && "sr-only")}>
        <label htmlFor={id} className={s.label}>
          {chrome.label}
        </label>
        {chrome.edited && <span className={s.edited} title="Edited by you" aria-label="edited" role="img" />}
        {chrome.counter && limit !== undefined && (
          <span className={cx(s.counter, length > limit && s.counterOver)} aria-live="polite">
            {length}/{limit}
          </span>
        )}
      </div>
      <div className={cx(s.box, chrome.error && s.invalid)}>
        {children}
        {chrome.onRegenerate && (
          <span className={s.slot}>
            <button type="button" className={s.regen} onClick={chrome.onRegenerate} aria-label={chrome.regenerateLabel ?? `Regenerate ${chrome.label}`}>
              <RegenIcon width={14} height={14} />
              <span aria-hidden="true">Regen</span>
            </button>
          </span>
        )}
      </div>
      {chrome.error ? (
        <div className={s.error} id={`${id}-err`} role="alert">
          <WarnIcon width={14} height={14} />
          {chrome.error}
        </div>
      ) : chrome.hint ? (
        <div className={s.hint} id={`${id}-hint`}>
          {chrome.hint}
        </div>
      ) : null}
    </div>
  );
}

export type TextFieldProps = FieldChrome & Omit<InputHTMLAttributes<HTMLInputElement>, "children">;

export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(props, ref) {
  const { label, hideLabel, hint, error, edited, counter, counterMax, onRegenerate, regenerateLabel, id: idProp, className, ...rest } = props;
  const auto = useId();
  const id = idProp ?? auto;
  const length = String(rest.value ?? rest.defaultValue ?? "").length;
  return (
    <Chrome id={id} length={length} max={rest.maxLength} chrome={{ label, hideLabel, hint, error, edited, counter, counterMax, onRegenerate, regenerateLabel }}>
      <input
        ref={ref}
        id={id}
        className={cx(s.input, className)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-err` : hint ? `${id}-hint` : undefined}
        {...rest}
      />
    </Chrome>
  );
});

export type TextAreaProps = FieldChrome & Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "children">;

export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(function TextArea(props, ref) {
  const { label, hideLabel, hint, error, edited, counter, counterMax, onRegenerate, regenerateLabel, id: idProp, className, ...rest } = props;
  const auto = useId();
  const id = idProp ?? auto;
  const length = String(rest.value ?? rest.defaultValue ?? "").length;
  return (
    <Chrome id={id} length={length} max={rest.maxLength} chrome={{ label, hideLabel, hint, error, edited, counter, counterMax, onRegenerate, regenerateLabel }}>
      <textarea
        ref={ref}
        id={id}
        className={cx(s.textarea, className)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-err` : hint ? `${id}-hint` : undefined}
        {...rest}
      />
    </Chrome>
  );
});

// ── Menu ─────────────────────────────────────────────────────────────────────
export interface MenuItem<V extends string = string> {
  id: V;
  label: ReactNode;
  icon?: ReactNode;
  hint?: ReactNode;
  danger?: boolean;
  disabled?: boolean;
  /** Draw a divider before this item. */
  divider?: boolean;
}

export interface MenuProps<V extends string> {
  open: boolean;
  items: MenuItem<V>[];
  onSelect: (id: V) => void;
  onClose: () => void;
  /** Accessible name (or use labelledBy). */
  label?: string;
  labelledBy?: string;
  /** "menu" (actions) or "listbox" (Select). */
  role?: "menu" | "listbox";
  selectedId?: V | null;
  align?: "left" | "right";
  id?: string;
  className?: string;
}

/**
 * Skewed popover menu, positioned absolutely under its (position: relative) parent.
 * Arrow keys / Home / End / Enter; Esc and outside click close it (Esc handled locally, R4 popover-first).
 */
export function Menu<V extends string>({
  open, items, onSelect, onClose, label, labelledBy, role = "menu", selectedId, align = "left", id, className,
}: MenuProps<V>) {
  const ref = useRef<HTMLUListElement>(null);
  const enabled = items.filter((i) => !i.disabled);
  const initial = Math.max(0, enabled.findIndex((i) => i.id === selectedId));
  const [active, setActive] = useState(initial);

  useEffect(() => {
    if (!open) return;
    setActive(initial);
    ref.current?.focus();
    const onDoc = (e: PointerEvent) => {
      const host = ref.current?.parentElement;
      if (host && !host.contains(e.target as Node)) onClose();
    };
    document.addEventListener("pointerdown", onDoc, true);
    return () => document.removeEventListener("pointerdown", onDoc, true);
  }, [open]);

  if (!open) return null;
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % enabled.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a - 1 + enabled.length) % enabled.length);
    } else if (e.key === "Home") {
      e.preventDefault();
      setActive(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActive(enabled.length - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const it = enabled[active];
      if (it) onSelect(it.id);
    } else if (e.key === "Tab") {
      onClose();
    }
  };
  const activeId = enabled[active] ? `${id ?? "menu"}-${enabled[active].id}` : undefined;
  return (
    <ul
      ref={ref}
      id={id}
      role={role}
      tabIndex={-1}
      aria-label={label}
      aria-labelledby={labelledBy}
      aria-activedescendant={activeId}
      className={cx(s.menu, align === "right" && s.menuRight, className)}
      onKeyDown={onKey}
    >
      {items.map((it) => {
        const itemRole = role === "menu" ? "menuitem" : "option";
        const isActive = enabled[active]?.id === it.id;
        return [
          it.divider ? <li key={`${it.id}-div`} role="separator" className={s.divider} /> : null,
          <li
            key={it.id}
            id={`${id ?? "menu"}-${it.id}`}
            role={itemRole}
            aria-disabled={it.disabled || undefined}
            aria-selected={role === "listbox" ? it.id === selectedId : undefined}
            data-active={isActive || undefined}
            className={cx(s.item, it.danger && s.itemDanger)}
            onPointerEnter={() => {
              const i = enabled.indexOf(it);
              if (i >= 0) setActive(i);
            }}
            onClick={() => !it.disabled && onSelect(it.id)}
          >
            {it.icon}
            <span>{it.label}</span>
            {it.hint && <span className={s.itemHint}>{it.hint}</span>}
          </li>,
        ];
      })}
    </ul>
  );
}

// ── Select ───────────────────────────────────────────────────────────────────
export interface SelectProps<V extends string> {
  label: string;
  hideLabel?: boolean;
  value: V | null;
  options: { value: V; label: ReactNode; hint?: ReactNode; disabled?: boolean }[];
  onChange: (v: V) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export function Select<V extends string>({ label, hideLabel, value, options, onChange, placeholder = "Choose…", disabled, className }: SelectProps<V>) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const btn = useRef<HTMLButtonElement>(null);
  const current = options.find((o) => o.value === value);
  return (
    <div className={cx(s.selectWrap, className)}>
      <span id={`${id}-l`} className={cx(s.label, hideLabel && "sr-only")}>
        {label}
      </span>
      <button
        ref={btn}
        type="button"
        className={s.trigger}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-labelledby={`${id}-l ${id}-v`}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span id={`${id}-v`}>{current?.label ?? placeholder}</span>
        <ChevronDownIcon />
      </button>
      <Menu
        id={`${id}-m`}
        role="listbox"
        open={open}
        labelledBy={`${id}-l`}
        selectedId={value}
        items={options.map((o) => ({ id: o.value, label: o.label, hint: o.hint, disabled: o.disabled }))}
        onSelect={(v) => {
          onChange(v);
          setOpen(false);
          btn.current?.focus();
        }}
        onClose={() => {
          setOpen(false);
          btn.current?.focus();
        }}
      />
    </div>
  );
}
