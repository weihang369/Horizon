// S14 Settings (SET-01..12): 8 tabs — Connection · Audio · Chat · Display · Models · Cost (+ Spend view) · Data · About.
// Vertical tab rail (↑/↓), deep-linkable (`#/settings/:tab?from=`), ◂ returns to `from`. House palette. Owner: Builder A.
import { useRef } from "react";
import type { KeyboardEvent } from "react";
import { openOverlay, toast } from "../../app/layers";
import { audio } from "../../audio/engine";
import { useSettings } from "../../client/hooks";
import { client } from "../../client";
import type { AppSettings } from "../../contract/types";
import type { Route, SettingsTab } from "../../router";
import { navigate, parseRoute } from "../../router";
import { SETTINGS_TABS } from "../../router/routes";
import { mockActions } from "../../stores/mock";
import { setPrefs, usePrefs } from "../../stores/prefs";
import { Button } from "../../ui/Button";
import { Segmented, Slider, Toggle } from "../../ui/Controls";
import { Skeleton } from "../../ui/Data";
import { Kbd } from "../../ui/Kbd";
import { RansomText } from "../../ui/RansomText";
import { Tape } from "../../ui/Tape";
import { BackIcon } from "../../ui/icons";
import { useHouseScreen } from "../shell/house";
import { APP_VERSION } from "../shell/TitleScreen";
import { ConnectionTab } from "./ConnectionTab";
import { CostTab } from "./CostTab";
import { DisplayTab } from "./DisplayTab";
import { ModelsTab } from "./ModelsTab";
import { Row, Section, useSettingsPatch } from "./parts";
import s from "./Settings.module.css";

const LABEL: Record<SettingsTab, string> = {
  connection: "Connection", audio: "Audio", chat: "Chat", display: "Display", models: "Models", cost: "Cost", data: "Data", about: "About",
};
const BLURB: Record<SettingsTab, string> = {
  connection: "Your OpenRouter key", audio: "Volumes & ducking", chat: "Defaults for new sessions", display: "Motion, VFX, text size",
  models: "Advanced model IDs", cost: "Caps, energy, spend", data: "Reset & delete", about: "Version & credits",
};
const pct = (v: number) => `${Math.round(v * 100)} %`;

export function SettingsScreen({ route }: { route: Extract<Route, { name: "settings" }> }) {
  useHouseScreen({ music: false });
  const tab: SettingsTab = route.tab ?? "connection";
  const settings = useSettings();
  const rail = useRef<HTMLDivElement>(null);
  const setTab = (t: SettingsTab) => {
    if (t === tab) return;
    audio.playSfx("ui_toggle");
    navigate({ name: "settings", tab: t, ...(route.from ? { from: route.from } : {}) }, { transition: "none", replace: true });
  };
  const goBack = () => {
    const to = route.from ? parseRoute(route.from) : null;
    navigate(to && to.name !== "settings" && to.name !== "title" ? to : { name: "worlds" }, { transition: "slash-back" });
  };
  const onRailKey = (e: KeyboardEvent) => {
    const i = SETTINGS_TABS.indexOf(tab);
    let n = -1;
    if (e.key === "ArrowDown") n = (i + 1) % SETTINGS_TABS.length;
    else if (e.key === "ArrowUp") n = (i - 1 + SETTINGS_TABS.length) % SETTINGS_TABS.length;
    else if (e.key === "Home") n = 0;
    else if (e.key === "End") n = SETTINGS_TABS.length - 1;
    if (n < 0) return;
    e.preventDefault();
    setTab(SETTINGS_TABS[n]);
    rail.current?.querySelector<HTMLButtonElement>(`#set-tab-${SETTINGS_TABS[n]}`)?.focus();
  };

  return (
    <main className={s.screen} data-screen="S14" aria-labelledby="settings-title">
      <div className={s.stripe} aria-hidden="true" />
      <aside className={s.side}>
        <Button variant="ghost" size="sm" icon={<BackIcon />} onClick={goBack}>Back</Button>
        <h1 id="settings-title" className={s.title}>
          <RansomText text="SETTINGS" size={33} tone="mixed" slam staggerMs={28} />
        </h1>
        <div ref={rail} className={s.rail} role="tablist" aria-orientation="vertical" aria-label="Settings sections" onKeyDown={onRailKey}>
          {SETTINGS_TABS.map((t, i) => (
            <button
              key={t}
              id={`set-tab-${t}`}
              type="button"
              role="tab"
              aria-selected={t === tab}
              aria-controls="set-panel"
              tabIndex={t === tab ? 0 : -1}
              className={s.tab}
              onClick={() => setTab(t)}
            >
              <span className={s.tabNum} aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
              <span className={s.tabText}>
                <span className={s.tabLabel}>{LABEL[t]}</span>
                <span className={s.tabBlurb}>{BLURB[t]}</span>
              </span>
              {t === "connection" && settings.data?.demoMode && <span className={s.tabDot}>NO KEY</span>}
            </button>
          ))}
        </div>
      </aside>

      <section id="set-panel" role="tabpanel" aria-labelledby={`set-tab-${tab}`} className={s.panel} key={tab}>
        <header className={s.panelHead}>
          <span className={s.panelNum} aria-hidden="true">{String(SETTINGS_TABS.indexOf(tab) + 1).padStart(2, "0")}</span>
          <h2 className={s.panelTitle}>{LABEL[tab]}</h2>
        </header>
        {!settings.data ? (
          <Skeleton lines={6} widths={["60%", "90%", "80%", "70%", "85%", "50%"]} height={18} />
        ) : (
          <TabBody tab={tab} settings={settings.data} />
        )}
      </section>
    </main>
  );
}

function TabBody({ tab, settings }: { tab: SettingsTab; settings: AppSettings }) {
  switch (tab) {
    case "connection": return <ConnectionTab settings={settings} />;
    case "audio": return <AudioTab />;
    case "chat": return <ChatTab settings={settings} />;
    case "display": return <DisplayTab />;
    case "models": return <ModelsTab settings={settings} />;
    case "cost": return <CostTab settings={settings} />;
    case "data": return <DataTab />;
    case "about": return <AboutTab />;
  }
}

// ── Audio (SET-02) ───────────────────────────────────────────────────────────
function AudioTab() {
  const a = usePrefs((p) => p.audio);
  return (
    <>
      <Section title="Volume" desc="Changes apply instantly. Stored in this browser.">
        <Slider label="Master" value={a.master} min={0} max={1} step={0.05} format={pct} onChange={(master) => setPrefs({ audio: { master } })} />
        <Slider label="Music" value={a.music} min={0} max={1} step={0.05} format={pct} onChange={(music) => setPrefs({ audio: { music } })} />
        <Slider label="Sound effects" value={a.sfx} min={0} max={1} step={0.05} format={pct} onChange={(sfx) => { setPrefs({ audio: { sfx } }); audio.playSfx("ui_toggle"); }} />
      </Section>
      <Section title="Mute">
        <Row label="Mute everything" desc="Global mute."><Toggle label="Mute everything" hideLabel checked={a.masterMuted} onChange={(masterMuted) => setPrefs({ audio: { masterMuted } })} /></Row>
        <Row label="Mute music"><Toggle label="Mute music" hideLabel checked={a.musicMuted} onChange={(musicMuted) => setPrefs({ audio: { musicMuted } })} /></Row>
        <Row label="Mute sound effects"><Toggle label="Mute sound effects" hideLabel checked={a.sfxMuted} onChange={(sfxMuted) => setPrefs({ audio: { sfxMuted } })} /></Row>
      </Section>
      <Section title="Mixing">
        <Row label="Duck music under stings" desc="Gong, VS, verdict and Summon dip the music to 40 %, then recover over 600 ms.">
          <Toggle label="Duck music under stings" hideLabel checked={a.duckMusic} onChange={(duckMusic) => setPrefs({ audio: { duckMusic } })} />
        </Row>
        <Row label="Test" desc="Plays the VS sting so you can hear the duck.">
          <Button size="sm" variant="secondary" onClick={() => { void audio.unlock().then(() => audio.playSfx("vs_sting")); }}>Play sting</Button>
        </Row>
      </Section>
    </>
  );
}

// ── Chat defaults (SET-03) ───────────────────────────────────────────────────
function ChatTab({ settings }: { settings: AppSettings }) {
  const { save } = useSettingsPatch();
  const cutIns = usePrefs((p) => p.display.speakerCutIns);
  const c = settings.chat;
  return (
    <Section title="New sessions start with" desc="You can still change each of these inside a session.">
      <Row label="Emotion mode" desc="AUTO lets the model pick faces; MANUAL lets you set them (Alt+1…7).">
        <Segmented label="Emotion mode" value={c.defaultEmotionMode} onChange={(v) => void save({ chat: { defaultEmotionMode: v } })} options={[{ value: "llm", label: "Auto" }, { value: "user", label: "Manual" }]} />
      </Row>
      <Row label="Group responders" desc="Who answers in a group chat by default.">
        <Segmented label="Group responders" value={c.responderDefault} onChange={(v) => void save({ chat: { responderDefault: v } })} options={[{ value: "auto", label: "Auto" }, { value: "everyone", label: "Everyone" }, { value: "mentioned", label: "Mentioned" }]} />
      </Row>
      <Row label="Debate auto-advance" desc="Turns flow on their own; turn it off to step with Next.">
        <Toggle label="Debate auto-advance" hideLabel checked={c.debateAutoAdvance} onChange={(v) => void save({ chat: { debateAutoAdvance: v } })} />
      </Row>
      <Row label="Readable Mode" desc="Long answers open in a straight, 68-character panel.">
        <Toggle label="Readable Mode by default" hideLabel checked={c.readableDefault} onChange={(v) => void save({ chat: { readableDefault: v } })} />
      </Row>
      <Row label="Speaker cut-ins" desc="A quick portrait slash when the speaker changes in multi-character scenes.">
        <Toggle label="Speaker cut-ins" hideLabel checked={cutIns} onChange={(speakerCutIns) => setPrefs({ display: { speakerCutIns } })} />
      </Row>
    </Section>
  );
}

// ── Data (SET-10) ────────────────────────────────────────────────────────────
function DataTab() {
  const trim = usePrefs((p) => p.replayTrimGaps);
  const reset = () =>
    openOverlay("O03", {
      title: "Reset demo data?",
      body: "Restores the seed worlds, characters and recordings exactly as shipped. Anything you created in this browser is removed. Your key and display settings stay.",
      confirmLabel: "Reset demo data",
      onConfirm: async () => {
        await mockActions.resetDemoData();
        toast({ variant: "success", text: "Demo data restored." });
      },
    });
  const wipe = () =>
    openOverlay("O03", {
      title: "Delete all data?",
      body: "Every world, character, session, memory and your saved key are deleted from this machine. This can't be undone.",
      typed: "DELETE ALL",
      confirmLabel: "Delete everything",
      onConfirm: async () => {
        const worlds = await client.worlds.list();
        for (const w of worlds) await client.worlds.delete(w.id);
        await client.settings.setKey(null);
        toast({ variant: "info", text: "All data deleted." });
        navigate({ name: "worlds" });
      },
    });
  return (
    <>
      <Section title="Where your data lives" desc="Horizon is local-first: nothing leaves this machine except calls to OpenRouter.">
        <Row label="Data folder" desc="This UI preview keeps everything in your browser's local storage.">
          <code className={s.path}>localStorage · horizon.*</code>
        </Row>
      </Section>
      <Section title="Replays">
        <Row label="Trim long pauses" desc="Replays clamp gaps longer than 2.5 s so recordings stay snappy.">
          <Toggle label="Trim long pauses in replays" hideLabel checked={trim} onChange={(replayTrimGaps) => setPrefs({ replayTrimGaps })} />
        </Row>
      </Section>
      <Section title="Danger zone">
        <Row label="Reset demo data" desc="Bring back the seed worlds and recordings as shipped.">
          <Button variant="secondary" onClick={reset}>Reset demo data</Button>
        </Row>
        <Row label="Delete all data" desc="Requires typing DELETE ALL.">
          <Button variant="danger" onClick={wipe}>Delete all data…</Button>
        </Row>
      </Section>
    </>
  );
}

// ── About (SET-11) ───────────────────────────────────────────────────────────
function AboutTab() {
  return (
    <>
      <div className={s.about}>
        <RansomText text="HORIZON" size={56} tone="mixed" />
        <div className={s.aboutMeta}>
          <Tape tone="paper" size="sm">{APP_VERSION}</Tape>
          <span>An open-source multi-agent character sandbox. Bring your own OpenRouter key.</span>
        </div>
      </div>
      <Section title="Project">
        <Row label="Source" desc="Issues and pull requests welcome."><a className={s.link} href="https://github.com/weihang369/Horizon" target="_blank" rel="noreferrer">github.com/weihang369/Horizon ↗</a></Row>
        <Row label="Licence"><span className={s.value}>MIT</span></Row>
        <Row label="Asset credits" desc="Portraits and music in this preview are procedural placeholders (labelled PLACEHOLDER / SKETCH). Real assets and their provenance are listed in ASSETS.md.">
          <a className={s.link} href="https://github.com/weihang369/Horizon/blob/main/ASSETS.md" target="_blank" rel="noreferrer">ASSETS.md ↗</a>
        </Row>
      </Section>
      <Section title="Help">
        <Row label="Replay onboarding" desc="The four intro cards and the key step.">
          <Button variant="secondary" onClick={() => { setPrefs({ seenOnboarding: false }); navigate({ name: "onboarding", card: 1 }); }}>Replay intro</Button>
        </Row>
        <Row label="Keyboard shortcuts" desc={<>Or press <Kbd>?</Kbd> anywhere outside a text field.</>}>
          <Button variant="secondary" onClick={() => openOverlay("O20")}>Show shortcuts</Button>
        </Row>
      </Section>
    </>
  );
}
