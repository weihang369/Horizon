import type { ReactNode } from "react";
import s from "./Tags.module.css";

/** Keycap. `<Kbd>Ctrl</Kbd>+<Kbd>Shift</Kbd>` */
export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className={s.kbd}>{children}</kbd>;
}
