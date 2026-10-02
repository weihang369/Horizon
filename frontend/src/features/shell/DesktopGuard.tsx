// O19 Desktop guard (APP-06): below 1280×720 a stylised, undismissable notice. No mobile layout is built.
// Owner: Builder A. Statically imported by App (entry bundle): keep it light.
import { useEffect, useState } from "react";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { RansomText } from "../../ui/RansomText";
import s from "./DesktopGuard.module.css";

export function DesktopGuard(_: Partial<OverlayComponentProps<"O19">>) {
  const [size, setSize] = useState(() => ({ w: window.innerWidth, h: window.innerHeight }));
  useEffect(() => {
    const on = () => setSize({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return (
    <div role="alertdialog" aria-modal="true" aria-labelledby="guard-t" aria-describedby="guard-d" className={s.guard}>
      <div className={s.band} aria-hidden="true" />
      <div className={s.inner}>
        <h2 id="guard-t" className={s.title}><RansomText text="DESKTOP ONLY" size="min(64px, 11vw)" tone="mixed" /></h2>
        <p id="guard-d" className={s.copy}>Horizon is designed for desktop (≥ 1280×720).</p>
        <p className={s.size}>
          <span data-bad={size.w < 1280 || undefined}>{size.w}</span> × <span data-bad={size.h < 720 || undefined}>{size.h}</span>
          <span className={s.need}> · need 1280 × 720</span>
        </p>
        <p className={s.tip}>Widen the window or zoom out (Ctrl −).</p>
      </div>
    </div>
  );
}
