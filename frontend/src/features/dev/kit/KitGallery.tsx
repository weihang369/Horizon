// Kit Gallery (#/dev/kit): every primitive, all 6 seed characters × 7 emotions, every VFX, energy state,
// transition, ceremony, palette, cover and sound — one anchored page for screenshot review. Owner: VMD.
// Hidden in Presenter Mode by the EE's router. Lazy-loaded: `export function KitGallery()` (no props).
import { useEffect, useMemo, useRef, useState, type CSSProperties, type MouseEvent, type ReactNode } from "react";
import type { Character, Emotion, EnergyState } from "../../../contract/types";
import { EMOTIONS } from "../../../contract/types";
import amaraJson from "@seed/characters/chr_seedAmara.json";
import victorJson from "@seed/characters/chr_seedVictor.json";
import meiJson from "@seed/characters/chr_seedMei.json";
import hanaJson from "@seed/characters/chr_seedHana.json";
import takeshiJson from "@seed/characters/chr_seedTakeshi.json";
import rinJson from "@seed/characters/chr_seedRin.json";
import { EmotionVfx, EnergyBar, NamePlate, PortraitCard, emotionMeta, type EnergyValue } from "../../../character";
import {
  Button, ChipGroup, CostBadge, Drawer, EmptyState, ErrorTape, HalftoneDevelop, IconButton, Kbd, Menu, Modal,
  ProbBar, RansomText, ScanLoader, Segmented, Select, Skeleton, Slider, StackedBar, Swatch, Tabs, Tape, TextArea,
  TextField, ToastView, Toggle, Tooltip, WorldCover, Chip,
  BackIcon, GearIcon, MoreIcon, MusicIcon, PauseIcon, PlayIcon, PlusIcon, SearchIcon, SendIcon, StopIcon,
} from "../../../ui";
import { PALETTES, PaletteScope, setAppPalette, useAppPalette } from "../../../theme";
import { COVER_PRESETS } from "../../../vfx/covers";
import {
  applyDisplayPrefs, playCeremony, runTransition, useCeremony, useMotionPrefs, type TransitionKind,
} from "../../../motion";
import { SFX_IDS, renderSfx, type SfxId } from "../../../audio/synth/sfx";
import { SYSTEM_TRACK_KINDS } from "../../../audio/synth/system";
import { resolveAudio } from "../../../audio/resolve";
import s from "./KitGallery.module.css";

const unwrap = (j: unknown) => (j as { data: Character }).data;
const CAST: Character[] = [amaraJson, victorJson, meiJson, hanaJson, takeshiJson, rinJson].map(unwrap);
const first = (c: Character) => c.profile.name.split(" ")[0];

const SECTIONS: [string, string][] = [
  ["type", "Type & tape"], ["buttons", "Buttons"], ["controls", "Controls"], ["fields", "Fields"], ["data", "Data"],
  ["panels", "Panels"], ["portraits", "Portraits"], ["sizes", "Sizes & states"], ["vfx", "Emotion VFX"],
  ["energy", "Energy"], ["motion", "Motion"], ["palettes", "Palettes"], ["covers", "Covers"], ["audio", "Audio"],
];

export function KitGallery() {
  const prefs = useMotionPrefs();
  const appPalette = useAppPalette();
  return (
    <div className={s.root} data-kit-gallery="">
      <nav className={s.nav} aria-label="Kit sections">
        <RansomText text="KIT" size={44} as="div" tone="brand" />
        <p className={s.navSub}>Horizon visual kit · v1</p>
        <ul role="list">
          {SECTIONS.map(([id, label]) => (
            <li key={id}>
              <a href={`#kit-${id}`} onClick={(e) => { e.preventDefault(); document.getElementById(`kit-${id}`)?.scrollIntoView(); }}>
                {label}
              </a>
            </li>
          ))}
        </ul>
        <div className={s.prefs}>
          <Toggle label="Reduced motion" checked={prefs.reduced} onChange={(v) => applyDisplayPrefs({ reducedMotion: v ? "on" : "off" })} />
          <Segmented
            label="VFX"
            value={prefs.vfx}
            options={[{ value: "full", label: "Full" }, { value: "subtle", label: "Subtle" }, { value: "off", label: "Off" }]}
            onChange={(v) => applyDisplayPrefs({ vfxIntensity: v })}
          />
          <Segmented
            label="Flash"
            value={prefs.flash}
            options={[{ value: "full", label: "Full" }, { value: "low", label: "Low" }, { value: "off", label: "Off" }]}
            onChange={(v) => applyDisplayPrefs({ flashIntensity: v })}
          />
          <Toggle label="Parallax" checked={prefs.parallax} onChange={(v) => applyDisplayPrefs({ parallax: v })} />
          <span className={s.mono}>app palette: {appPalette ?? "house"}</span>
        </div>
      </nav>
      <main className={s.main}>
        <header className={s.hero}>
          <RansomText text="HORIZON VISUAL KIT" size={64} as="h1" slam />
          <p className={s.lede}>
            Ink, paper and one loud colour. Everything here is a production primitive — screenshot it, poke it, break it.
          </p>
        </header>
        <TypeSection />
        <ButtonsSection />
        <ControlsSection />
        <FieldsSection />
        <DataSection />
        <PanelsSection />
        <PortraitGrid />
        <SizesSection />
        <VfxSection />
        <EnergySection />
        <MotionSection />
        <PalettesSection />
        <CoversSection />
        <AudioSection />
        <footer className={s.footer}>End of kit · {CAST.length} seed characters · {PALETTES.length} palettes · {COVER_PRESETS.length} covers · {SFX_IDS.length} SFX</footer>
      </main>
    </div>
  );
}

function Section({ id, title, kicker, children }: { id: string; title: string; kicker?: string; children: ReactNode }) {
  return (
    <section id={`kit-${id}`} className={s.section} aria-labelledby={`kit-${id}-h`}>
      <div className={s.sectionHead}>
        <Tape tone="paper" size="sm">{kicker ?? id}</Tape>
        <h2 id={`kit-${id}-h`} className={s.h2}>{title}</h2>
      </div>
      {children}
    </section>
  );
}

function Row({ label, children, wrap = true }: { label?: string; children: ReactNode; wrap?: boolean }) {
  return (
    <div className={s.row}>
      {label && <div className={s.rowLabel}>{label}</div>}
      <div className={wrap ? s.rowBody : s.rowBodyNoWrap}>{children}</div>
    </div>
  );
}

// ── Type & tape ──────────────────────────────────────────────────────────────
function TypeSection() {
  return (
    <Section id="type" title="Type, tape & ransom" kicker="01">
      <Row label="Ransom">
        <RansomText text="ROUND 2" size={56} />
        <RansomText text="STRONGER CASE" size={40} tone="brand" />
        <RansomText text="Sunny Hollow" size={32} tone="paper" />
      </Row>
      <Row label="Display / UI / mono">
        <span className={s.display}>Anton display 40</span>
        <span className={s.body}>Inter body 16 / 1.55 — readability beats style for content.</span>
        <span className={s.mono}>JetBrains Mono · 0.71 · HIGH</span>
      </Row>
      <Row label="Tapes">
        {(["brand", "primary", "ink", "paper", "prop", "opp", "ok", "warn", "error"] as const).map((t) => (
          <Tape key={t} tone={t}>{t}</Tape>
        ))}
        <Tape tone="ink" size="lg" rotate={-3}>REPLAY</Tape>
        <Tape tone="brand" size="sm">RUSH HOUR · 2× ⚡</Tape>
      </Row>
      <Row label="Kbd / cost">
        <span><Kbd>Ctrl</Kbd> + <Kbd>Shift</Kbd> + <Kbd>P</Kbd></span>
        <Kbd>Esc</Kbd>
        <CostBadge usd={0.04} />
        <CostBadge usd={0.0042} tone="paper" />
        <CostBadge usd={1.2} approx={false} tone="brand" />
      </Row>
    </Section>
  );
}

// ── Buttons ──────────────────────────────────────────────────────────────────
function ButtonsSection() {
  return (
    <Section id="buttons" title="Buttons" kicker="02">
      {(["primary", "secondary", "ghost", "danger"] as const).map((v) => (
        <Row key={v} label={v}>
          <Button variant={v} size="sm">Small</Button>
          <Button variant={v}>Start session</Button>
          <Button variant={v} size="lg" iconRight={<SendIcon />}>Summon</Button>
          <Button variant={v} disabled>Disabled</Button>
        </Row>
      ))}
      <Row label="Cost / key-locked">
        <Button cost={0.04}>Generate ▸</Button>
        <Button keyLocked>Continue live</Button>
        <Button keyLocked variant="secondary" cost={0.06}>Regenerate</Button>
      </Row>
      <Row label="IconButton">
        <IconButton label="Play"><PlayIcon /></IconButton>
        <IconButton label="Pause"><PauseIcon /></IconButton>
        <IconButton label="Stop"><StopIcon /></IconButton>
        <IconButton label="Back"><BackIcon /></IconButton>
        <IconButton label="Add" size="sm"><PlusIcon /></IconButton>
        <IconButton label="More"><MoreIcon /></IconButton>
        <IconButton label="Search"><SearchIcon /></IconButton>
        <IconButton label="Music"><MusicIcon /></IconButton>
        <IconButton label="Settings" size="lg"><GearIcon /></IconButton>
      </Row>
    </Section>
  );
}

// ── Controls ─────────────────────────────────────────────────────────────────
function ControlsSection() {
  const [single, setSingle] = useState<string | null>("calm");
  const [multi, setMulti] = useState<string[]>(["glasses", "headphones"]);
  const [tab, setTab] = useState("roster");
  const [on, setOn] = useState(true);
  const [pace, setPace] = useState("normal");
  const [vol, setVol] = useState(70);
  const [pal, setPal] = useState("pal_sakura_pop");
  const [preview, setPreview] = useState<string | null>(null);
  return (
    <Section id="controls" title="Chips, tabs, toggles, sliders, swatches" kicker="03">
      <Row label="Chip">
        <Chip>Idle</Chip>
        <Chip selected>Selected</Chip>
        <Chip size="sm">Small</Chip>
        <Chip disabled>Disabled</Chip>
      </Row>
      <Row label="ChipGroup">
        <ChipGroup
          label="Mood (single)"
          value={single}
          onChange={setSingle}
          options={["calm", "hopeful", "tense", "playful", "dreamy"].map((v) => ({ value: v, label: v }))}
        />
        <ChipGroup
          multiple
          max={3}
          label="Accessories (max 3)"
          value={multi}
          onChange={setMulti}
          options={["glasses", "headphones", "scarf", "earrings", "hairpin", "tie"].map((v) => ({ value: v, label: v }))}
        />
      </Row>
      <Row label="Tabs">
        <Tabs
          label="Hub"
          value={tab}
          onChange={setTab}
          tabs={[{ id: "roster", label: "Roster", badge: 6 }, { id: "sessions", label: "Sessions", badge: 5 }, { id: "memory", label: "Memory" }, { id: "locked", label: "Locked", disabled: true }]}
        />
      </Row>
      <Row label="Toggle / segmented / slider">
        <Toggle label="Auto-advance" checked={on} onChange={setOn} />
        <Segmented label="Pace" value={pace} onChange={setPace} options={[{ value: "slow", label: "Slow" }, { value: "normal", label: "Normal" }, { value: "fast", label: "Fast" }]} />
        <Slider label="Music" value={vol} min={0} max={100} onChange={setVol} format={(v) => `${v}%`} className={s.slider} />
      </Row>
      <Row label={`Swatch · preview: ${preview ?? "—"}`}>
        <div role="radiogroup" aria-label="Palette" className={s.swatches}>
          {PALETTES.map((p) => (
            <Swatch
              key={p.id}
              palette={p}
              selected={pal === p.id}
              aiPick={p.id === "pal_sakura_pop"}
              onSelect={(id) => setPal(id)}
              onPreview={setPreview}
            />
          ))}
        </div>
      </Row>
    </Section>
  );
}

// ── Fields ───────────────────────────────────────────────────────────────────
function FieldsSection() {
  const [name, setName] = useState("Hana Sato");
  const [bio, setBio] = useState("Runs the corner bakery. Remembers everyone's order and everyone's birthday.");
  const [voice, setVoice] = useState<string | null>("warm");
  const [menu, setMenu] = useState(false);
  const [picked, setPicked] = useState("—");
  return (
    <Section id="fields" title="Text fields, select, menu, tooltip" kicker="04">
      <div className={s.grid2}>
        <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} counter edited onRegenerate={() => setName("Hana Morita")} />
        <TextField label="Tagline" defaultValue="" placeholder="One line they'd say about themselves" error="Tagline is required." />
        <TextArea label="Backstory" value={bio} onChange={(e) => setBio(e.target.value)} counter counterMax={600} hint="Plain language. 2–4 sentences." onRegenerate={() => undefined} />
        <div className={s.stack}>
          <Select
            label="Speaking tone"
            value={voice}
            onChange={setVoice}
            options={[{ value: "warm", label: "Warm" }, { value: "dry", label: "Dry wit" }, { value: "formal", label: "Formal", hint: "slower" }, { value: "chaotic", label: "Chaotic", disabled: true }]}
          />
          <div className={s.menuHost}>
            <Button variant="secondary" size="sm" onClick={() => setMenu((m) => !m)} iconRight={<MoreIcon />}>Portrait menu</Button>
            <Menu
              open={menu}
              label="Portrait menu"
              onClose={() => setMenu(false)}
              onSelect={(id) => { setPicked(id); setMenu(false); }}
              items={[
                { id: "profile", label: "View profile", hint: "P" },
                { id: "ask", label: "Ask…", hint: "A" },
                { id: "mute", label: "Mute for 3 turns" },
                { id: "remove", label: "Remove from scene", danger: true, divider: true },
              ]}
            />
            <span className={s.mono}>picked: {picked}</span>
          </div>
          <Tooltip content="Estimated from the last 20 turns. Rush hour doubles energy cost.">
            <Button variant="ghost" size="sm">Hover me (tooltip)</Button>
          </Tooltip>
        </div>
      </div>
    </Section>
  );
}

// ── Data ─────────────────────────────────────────────────────────────────────
function DataSection() {
  return (
    <Section id="data" title="Insight data & loaders" kicker="05">
      <div className={s.grid2}>
        <div className={s.panel}>
          <Tape tone="brand" size="sm">Who speaks next</Tape>
          <div className={s.stack}>
            <ProbBar label="Amara" p={0.71} />
            <ProbBar label="Mei" p={0.52} color="var(--signal-warn)" />
            <ProbBar label="Victor" p={0.18} />
            <ProbBar label="Rin" p={1} forced />
          </div>
        </div>
        <div className={s.panel}>
          <Tape tone="brand" size="sm">Context budget</Tape>
          <StackedBar
            label="Context budget"
            total={16000}
            segments={[
              { key: "sys", label: "system", value: 900, color: "var(--paper-300)" },
              { key: "persona", label: "persona", value: 1800, color: "var(--horizon-500)" },
              { key: "mem", label: "memory", value: 1400, color: "var(--horizon-300)" },
              { key: "kn", label: "knowledge", value: 2200, color: "var(--signal-ok)" },
              { key: "hist", label: "history", value: 5200, color: "#6286BA" },
              { key: "user", label: "user", value: 380, color: "var(--signal-warn)" },
              { key: "mode", label: "mode", value: 260, color: "#B388EB" },
            ]}
          />
        </div>
        <div className={s.panel}>
          <Tape tone="ink" size="sm">Skeleton</Tape>
          <Skeleton lines={4} widths={["70%", "100%", "92%", "48%"]} />
        </div>
        <div className={s.panel}>
          <Tape tone="ink" size="sm">Loaders</Tape>
          <ScanLoader label="Drafting profile…" width={220} />
          <PaletteScope paletteId="pal_lavender_dream">
            <HalftoneDevelop label="Developing portrait…" className={s.develop} />
          </PaletteScope>
        </div>
      </div>
    </Section>
  );
}

// ── Panels ───────────────────────────────────────────────────────────────────
function PanelsSection() {
  return (
    <Section id="panels" title="Modal, drawer, toast, error, empty" kicker="06">
      <div className={s.panelsGrid}>
        <Modal
          title="Generate 6 emotions?"
          tape="Cost"
          onClose={() => undefined}
          actions={<><Button variant="ghost" size="sm">Cancel</Button><Button size="sm" cost={0.06}>Generate</Button></>}
        >
          <p className={s.body}>Six images at the lean preset. You can regenerate any one later.</p>
        </Modal>
        <Modal
          title="Delete Hana?"
          tape="Confirm"
          tone="danger"
          size="sm"
          actions={<><Button variant="ghost" size="sm">Keep</Button><Button variant="danger" size="sm">Delete</Button></>}
        >
          <p className={s.body}>Her memories and sessions go too. This can't be undone.</p>
        </Modal>
        <div className={s.drawerBox}>
          <Drawer title="Insight" width={380} onClose={() => undefined} headerExtra={<Tape tone="paper" size="sm">CACHE 80%</Tape>}>
            <div className={s.stack}>
              <ProbBar label="Amara" p={0.71} />
              <ProbBar label="Mei" p={0.33} />
              <span className={s.mono}>−5 ⚡ · 742 / 1000 · PEAK</span>
            </div>
          </Drawer>
        </div>
        <div className={s.stack}>
          <ToastView variant="success" text="Hana summoned." action={{ label: "View", run: () => undefined }} onDismiss={() => undefined} />
          <ToastView variant="info" text="Paused · Bakery Debate" />
          <ToastView variant="warn" text="Rin is tired (18%)." action={{ label: "Top up", run: () => undefined }} />
          <ToastView variant="error" text="Rate limited by the provider." onDismiss={() => undefined} />
          <ErrorTape message="The provider refused this turn." code="content_refused" action={{ label: "Retry", run: () => undefined, cost: 0.002 }} />
          <ErrorTape tone="warn" message="Daily budget at 80%." action={{ label: "Settings", run: () => undefined }} />
        </div>
        <div className={s.panel}>
          <EmptyState title="No sessions yet" body="Start a 1:1 or put three characters in a debate." action={{ label: "Start session", run: () => undefined }} />
        </div>
      </div>
    </Section>
  );
}

// ── Portrait grid: 6 × 7 ─────────────────────────────────────────────────────
function PortraitGrid() {
  return (
    <Section id="portraits" title="Seed cast × 7 emotions (Shadow Self placeholders)" kicker="07">
      <div className={s.emoHead}>
        <span />
        {EMOTIONS.map((e) => (
          <span key={e} className={s.emoLabel}>
            <b>{emotionMeta[e].hotkey}</b> {emotionMeta[e].icon} {emotionMeta[e].label}
          </span>
        ))}
      </div>
      {CAST.map((c) => (
        <div key={c.id} className={s.emoRow}>
          <NamePlate character={c} size="sm" />
          {EMOTIONS.map((e) => (
            <PortraitCard key={e} character={c} emotion={e} size="card" width="100%" />
          ))}
        </div>
      ))}
    </Section>
  );
}

// ── Sizes & states ───────────────────────────────────────────────────────────
function SizesSection() {
  const [hana, takeshi, rin, victor, mei, amara] = [CAST[3], CAST[4], CAST[5], CAST[1], CAST[2], CAST[0]];
  const hanaNoSad = useMemo(() => ({ ...hana, emotions: { ...hana.emotions, sad: null, angry: null } }), [hana]);
  const [emo, setEmo] = useState<Emotion>("neutral");
  return (
    <Section id="sizes" title="Sizes, plate, step-forward & states" kicker="08">
      <div className={s.sizesRow}>
        <PortraitCard character={amara} emotion={emo} size="hero" width={400} showPlate showEnergy onClick={() => setEmo(EMOTIONS[(EMOTIONS.indexOf(emo) + 1) % 7])} />
        <div className={s.stack}>
          <div className={s.emoPicker} role="radiogroup" aria-label="Emotion">
            {EMOTIONS.map((e) => (
              <Chip key={e} radio size="sm" selected={emo === e} onClick={() => setEmo(e)}>
                {emotionMeta[e].hotkey} · {emotionMeta[e].label}
              </Chip>
            ))}
          </div>
          <p className={s.note}>Hero 400 px, click the card or a chip: 300 ms crossfade + 1.02→1 settle, shake on angry, jump on surprised.</p>
          <div className={s.sizesSmall}>
            <PortraitCard character={victor} emotion="neutral" size="stage" showPlate showEnergy />
            <PortraitCard character={mei} emotion="thinking" size="card" showPlate showEnergy />
            <div className={s.stack}>
              <PortraitCard character={rin} emotion="happy" size="thumb" />
              <div className={s.heads}>
                {CAST.map((c) => <PortraitCard key={c.id} character={c} emotion="neutral" size="head" />)}
              </div>
            </div>
          </div>
        </div>
      </div>
      <Row label="States">
        <Labeled text="speaking"><PortraitCard character={victor} emotion="angry" size="card" width={170} speaking showPlate /></Labeled>
        <Labeled text="listening"><PortraitCard character={mei} emotion="neutral" size="card" width={170} listening showPlate /></Labeled>
        <Labeled text="dimmed"><PortraitCard character={hana} emotion="sad" size="card" width={170} dimmed showPlate /></Labeled>
        <Labeled text="tired"><PortraitCard character={rin} emotion="neutral" size="card" width={170} energyState="tired" showPlate showEnergy /></Labeled>
        <Labeled text="exhausted">
          <PortraitCard character={{ ...takeshi, energy: { ...takeshi.energy, current: 0, state: "exhausted" } }} emotion="happy" size="card" width={170} showPlate showEnergy />
        </Labeled>
        <Labeled text="missing art → tint"><PortraitCard character={hanaNoSad} emotion="sad" size="card" width={170} showPlate /></Labeled>
      </Row>
    </Section>
  );
}

function Labeled({ text, children }: { text: string; children: ReactNode }) {
  return (
    <figure className={s.labeled}>
      {children}
      <figcaption className={s.mono}>{text}</figcaption>
    </figure>
  );
}

// ── VFX ──────────────────────────────────────────────────────────────────────
function VfxSection() {
  const [n, setN] = useState(0);
  const [react, setReact] = useState<{ emotion: Emotion; key: number } | null>(null);
  const cast = CAST;
  return (
    <Section id="vfx" title="Emotion VFX: one-shots, loops, intensity, mini" kicker="09">
      <Row label="Replay">
        <Button size="sm" onClick={() => setN((x) => x + 1)}>Replay all one-shots</Button>
        <span className={s.note}>Max 3 one-shots run at once app-wide, so the replay staggers by design.</span>
      </Row>
      <div className={s.vfxGrid}>
        {EMOTIONS.filter((e) => e !== "neutral").map((e, i) => (
          <VfxCell key={e} character={cast[i % cast.length]} emotion={e} replay={n} delay={i * 260} />
        ))}
      </div>
      <Row label="Intensity (angry)">
        {(["full", "subtle", "off"] as const).map((lvl) => (
          <Labeled key={lvl} text={lvl}>
            <div className={s.vfxBox}>
              <PaletteScope paletteId={cast[1].paletteId} className={s.vfxCard}>
                <img src={cast[1].emotions.angry!.url} alt="" />
                <EmotionVfx emotion="angry" prev="neutral" intensity={lvl} playKey={n} />
              </PaletteScope>
            </div>
          </Labeled>
        ))}
        {(["tired", "exhausted"] as EnergyState[]).map((st) => (
          <Labeled key={st} text={`${st} (vfx off → badge)`}>
            <div className={s.vfxBox}>
              <PaletteScope paletteId={cast[5].paletteId} className={s.vfxCard}>
                <img src={cast[5].emotions.neutral!.url} alt="" />
                <EmotionVfx emotion="neutral" energyState={st} intensity="off" />
              </PaletteScope>
            </div>
          </Labeled>
        ))}
      </Row>
      <Row label="Mini reactions">
        {(["happy", "angry", "surprised", "thinking", "sad", "embarrassed"] as Emotion[]).map((e) => (
          <Button key={e} size="sm" variant="secondary" onClick={() => setReact({ emotion: e, key: Date.now() })}>
            {emotionMeta[e].icon} {e}
          </Button>
        ))}
        <PortraitCard character={cast[2]} emotion="neutral" size="card" width={150} reaction={react} listening />
        <PortraitCard character={cast[4]} emotion="neutral" size="card" width={150} reaction={react} listening />
      </Row>
    </Section>
  );
}

function VfxCell({ character, emotion, replay, delay }: { character: Character; emotion: Emotion; replay: number; delay: number }) {
  const [e, setE] = useState<Emotion>("neutral");
  useEffect(() => {
    setE("neutral");
    const t = window.setTimeout(() => setE(emotion), 120 + delay);
    return () => window.clearTimeout(t);
  }, [replay, emotion, delay]);
  return (
    <Labeled text={`${emotion} · ${emotionMeta[emotion].vfx}`}>
      <PortraitCard character={character} emotion={e} size="stage" width={200} />
    </Labeled>
  );
}

// ── Energy ───────────────────────────────────────────────────────────────────
function EnergySection() {
  const [v, setV] = useState<EnergyValue>({ current: 742, max: 1000, state: "active" });
  const set = (cur: number) => {
    const c = Math.max(0, Math.min(1000, cur));
    setV({ current: c, max: 1000, state: c <= 0 ? "exhausted" : c < 200 ? "tired" : "active" });
  };
  const fixed: [string, EnergyValue][] = [
    ["full", { current: 1000, max: 1000, state: "active" }],
    ["regenerating 74%", { current: 742, max: 1000, state: "active" }],
    ["amber < 40%", { current: 350, max: 1000, state: "active" }],
    ["red < 20% · tired", { current: 150, max: 1000, state: "tired" }],
    ["exhausted", { current: 0, max: 1000, state: "exhausted" }],
  ];
  return (
    <Section id="energy" title="Energy bar" kicker="10">
      <div className={s.grid2}>
        <div className={s.stack}>
          {fixed.map(([label, e]) => (
            <div key={label} className={s.energyRow}>
              <span className={s.rowLabel}>{label}</span>
              <PaletteScope paletteId="pal_ocean_clinic" className={s.energyCell}>
                <EnergyBar energy={e} size="chat" label="Amara" />
              </PaletteScope>
              <PaletteScope paletteId="pal_ocean_clinic" className={s.energyCell}>
                <EnergyBar energy={e} size="stage" />
              </PaletteScope>
            </div>
          ))}
        </div>
        <div className={s.panel}>
          <Tape tone="brand" size="sm">Interactive</Tape>
          <PaletteScope paletteId="pal_sakura_pop" className={s.energyLive}>
            <NamePlate character={CAST[3]} size="md" subtitle={`⚡ ${v.current} / ${v.max}`} />
            <EnergyBar energy={v} size="chat" label="Hana" onTopUp={() => set(v.current + 300)} />
            <EnergyBar energy={v} size="stage" />
          </PaletteScope>
          <div className={s.rowBody}>
            <Button size="sm" variant="secondary" onClick={() => set(v.current - 5)}>Drain −5</Button>
            <Button size="sm" variant="secondary" onClick={() => set(v.current - 120)}>Drain −120</Button>
            <Button size="sm" variant="secondary" onClick={() => set(v.current + 8)}>Regen tick</Button>
            <Button size="sm" onClick={() => set(v.current + 300)}>Top up +300</Button>
            <Button size="sm" variant="ghost" onClick={() => set(0)}>Exhaust</Button>
          </div>
        </div>
      </div>
    </Section>
  );
}

// ── Motion ───────────────────────────────────────────────────────────────────
function MotionSection() {
  const [route, setRoute] = useState(0);
  const card = useRef<HTMLDivElement>(null);
  const run = (kind: TransitionKind, e: MouseEvent) => {
    runTransition(kind, {
      origin: { x: e.clientX, y: e.clientY },
      sourceEl: kind === "shatter" ? card.current : undefined,
      onCover: () => setRoute((r) => r + 1),
    });
  };
  return (
    <Section id="motion" title="Transitions, ceremonies, palette flood" kicker="11">
      <Row label="Transitions">
        {(["slash", "slash-back", "flood", "fade", "none"] as TransitionKind[]).map((k) => (
          <Button key={k} size="sm" variant="secondary" onClick={(e) => run(k, e)}>{k}</Button>
        ))}
        <span className={s.mono}>route swaps at cover: #{route}</span>
      </Row>
      <Row label="Shatter (click the card)">
        <div ref={card} className={s.shatterCard} onClick={(e) => run("shatter", e)} role="button" tabIndex={0} aria-label="Shatter Meridian">
          <WorldCover presetId="cover_night_skyline" className={s.shatterCover}>
            <RansomText text="MERIDIAN" size={24} />
          </WorldCover>
        </div>
        <p className={s.note}>Six clipped clones radiate from the click point; the hub fades in under them (550 ms).</p>
      </Row>
      <Row label="Ceremonies">
        <CeremonyDemo />
      </Row>
      <Row label="setAppPalette (flood + snap)">
        {PALETTES.slice(0, 6).map((p) => (
          <Button
            key={p.id}
            size="sm"
            variant="secondary"
            style={{ "--c-glow": p.glow } as CSSProperties}
            onClick={(e) => setAppPalette(p.id, { flood: { x: e.clientX, y: e.clientY } })}
          >
            <span className={s.dot} style={{ background: p.primary }} /> {p.name}
          </Button>
        ))}
        <Button size="sm" variant="ghost" onClick={(e) => setAppPalette(null, { flood: { x: e.clientX, y: e.clientY } })}>House</Button>
      </Row>
    </Section>
  );
}

const CEREMONIES = [
  { id: "kit-vs", label: "VS slam", ms: 1600, text: "VS" },
  { id: "kit-round", label: "Banner slam", ms: 1500, text: "ROUND 2" },
  { id: "kit-summon", label: "Summon", ms: 1800, text: "SUMMONED" },
] as const;

function CeremonyDemo() {
  const [last, setLast] = useState<{ id: string; result: string } | null>(null);
  const [current, setCurrent] = useState<string | null>(null);
  return (
    <div className={s.ceremonyWrap}>
      <div className={s.rowBody}>
        {CEREMONIES.map((c) => (
          <Button
            key={c.id}
            size="sm"
            onClick={() => {
              setLast(null);
              setCurrent(c.id);
              void playCeremony(c.id, { durationMs: c.ms }).done.then((r) => setLast({ id: c.label, result: r }));
            }}
          >
            {c.label}
          </Button>
        ))}
        <span className={s.mono}>{last ? `${last.id}: ${last.result}` : "any key / click skips to the end state (≤120 ms)"}</span>
      </div>
      <div className={s.ceremonyStage}>
        {CEREMONIES.filter((c) => c.id === current).map((c) => <CeremonyView key={c.id} id={c.id} text={c.text} />)}
      </div>
    </div>
  );
}

function CeremonyView({ id, text }: { id: string; text: string }) {
  const { active, skipped } = useCeremony(id);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (active) setShown(true);
  }, [active]);
  if (!shown) return null;
  const end = skipped || !active;
  return (
    <div className={s.ceremony} data-end={end || undefined}>
      <div className={s.ceremonyBand} />
      <RansomText key={end ? "end" : "play"} text={text} size={text === "VS" ? 96 : 56} slam={!end} staggerMs={60} tone="mixed" />
    </div>
  );
}

// ── Palettes ─────────────────────────────────────────────────────────────────
function PalettesSection() {
  return (
    <Section id="palettes" title="12 palettes (scoped)" kicker="12">
      <div className={s.palGrid}>
        {PALETTES.map((p) => (
          <PaletteScope key={p.id} paletteId={p.id} className={s.palCard}>
            <div className={s.palChips}>
              {(["primary", "secondary", "accent", "glow", "surface", "stage"] as const).map((k) => (
                <i key={k} title={`${k} ${p[k]}`} style={{ background: p[k] }} />
              ))}
            </div>
            <div className={s.palBody}>
              <span className={s.palName}>{p.name}</span>
              <span className={s.palFit}>{p.fit}</span>
              <div className={s.rowBody}>
                <Button size="sm">Summon</Button>
                <Tape tone="primary" size="sm">{p.id.replace("pal_", "")}</Tape>
              </div>
              <EnergyBar energy={{ current: 640, max: 1000 }} size="stage" />
            </div>
          </PaletteScope>
        ))}
      </div>
    </Section>
  );
}

// ── Covers ───────────────────────────────────────────────────────────────────
function CoversSection() {
  return (
    <Section id="covers" title="World covers (8 presets)" kicker="13">
      <div className={s.coverGrid}>
        {COVER_PRESETS.map((c) => (
          <figure key={c.id} className={s.coverCard}>
            <WorldCover presetId={c.id} className={s.cover} label={c.name}>
              <RansomText text={c.name.toUpperCase()} size={19} tone="ink" />
            </WorldCover>
            <figcaption className={s.mono}>{c.id}</figcaption>
          </figure>
        ))}
      </div>
    </Section>
  );
}

// ── Audio ────────────────────────────────────────────────────────────────────
let actx: AudioContext | null = null;
let playing: AudioBufferSourceNode | null = null;
function play(buf: AudioBuffer, loop = false): void {
  actx ??= new AudioContext();
  void actx.resume();
  playing?.stop();
  const src = actx.createBufferSource();
  src.buffer = buf;
  src.loop = loop;
  src.connect(actx.destination);
  src.start();
  playing = src;
}

function stats(buf: AudioBuffer) {
  let peak = 0;
  let sum = 0;
  let diff = 0;
  let n = 0;
  for (let c = 0; c < buf.numberOfChannels; c++) {
    const d = buf.getChannelData(c);
    for (let i = 0; i < d.length; i++) {
      const v = d[i];
      peak = Math.max(peak, Math.abs(v));
      sum += v * v;
      if (i) diff += (v - d[i - 1]) ** 2;
      n++;
    }
  }
  const rms = Math.sqrt(sum / Math.max(1, n));
  const db = (x: number) => (x > 0 ? 20 * Math.log10(x) : -Infinity);
  // "brightness": energy of the first difference relative to the signal (≈ high-frequency share)
  return { peakDb: +db(peak).toFixed(1), rmsDb: +db(rms).toFixed(1), bright: +(diff / Math.max(1e-9, sum)).toFixed(3), sec: +buf.duration.toFixed(2) };
}

// Exposed for automated QA (Playwright eval): renders everything and returns loudness stats.
(globalThis as unknown as { __kitAudioStats?: () => Promise<unknown> }).__kitAudioStats = async () => {
  const out: Record<string, ReturnType<typeof stats>> = {};
  for (const id of SFX_IDS) out[id] = stats(await renderSfx(id));
  for (const k of SYSTEM_TRACK_KINDS) out[`system/${k}`] = stats(await resolveAudio(`placeholder:system/${k}`));
  for (const c of CAST) out[`theme/${first(c)}`] = stats(await resolveAudio(`/assets/placeholder/themes/${c.id}.proc.json`));
  return out;
};

function AudioSection() {
  const [info, setInfo] = useState<string>("Click to render + play. First click unlocks WebAudio.");
  const go = async (label: string, url: string, loop = false) => {
    setInfo(`rendering ${label}…`);
    const t0 = performance.now();
    try {
      const buf = await resolveAudio(url);
      const st = stats(buf);
      setInfo(`${label} · ${st.sec}s · peak ${st.peakDb} dBFS · rms ${st.rmsDb} dBFS · rendered in ${Math.round(performance.now() - t0)} ms`);
      play(buf, loop);
    } catch (err) {
      setInfo(`${label} failed: ${(err as Error).message}`);
    }
  };
  const groups = useMemo(() => {
    const g: Record<string, SfxId[]> = {};
    const group = (id: SfxId) =>
      /^(vs|round|verdict|summon)_/.test(id) ? "ceremony" : id.split("_")[0];
    for (const id of SFX_IDS) (g[group(id)] ??= []).push(id);
    return g;
  }, []);
  return (
    <Section id="audio" title="Procedural audio (SKETCH)" kicker="14">
      <p className={s.mono}>{info}</p>
      {Object.entries(groups).map(([k, ids]) => (
        <Row key={k} label={k}>
          {ids.map((id) => (
            <Button key={id} size="sm" variant="secondary" onClick={() => void go(id, `placeholder:sfx/${id}`)}>
              {k === "ceremony" ? id : id.slice(k.length + 1)}
            </Button>
          ))}
        </Row>
      ))}
      <Row label="System tracks">
        {SYSTEM_TRACK_KINDS.map((k) => (
          <Button key={k} size="sm" iconRight={<MusicIcon />} onClick={() => void go(k, `placeholder:system/${k}`, true)}>{k}</Button>
        ))}
      </Row>
      <Row label="Character themes (.proc.json)">
        {CAST.map((c) => (
          <PaletteScope key={c.id} paletteId={c.paletteId} as="span">
            <Button size="sm" onClick={() => void go(`${first(c)}'s Theme`, `/assets/placeholder/themes/${c.id}.proc.json`, true)}>
              ♪ {first(c)} · SKETCH
            </Button>
          </PaletteScope>
        ))}
        <Button size="sm" variant="ghost" onClick={() => { playing?.stop(); playing = null; setInfo("stopped"); }}>■ Stop</Button>
      </Row>
    </Section>
  );
}
