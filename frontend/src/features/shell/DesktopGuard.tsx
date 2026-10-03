// O19 Desktop guard (APP-06): below 1280×720 a stylised, undismissable notice. No mobile layout is built.
// On phones and tablets (coarse pointer) "widen the window" is no advice: show what they're missing (the share image)
// and hand them the link to open on a laptop. Owner: Builder A. Statically imported by App (entry bundle): keep it light.
import { useEffect, useState } from "react";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { RansomText } from "../../ui/RansomText";
import s from "./DesktopGuard.module.css";

const REPO_URL = "https://github.com/weihang369/Horizon";
const touch = () => typeof matchMedia !== "undefined" && matchMedia("(pointer: coarse)").matches;

export function DesktopGuard(_: Partial<OverlayComponentProps<"O19">>) {
  const [size, setSize] = useState(() => ({ w: window.innerWidth, h: window.innerHeight }));
  const [phone] = useState(touch);
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      setCopied(true);
    } catch { /* clipboard blocked: the URL bar still has it */ }
  };
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
        {phone ? (
          <>
            <img className={s.preview} src={`${import.meta.env.BASE_URL}og.jpg`} width={1200} height={627} alt="Three AI characters debating a four-day work week, with cited sources under each argument." />
            <p id="guard-d" className={s.copy}>AI characters that debate, cite their sources and live their lives. Built for a laptop or desktop screen.</p>
            <div className={s.actions}>
              <button type="button" className={s.primary} onClick={() => void copy()}>{copied ? "Link copied ✓" : "Copy link"}</button>
              <a className={s.secondary} href={REPO_URL} target="_blank" rel="noreferrer">View on GitHub</a>
            </div>
            <p className={s.tip}>Open the link on a computer (1280 × 720 or larger).</p>
          </>
        ) : (
          <>
            <p id="guard-d" className={s.copy}>Horizon is designed for desktop (≥ 1280×720).</p>
            <p className={s.size}>
              <span data-bad={size.w < 1280 || undefined}>{size.w}</span> × <span data-bad={size.h < 720 || undefined}>{size.h}</span>
              <span className={s.need}> · need 1280 × 720</span>
            </p>
            <p className={s.tip}>Widen the window or zoom out (Ctrl −).</p>
          </>
        )}
      </div>
    </div>
  );
}
