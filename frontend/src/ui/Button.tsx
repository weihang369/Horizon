import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import s from "./Button.module.css";
import { cx } from "./cx";
import { KeyIcon } from "./icons";
import { formatUsd } from "./CostBadge";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Cost estimate shown inside the button: number = USD (`≈ $0.04`), string = verbatim. */
  cost?: number | string;
  /** Demo mode (R15): looks enabled, shows a key glyph; the click handler should open O05. */
  keyLocked?: boolean;
  icon?: ReactNode;
  iconRight?: ReactNode;
  block?: boolean;
}

/** Slash-shaped button (spec §3.7). Text stays level; only the fill is slanted. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", cost, keyLocked, icon, iconRight, block, className, children, type = "button", ...rest },
  ref,
) {
  const costText = cost === undefined ? null : typeof cost === "number" ? `≈ ${formatUsd(cost)}` : cost;
  return (
    <button
      ref={ref}
      type={type}
      className={cx(s.btn, s[variant], s[size], block && s.block, className)}
      data-key-locked={keyLocked || undefined}
      {...rest}
    >
      <span className={s.ring} aria-hidden="true" />
      <span className={s.shape} aria-hidden="true">
        <span className={s.sweep} />
      </span>
      <span className={s.content}>
        {keyLocked && (
          <span className={s.lock} title="Needs an OpenRouter key">
            <KeyIcon />
            <span className="sr-only">(needs API key)</span>
          </span>
        )}
        {icon}
        {children}
        {iconRight}
        {costText && <span className={s.cost}>{costText}</span>}
      </span>
    </button>
  );
});

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Required accessible name. */
  label: string;
  size?: ButtonSize;
  children: ReactNode;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, size = "md", className, children, type = "button", ...rest },
  ref,
) {
  return (
    <button ref={ref} type={type} aria-label={label} title={label} className={cx(s.btn, s.icon, s[size], className)} {...rest}>
      <span className={s.ring} aria-hidden="true" />
      <span className={s.shape} aria-hidden="true">
        <span className={s.sweep} />
      </span>
      <span className={s.content}>{children}</span>
    </button>
  );
});
