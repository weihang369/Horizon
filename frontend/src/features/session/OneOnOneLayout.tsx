// S07 1:1 layout (UXA §2.2, doc 03 §5, R14). Stage column 600 / 520 with the hero card bleeding off the bottom,
// name plate at y = 96 over the card's left edge (the right carries the thinking bubble) with the 10 px energy bar under it; log column 840 / 760 with an
// 8° diagonal left cut overlapping the stage by ~120 px; the composer lives inside the log column.
// Insight (O08) compresses the STAGE, never the log: stage 440 / 360, log ≥ 520 (R14).
import { useMemo, type CSSProperties } from "react";
import { openOverlay } from "../../app/layers";
import { useEnergy, useNow, useRushHour, useSettings } from "../../client/hooks";
import { NamePlate } from "../../character/NamePlate";
import { PortraitCard } from "../../character/PortraitCard";
import { EnergyBar } from "../../character/EnergyBar";
import { EMOTIONS } from "../../contract/types";
import { EST_REPLY_POINTS } from "../../domain/energy";
import { formatDuration, formatUsd } from "../../domain/format";
import { Tape } from "../../ui/Tape";
import { Tooltip } from "../../ui/Data";
import { cx } from "../../ui/cx";
import { EmotionStrip } from "./EmotionPicker";
import { SessionLog } from "./SessionLog";
import { firstName, useChar, useSessionCtx } from "./sessionContext";
import type { LayoutProps } from "./registry";
import s from "./OneOnOneLayout.module.css";

export function OneOnOneLayout({ rt, dock, insightOpen }: LayoutProps) {
  const ctx = useSessionCtx();
  const p = rt.participants[0];
  const c = useChar(p?.characterId);
  const energy = useEnergy(p?.characterId);
  const now = useNow(30_000);
  const rush = useRushHour();
  const settings = useSettings().data;
  const live = !!ctx && !ctx.replay && !ctx.isSeed;
  const manual = rt.session?.emotionMode === "user";
  const streaming = !!rt.streamingId;
  const asleep = energy?.state === "exhausted";

  const available = useMemo(() => {
    if (!c) return undefined;
    return Object.fromEntries(EMOTIONS.map((e) => [e, !!c.emotions[e]]));
  }, [c]);

  const usdPer = settings?.energy.usdPerPoint ?? 0.0001;
  const tip = energy
    ? `⚡ ${Math.floor(energy.current)} / ${energy.max} · ≈ US${formatUsd(energy.current * usdPer)} left today${energy.fullAt && energy.current < energy.max ? ` · full in ${formatDuration(Date.parse(energy.fullAt) - now)}` : ""}`
    : "";
  const backIn = energy && asleep
    ? formatDuration(((EST_REPLY_POINTS[rush.peak ? "peak" : "off_peak"] - energy.current) / Math.max(1, energy.max / 24)) * 3_600_000)
    : "";
  const topUp = p ? () => (ctx?.demo ? openOverlay("O05", { reason: "Topping up energy needs your OpenRouter key." }) : openOverlay("O27", { characterId: p.characterId, sessionId: rt.session?.id })) : undefined;

  return (
    <div className={cx(s.oo, insightOpen && s.pushed)}>
      <section className={s.stage} aria-label="Stage">
        <div className={s.band} aria-hidden="true" />
        <div className={s.halftone} aria-hidden="true" />
        {c && p && (
          <>
            <div className={cx(s.card, p.leanIn && s.leanIn)}>
              <PortraitCard
                character={c}
                emotion={p.displayEmotion}
                size="hero"
                width="var(--card-w)"
                speaking={streaming}
                energyState={energy?.state}
                parallax
              />
            </div>
            <div className={s.plate}>
              <NamePlate
                character={c}
                size="lg"
                subtitle={asleep ? `Exhausted · back in ${backIn}` : c.profile.role}
              />
              <div className={s.energyRow}>
                <Tooltip content={tip} placement="bottom">
                  <span className={s.energyWrap} tabIndex={0}>
                    <EnergyBar characterId={c.id} energy={c.energy} size="chat" showLabel label={firstName(c.profile.name)} onTopUp={live ? topUp : undefined} />
                  </span>
                </Tooltip>
                {rush.peak && <Tape tone="brand" size="sm">Rush hour · 2× ⚡</Tape>}
              </div>
            </div>
          </>
        )}
      </section>
      {c && p && manual && live && (
        <div className={s.strip}>
          <span className={s.stripTag}>Manual</span>
          <EmotionStrip sessionId={rt.session!.id} characterId={c.id} current={p.displayEmotion} available={available} />
        </div>
      )}
      <section className={s.logCol} aria-label="Conversation">
        <div className={s.cutEdge} aria-hidden="true" />
        <div className={s.panel} style={{ "--log-pad": dock ? "0px" : "16px" } as CSSProperties}>
          <SessionLog rt={rt} className={s.log} />
          {dock && <div className={s.dock}>{dock}</div>}
        </div>
      </section>
    </div>
  );
}
