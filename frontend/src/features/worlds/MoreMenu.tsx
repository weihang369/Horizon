// "⋯" button + skewed Menu (world header, history rows). Owner: Builder A.
import { useId, useRef, useState } from "react";
import { IconButton } from "../../ui/Button";
import { Menu } from "../../ui/Fields";
import type { MenuItem } from "../../ui/Fields";
import { MoreIcon } from "../../ui/icons";
import s from "./Hub.module.css";

export function MoreMenu<V extends string>({ label, items, onSelect, align = "right", size = "md" }: {
  label: string; items: MenuItem<V>[]; onSelect: (id: V) => void; align?: "left" | "right"; size?: "sm" | "md";
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const btn = useRef<HTMLButtonElement>(null);
  const close = () => {
    setOpen(false);
    btn.current?.focus();
  };
  return (
    <span className={s.more}>
      <IconButton ref={btn} label={label} size={size} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => setOpen((o) => !o)}>
        <MoreIcon />
      </IconButton>
      <Menu
        id={id}
        open={open}
        items={items}
        label={label}
        align={align}
        onClose={close}
        onSelect={(v) => {
          setOpen(false);
          onSelect(v);
        }}
      />
    </span>
  );
}
