// S09 Group layout (R14, D-53) — Builder D. Wings of portraits on both sides of a full-height centred log.
// Log 640/560 between the NEXT strip (40) and the dock; wings 400/360, bottom-anchored portraits ≥ 38 % vh,
// overlapping ≤ 45 %; a 5th seat stacks behind at 0.8. Speaker: scale 1.08 + 24 px toward centre (MULTI-02 AC2).
// The NEXT strip carries the responder policy, "Everyone answer" and "Next ▸" (MULTI-03, MULTI-16).
import { useMemo } from "react";
import type { CSSProperties } from "react";
import { client } from "../../client";
import type { GroupConfig } from "../../contract/types";
import { run } from "../../app/errors";
import { EnergyBar, NamePlate, PortraitCard } from "../../character";
import { PaletteScope } from "../../theme";
import { Button, Select, cx } from "../../ui";
import { SessionLog } from "../session/SessionLog";
import type { LayoutProps } from "../session/registry";
import { StageCard } from "./StageCard";
import { activeSpeakerId, firstName, latestReactions, lastSpeakerId, splitWings, useCharMap } from "./shared";
import s from "./GroupLayout.module.css";

const POLICY: { value: GroupConfig["responderPolicy"]; label: string; hint: string }[] = [
  { value: "auto", label: "Auto", hint: "The AI picks up to 2" },
  { value: "everyone", label: "Everyone", hint: "All of them reply" },
  { value: "mentioned", label: "Mentioned only", hint: "Only @mentions reply" },
];

export function GroupLayout({ rt, replay }: LayoutProps) {
  const chars = useCharMap();
  const session = rt.session!;
  const cfg = session.config as GroupConfig | null;
  const ids = rt.participants.map((p) => p.characterId);
  const { left, right } = useMemo(() => splitWings(ids), [ids.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
  const active = activeSpeakerId(rt);
  const bandId = active ?? lastSpeakerId(rt.list);
  const reactions = useMemo(() => latestReactions(rt.list), [rt.list]);
  const byId = useMemo(() => Object.fromEntries(rt.participants.map((p) => [p.characterId, p])), [rt.participants]);
  const next = rt.nextSpeakerId;
  const nextChar = next ? chars[next] : undefined;
  const busy = !!rt.streamingId || !!rt.thinkingId;
  const live = !replay && session.status !== "ended";

  const wing = (side: "left" | "right", list: string[]) => (
    <section className={cx(s.wing, s[side])} aria-label={side === "left" ? "Cast, left wing" : "Cast, right wing"} data-stage-root="">
      {list.map((cid, i) => {
        const c = chars[cid];
        const p = byId[cid];
        if (!c || !p) return null;
        const speaking = active === cid;
        const energy = rt.energyById[cid]?.state ?? c.energy.state;
        const back = i >= 2;
        return (
          <div
            key={cid}
            className={cx(s.seat, speaking && s.speaking, p.leanIn && s.lean, back && s.back)}
            data-i={i}
            style={{ "--i": i, "--n": Math.min(list.length, 2) } as CSSProperties}
          >
            {next === cid && !speaking && <span className={s.upNext} aria-hidden="true">Next</span>}
            <StageCard
              sessionId={session.id}
              character={c}
              emotion={p.displayEmotion}
              size="stage"
              width="var(--seat-w)"
              speaking={speaking}
              listening={!!active && !speaking}
              dimmed={p.mutedByUser}
              energyState={energy}
              reaction={reactions[cid] ?? null}
            />
            <div className={s.foot}>
              <NamePlate
                character={c}
                size="sm"
                subtitle={p.mutedByUser ? "Muted" : energy === "exhausted" ? "Asleep · ⚡0" : energy === "tired" ? "Tired" : null}
              />
              <EnergyBar characterId={cid} size="stage" label={c.profile.name} className={s.energy} />
            </div>
          </div>
        );
      })}
    </section>
  );

  return (
    <div className={s.root} data-layout="group">
      <div className={s.bands} aria-hidden="true">
        {rt.participants.map((p) => (
          <PaletteScope
            key={p.characterId}
            paletteId={chars[p.characterId]?.paletteId}
            className={cx(s.band, bandId === p.characterId && s.bandOn, active === p.characterId && s.bandHot)}
          />
        ))}
      </div>

      <div className={s.strip}>
        <div className={s.nextChip} aria-live="polite" aria-atomic="true">
          <span className={s.nextLabel}>Next ▸</span>
          {nextChar ? (
            <>
              <PortraitCard character={nextChar} emotion={byId[nextChar.id]?.displayEmotion ?? "neutral"} size="head" width={24} />
              <span className={s.nextName}>{firstName(nextChar)}</span>
            </>
          ) : (
            <span className={s.nextName}>{busy ? "…" : "Your turn"}</span>
          )}
        </div>
        {live && (
          <div className={s.controls}>
            <Select
              label="Who responds"
              hideLabel
              value={cfg?.responderPolicy ?? "auto"}
              options={POLICY.map((o) => ({ value: o.value, label: o.label, hint: o.hint }))}
              onChange={(v) => void run(() => client.chat.setResponderPolicy(session.id, v))}
              className={s.policy}
            />
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => void run(() => client.chat.everyoneAnswer(session.id))}>
              Everyone answer
            </Button>
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => void run(() => client.chat.nextSpeaker(session.id))}>
              Next ▸
            </Button>
          </div>
        )}
      </div>

      <div className={s.stage}>
        {wing("left", left)}
        <div className={s.logPanel}>
          <SessionLog rt={rt} className={s.log} />
        </div>
        {wing("right", right)}
      </div>
    </div>
  );
}
