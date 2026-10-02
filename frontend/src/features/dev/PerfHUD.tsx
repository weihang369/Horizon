// PerfHUD (R20, EE paper §2.9): fps, dropped frames, long tasks, React commits. Ctrl+Shift+P, dev builds only. Owner: EE.
import { Profiler, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { onTick } from "../../vfx/ticker";
import s from "./dev.module.css";

let commits = 0;
/** Wrap the app root to count React commits (dev only). */
export function CommitCounter({ children }: { children: ReactNode }) {
  if (!import.meta.env.DEV) return <>{children}</>;
  return <Profiler id="app" onRender={() => { commits++; }}>{children}</Profiler>;
}

export function PerfHUD() {
  const [text, setText] = useState("");
  const [bad, setBad] = useState(false);
  const stats = useRef({ frames: 0, dropped: 0, long: 0, longMax: 0, lastCommits: commits, since: performance.now() });
  useEffect(() => {
    let obs: PerformanceObserver | null = null;
    try {
      obs = new PerformanceObserver((list) => {
        for (const e of list.getEntries()) {
          stats.current.long++;
          stats.current.longMax = Math.max(stats.current.longMax, e.duration);
        }
      });
      obs.observe({ type: "longtask", buffered: false });
    } catch { /* longtask unsupported */ }
    const stop = onTick((dt, now) => {
      const st = stats.current;
      st.frames++;
      if (dt > 25) st.dropped++;
      if (now - st.since >= 1000) {
        const secs = (now - st.since) / 1000;
        const fps = st.frames / secs;
        const dropPct = (st.dropped / Math.max(1, st.frames)) * 100;
        const c = commits - st.lastCommits;
        setText(`fps ${fps.toFixed(0)}  dropped ${dropPct.toFixed(1)}%\nlongtasks ${st.long} (max ${st.longMax.toFixed(0)} ms)\ncommits/s ${c}`);
        setBad(fps < 55 || dropPct > 2 || st.longMax > 50);
        Object.assign(st, { frames: 0, dropped: 0, long: 0, longMax: 0, lastCommits: commits, since: now });
      }
    });
    return () => {
      stop();
      obs?.disconnect();
    };
  }, []);
  return <div className={`${s.hud} ${bad ? s.bad : ""}`} aria-hidden="true">{text || "PerfHUD…"}</div>;
}
