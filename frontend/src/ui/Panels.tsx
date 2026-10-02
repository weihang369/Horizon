// Modal (frame), Drawer (frame), ToastView, ErrorTape, EmptyState (spec §3.7). Owner: VMD.
// Stacking, focus trap/restore and Esc routing are the EE's LayerStack; these are presentational frames.
import { useId, useMemo, type HTMLAttributes, type ReactNode } from "react";
import s from "./Panels.module.css";
import { cx } from "./cx";
import { Button, IconButton } from "./Button";
import { CheckIcon, CloseIcon, WarnIcon } from "./icons";
import { RansomText } from "./RansomText";
import { Tape, type TapeTone } from "./Tape";
import { shadowDataUrl } from "../vfx/shadow/renderShadowSvg";
import { specFromAppearance } from "../vfx/shadow/specFromAppearance";

// ── Modal ────────────────────────────────────────────────────────────────────
export interface ModalProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title: ReactNode;
  /** Small tape above the title (e.g. "CONFIRM", "COST"). */
  tape?: ReactNode;
  tapeTone?: TapeTone;
  size?: "sm" | "md" | "lg";
  tone?: "default" | "danger";
  onClose?: () => void;
  actions?: ReactNode;
  children?: ReactNode;
}

export function Modal({ title, tape, tapeTone = "brand", size = "md", tone = "default", onClose, actions, children, className, ...rest }: ModalProps) {
  const id = useId();
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={`${id}-t`}
      className={cx(s.modal, size !== "md" && s[`modal_${size}`], tone === "danger" && s.modal_danger, className)}
      {...rest}
    >
      <div className={s.modalHead}>
        <div>
          {tape && (
            <Tape tone={tone === "danger" ? "error" : tapeTone} size="sm" className={s.modalTape}>
              {tape}
            </Tape>
          )}
          <h2 id={`${id}-t`} className={s.modalTitle}>
            {title}
          </h2>
        </div>
        {onClose && (
          <IconButton label="Close" size="sm" className={s.modalClose} onClick={onClose}>
            <CloseIcon />
          </IconButton>
        )}
      </div>
      <div className={s.modalBody}>{children}</div>
      {actions && <div className={s.modalActions}>{actions}</div>}
    </div>
  );
}

// ── Drawer ───────────────────────────────────────────────────────────────────
export interface DrawerProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title: ReactNode;
  width?: number;
  onClose?: () => void;
  headerExtra?: ReactNode;
  children?: ReactNode;
}

/** Skewed right-side panel with a horizon-500 header tape (doc 04 §8). */
export function Drawer({ title, width = 400, onClose, headerExtra, children, className, style, ...rest }: DrawerProps) {
  const id = useId();
  return (
    <aside
      aria-labelledby={`${id}-t`}
      className={cx(s.drawer, className)}
      style={{ ...style, ["--drawer-w" as string]: `${width}px` }}
      {...rest}
    >
      <div className={s.drawerHead}>
        <Tape tone="brand" size="md" id={`${id}-t`}>
          {title}
        </Tape>
        {headerExtra}
        {onClose && (
          <IconButton label="Close" size="sm" className={s.drawerClose} onClick={onClose}>
            <CloseIcon />
          </IconButton>
        )}
      </div>
      <div className={s.drawerBody}>{children}</div>
    </aside>
  );
}

// ── ToastView ────────────────────────────────────────────────────────────────
export type ToastVariant = "success" | "info" | "warn" | "error";

export interface ToastViewProps {
  variant: ToastVariant;
  text: ReactNode;
  action?: { label: string; run(): void };
  onDismiss?: () => void;
}

export function ToastView({ variant, text, action, onDismiss }: ToastViewProps) {
  const icon = variant === "success" ? <CheckIcon /> : variant === "info" ? <span aria-hidden="true">i</span> : <WarnIcon />;
  return (
    <div className={cx(s.toast, s[`toast_${variant}`])} role={variant === "error" ? "alert" : "status"}>
      <span className={s.toastFlag} aria-hidden="true">
        {icon}
      </span>
      <span className={s.toastText}>{text}</span>
      {action ? (
        <button type="button" className={s.toastAction} onClick={action.run}>
          {action.label}
        </button>
      ) : (
        <span />
      )}
      {onDismiss && (
        <button type="button" className={s.toastClose} aria-label="Dismiss" onClick={onDismiss}>
          <CloseIcon width={14} height={14} />
        </button>
      )}
    </div>
  );
}

// ── ErrorTape ────────────────────────────────────────────────────────────────
export interface ErrorTapeProps {
  message: ReactNode;
  /** Error code shown in mono (e.g. `rate_limited`). */
  code?: string;
  label?: string;
  tone?: "error" | "warn";
  action?: { label: string; run(): void; cost?: number };
  className?: string;
}

/** Red "WARNING" tape + message + action (STATE-*). */
export function ErrorTape({ message, code, label, tone = "error", action, className }: ErrorTapeProps) {
  return (
    <div className={cx(s.errorTape, tone === "warn" && s.errorTape_warn, className)} role="alert">
      <Tape tone={tone} size="sm">
        {label ?? (tone === "error" ? "WARNING" : "HEADS UP")}
      </Tape>
      <span className={s.errorMsg}>
        {message}
        {code && <span className={s.errorCode}> · {code}</span>}
      </span>
      {action && (
        <Button size="sm" variant={tone === "error" ? "danger" : "secondary"} cost={action.cost} onClick={action.run}>
          {action.label}
        </Button>
      )}
    </div>
  );
}

// ── EmptyState ───────────────────────────────────────────────────────────────
export interface EmptyStateProps {
  title: string;
  body?: ReactNode;
  action?: { label: string; run(): void; keyLocked?: boolean };
  /** Custom art; defaults to an "unknown" Shadow silhouette in the current palette slot. */
  art?: ReactNode;
  paletteId?: string | null;
  className?: string;
}

export function EmptyState({ title, body, action, art, paletteId, className }: EmptyStateProps) {
  const src = useMemo(() => shadowDataUrl(specFromAppearance(null, paletteId ?? null, "neutral", "unknown")), [paletteId]);
  return (
    <div className={cx(s.empty, className)}>
      <div className={s.emptyArt} aria-hidden="true">
        {art ?? <img src={src} alt="" />}
      </div>
      <RansomText text={title} size={28} as="h3" className={s.emptyTitle} tone="mixed" />
      {body && <p className={s.emptyBody}>{body}</p>}
      {action && (
        <Button onClick={action.run} keyLocked={action.keyLocked}>
          {action.label}
        </Button>
      )}
    </div>
  );
}
