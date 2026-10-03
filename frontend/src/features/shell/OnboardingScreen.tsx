// S02 Onboarding (APP-04): 4 intro cards (copy: doc 06 §8) + a key step ("Enter key" / "Explore demo first").
// Shown once (prefs.seenOnboarding), replayable from World Select ("How it works"), the Esc menu and Settings → About.
// ←/→ page, Enter = next. A replay with a key already set ends on "You're live" instead of the key form. Owner: Builder A.
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { toast } from "../../app/layers";
import { useShortcut } from "../../app/shortcuts";
import { audio } from "../../audio/engine";
import { EnergyBar } from "../../character/EnergyBar";
import { client } from "../../client";
import { useSettings } from "../../client/hooks";
import type { HorizonErrorShape } from "../../contract/errors";
import type { Route } from "../../router";
import { navigate } from "../../router";
import { setPrefs } from "../../stores/prefs";
import { Button } from "../../ui/Button";
import { TextField } from "../../ui/Fields";
import { RansomText } from "../../ui/RansomText";
import { Tape } from "../../ui/Tape";
import { WorldCover } from "../../ui/WorldCover";
import { useHouseScreen } from "./house";
import { saveKeyHint } from "./keyHint";
import s from "./Onboarding.module.css";

interface Card { id: string; word: string; lead: string; body: string; art: () => ReactNode }

const portrait = (id: string, emotion = "neutral") => `/assets/placeholder/portraits/${id}/${emotion}.svg`;

const CARDS: Card[] = [
  { id: "worlds", word: "WORLDS", lead: "Worlds", body: "separate universes. Nothing crosses between them.", art: () => <WorldsArt /> },
  { id: "characters", word: "CHARACTERS", lead: "Characters", body: "describe someone in one line; AI drafts them, you approve.", art: () => <CharactersArt /> },
  { id: "sessions", word: "SESSIONS", lead: "Sessions", body: "chat 1:1, gather a group, run a debate, or just watch.", art: () => <SessionsArt /> },
  { id: "energy", word: "ENERGY", lead: "Energy ⚡", body: "characters spend energy when they talk and recharge over a day. That's how Horizon keeps your costs tiny.", art: () => <EnergyArt /> },
];
const STEPS = CARDS.length + 1; // + the key step

export function OnboardingScreen({ route }: { route: Extract<Route, { name: "onboarding" }> }) {
  useHouseScreen();
  const card = Math.min(Math.max(route.card ?? 1, 1), STEPS);
  const isKey = card === STEPS;
  const go = (n: number) => {
    if (n < 1 || n > STEPS || n === card) return;
    audio.playSfx("ui_whoosh");
    navigate({ name: "onboarding", card: n }, { transition: n > card ? "slash" : "slash-back", replace: true });
  };
  const finish = (to: Route) => {
    setPrefs({ seenOnboarding: true });
    navigate(to);
  };

  useShortcut("arrowright", () => go(card + 1));
  useShortcut("arrowleft", () => go(card - 1));

  const c = CARDS[card - 1];
  return (
    <main className={s.screen} data-screen="S02" aria-labelledby="onb-title">
      <div className={s.stripe} aria-hidden="true" />
      <header className={s.top}>
        <ol className={s.pips} aria-label={`Step ${card} of ${STEPS}`}>
          {Array.from({ length: STEPS }, (_, i) => (
            <li key={i} className={s.pip} data-on={i + 1 <= card || undefined} data-current={i + 1 === card || undefined}>
              <button type="button" onClick={() => go(i + 1)} aria-label={i < CARDS.length ? `Card ${i + 1}: ${CARDS[i].lead}` : "Key step"} aria-current={i + 1 === card ? "step" : undefined} />
            </li>
          ))}
        </ol>
        {!isKey && (
          <Button variant="ghost" size="sm" onClick={() => go(STEPS)}>Skip intro</Button>
        )}
      </header>

      {isKey ? (
        <KeyStep onDone={finish} onBack={() => go(card - 1)} />
      ) : (
        <section className={s.body} key={c.id}>
          <div className={s.copy}>
            <span className={s.num} aria-hidden="true">{String(card).padStart(2, "0")}<small>/{String(CARDS.length).padStart(2, "0")}</small></span>
            <h1 id="onb-title" className={s.word}>
              <RansomText text={c.word} size={`min(var(--word-size), ${Math.floor(560 / (c.word.length * 0.95))}px)`} tone="mixed" slam staggerMs={35} />
            </h1>
            <p className={s.line}>
              <strong>{c.lead}</strong>: {c.body}
            </p>
            <div className={s.nav}>
              <Button variant="secondary" onClick={() => go(card - 1)} disabled={card === 1}>◂ Back</Button>
              <Button onClick={() => go(card + 1)} autoFocus>Next ▸</Button>
            </div>
            <p className={s.hint} aria-hidden="true">← → to flip · Enter for next</p>
          </div>
          <div className={s.art} aria-hidden="true">{c.art()}</div>
        </section>
      )}
    </main>
  );
}

// ── Key step ────────────────────────────────────────────────────────────────
function KeyStep({ onDone, onBack }: { onDone: (to: Route) => void; onBack: () => void }) {
  const live = useSettings().data?.openRouterKeyStatus === "set";
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    const k = key.trim();
    if (!k) return setError("Paste your OpenRouter key, or explore the demo first.");
    setBusy(true);
    setError(null);
    try {
      const st = await client.settings.setKey(k);
      if (st.openRouterKeyStatus === "invalid") {
        setError("That key was rejected by OpenRouter.");
        return;
      }
      saveKeyHint(k);
      toast({ variant: "success", text: "Key saved on this machine. Live mode is on." });
      onDone({ name: "worlds" });
    } catch (e) {
      setError((e as HorizonErrorShape).message ?? "Couldn't save the key.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className={s.body}>
      <div className={s.copy}>
        <span className={s.num} aria-hidden="true">GO</span>
        <h1 id="onb-title" className={s.word}>
          <RansomText text="YOUR KEY" size="var(--word-size)" tone="mixed" slam staggerMs={35} />
        </h1>
        <p className={s.line}>
          Horizon thinks with your own <strong>OpenRouter</strong> key. No key? Every recording still plays: browse the seed worlds and replay their sessions.
        </p>
        {live ? (
          <div className={s.nav}>
            <Button onClick={() => onDone({ name: "worlds" })} autoFocus>You're live · To worlds ▸</Button>
          </div>
        ) : (
          <form
            className={s.keyForm}
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            <TextField
              label="OpenRouter key"
              type="password"
              placeholder="sk-or-…"
              value={key}
              autoComplete="off"
              spellCheck={false}
              onChange={(e) => {
                setKey(e.target.value);
                setError(null);
              }}
              error={error}
              hint="Stored on this machine only. Never sent anywhere but OpenRouter."
            />
            <div className={s.nav}>
              <Button type="submit" disabled={busy}>{busy ? "Checking…" : "Enter key ▸"}</Button>
              <Button variant="secondary" onClick={() => onDone({ name: "worlds" })} autoFocus>Explore demo first</Button>
            </div>
          </form>
        )}
        <div className={s.nav}>
          <Button variant="ghost" size="sm" onClick={onBack}>◂ Back</Button>
        </div>
      </div>
      <div className={s.art} aria-hidden="true">
        <div className={s.keyArt}>
          <div className={s.keyCard}>
            <Tape tone="brand" size="md">DEMO MODE</Tape>
            <ul>
              <li>✓ Browse worlds &amp; characters</li>
              <li>✓ Replay every recorded session</li>
              <li>✓ Open the Insight drawer</li>
              <li className={s.locked}>⚿ Chat, create, start sessions</li>
            </ul>
          </div>
          <div className={`${s.keyCard} ${s.keyCardLive}`}>
            <Tape tone="ink" size="md">LIVE</Tape>
            <ul>
              <li>✓ Everything in demo</li>
              <li>✓ Talk, summon, debate live</li>
              <li>✓ Costs shown before you spend</li>
              <li>✓ Energy keeps it cheap</li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

// ── Card art ────────────────────────────────────────────────────────────────
function WorldsArt() {
  return (
    <div className={s.worldsArt}>
      <WorldCover presetId="cover_night_skyline" className={`${s.cover} ${s.coverA}`}>
        <span className={s.coverName}>Meridian Council</span>
      </WorldCover>
      <WorldCover presetId="cover_sunset_rooftops" className={`${s.cover} ${s.coverB}`}>
        <span className={s.coverName}>Sunny Hollow</span>
      </WorldCover>
      <Tape tone="ink" size="lg" className={s.wall}>NOTHING CROSSES</Tape>
    </div>
  );
}

function CharactersArt() {
  return (
    <div className={s.charArt}>
      <div className={s.prompt}>
        <span className={s.promptLabel}>ONE LINE</span>
        <span className={s.promptText}>"An emergency doctor who hates hype"</span>
      </div>
      <div className={s.arrow}>AI DRAFTS ▸</div>
      <figure className={s.cardFig}>
        <img src={portrait("chr_seedAmara", "happy")} alt="" />
        <Tape tone="paper" size="sm" className={s.placeholderTape}>PLACEHOLDER · HAPPY</Tape>
        <Tape tone="brand" size="lg" className={s.summon}>SUMMONED</Tape>
      </figure>
    </div>
  );
}

function SessionsArt() {
  const modes: { k: string; label: string; ids: string[] }[] = [
    { k: "one", label: "1 : 1", ids: ["chr_seedHana"] },
    { k: "group", label: "GROUP", ids: ["chr_seedHana", "chr_seedTakeshi", "chr_seedRin"] },
    { k: "debate", label: "DEBATE", ids: ["chr_seedAmara", "chr_seedMei"] },
    { k: "watch", label: "WATCH", ids: ["chr_seedRin", "chr_seedTakeshi"] },
  ];
  return (
    <div className={s.modesArt}>
      {modes.map((m, i) => (
        <div key={m.k} className={s.mode} style={{ animationDelay: `${120 + i * 70}ms` }} data-mode={m.k}>
          <span className={s.modeLabel}>{m.label}</span>
          <span className={s.heads}>
            {m.ids.map((id, j) => (
              <img key={id + j} src={portrait(id)} alt="" />
            ))}
          </span>
          {m.k === "debate" && <span className={s.vs}>VS</span>}
        </div>
      ))}
    </div>
  );
}

function EnergyArt() {
  const [cur, setCur] = useState(640);
  useEffect(() => {
    const id = window.setInterval(() => setCur((c) => (c <= 600 ? 640 : c - 5)), 1800);
    return () => window.clearInterval(id);
  }, []);
  return (
    <div className={s.energyArt}>
      <figure className={s.energyFig}>
        <img src={portrait("chr_seedHana", "happy")} alt="" />
      </figure>
      <div className={s.energyPanel}>
        <span className={s.energyName}>HANA</span>
        <EnergyBar energy={{ current: cur, max: 1000, state: "active" }} size="chat" showLabel paletteId="pal_sakura_pop" label="Hana" />
        <div className={s.energyFacts}>
          <span><b>1 ⚡</b> = US$0.0001</span>
          <span><b>1000 ⚡</b> a day by default</span>
          <span><b>Full</b> again in ~24 h</span>
        </div>
      </div>
      <div className={s.sleepy}>
        <img src={portrait("chr_seedRin")} alt="" />
        <span className={s.zzz}>Z<sup>z</sup><sup>z</sup></span>
        <Tape tone="error" size="sm">TIRED · 180 ⚡</Tape>
      </div>
    </div>
  );
}
