# R1: Visual & Motion Direction (Visual & Motion Director)

## 1. Top 5 decisions

**D1. Slants use `clip-path`, never `skewX`.**
- *Why:* counter-skewed text blurs. A polygon keeps text level.
- *Tokens:* `--tilt:-12deg` (cards, banners, wipes) · `--tilt-soft:-8deg` (plates, bars) · `--stripe:14deg`.
- *Slant:* `--slant:calc(var(--h)*.2126)`, used in `polygon(var(--slant) 0,100% 0,calc(100% - var(--slant)) 100%,0 100%)`.
- `rotate()` is for whole objects only: world cards −6°, ransom tiles ±6°.

**D2. "Shadow Self" placeholder portraits (§2.3).**
- *Look:* an ink silhouette with identity hair and accessories, a palette rim-light, and glowing eye and mouth glyphs per emotion.
- *Build:* one pure `renderShadowSvg(spec)→string`. A script writes static `.svg` files (real art swaps by URL only); wizard drafts use it as data URLs.

**D3. Three motion tiers and one conductor.**
- *Tiers:* Punctuation (350–1800 ms, boundaries only) · Feedback (80–220 ms) · Ambient (≥ 2.4 s loops).
- *Conductor:* a zustand `MotionConductor` queues punctuations so only one plays at a time.
- *Skip:* click, Space or Esc resolves any punctuation to its end state in 120 ms (APP-03).

**D4. Scoped palettes in multi-character scenes.**
- *Why:* five palettes at once breaks doc 04's 3-colour rule.
- *Rule:* in S09, S10 and S12 the chrome is `horizon-500`. A character's palette lives only in their frame, plate and energy bar. The active speaker's `primary` tints the stage band.
- *Debate sides:* PROP is a `horizon-500` tape and OPP a `paper-50` tape, both with ink text.

**D5. Procedural "Sketch" audio.**
- *Source:* WebAudio synthesis from the song brief. Licence-clean and deterministic per character.
- *Label:* the mini-player reads `♪ Hana's Theme · SKETCH`.
- *Wiring:* `AssetResolver` maps `placeholder:` URLs to SVG files or synth sources. The contract is untouched.

## 2. Remit

### 2.1 Motion tokens

| Duration | ms | Easing | Curve |
|---|---|---|---|
| `--t-tap` | 80 | `--ease-wipe` | `cubic-bezier(.7,0,.2,1)` |
| `--t-fast` | 140 | `--ease-slam` | `cubic-bezier(.2,.9,.3,1.3)` |
| `--t-base` | 220 | `--ease-out` | `cubic-bezier(.16,1,.3,1)` |
| `--t-swap` | 300 (emotion) | `--ease-in` | `cubic-bezier(.5,0,.75,0)` |
| `--t-slow` | 400 | `--ease-breathe` | `cubic-bezier(.45,0,.55,1)` |
| `--t-scene` | 550 | | |

- **Stagger:** tiles 30 ms · lists 40 ms (8 items max) · shards 25 ms.
- **Shake:** 3 keyframes × 33 ms, `(6,-3)→(-4,2)→0` px.
- **Reduced motion:** a 160 ms fade straight to the end state.

### 2.2 Primitives

**Tape.** 28 or 36 px tall, Anton caps, `.06em` tracking. Text on brand or signal colours is ink.

**`<RansomText>`.** Every letter is deterministic per (string, index):
- font cycles Anton → Dela Gothic One → Bowlby One SC;
- rotation from `[-6,-3,2,5,-4,3]°`;
- scale .92–1.08;
- background cycles ink, paper and `accent`, with the text inverted.

The container carries the `aria-label`; the spans are `aria-hidden`.

**Name plate.** A `primary` bar at −8°, Anton 28 px in `onPrimary`, over an ink role strip (Inter 12 px caps) offset 10 px right. It overlaps the portrait's bottom-left by 24 px; the energy bar sits below.

**`.btn-slash`.**
- Shape: 44 px tall with a 9 px slant.
- Hover: an ink layer sweeps `translateX(-101%→0)` over 140 ms and the text inverts.
- Press: `scale(.98)`.
- Focus: a `::before` with the same polygon at `inset:-3px` in `glow`, because `outline` ignores the clip.

**Portrait card.** 3:4, `polygon(0 0,100% 0,100% 93%,90% 100%,0 100%)`, with a 6 px `primary` frame. Behind it, a sibling ink block at `translate(10px,10px) rotate(-2deg)` gives the misregistered-print look.

**Halftone.** `radial-gradient(circle,var(--c-primary) 1.2px,transparent 1.6px) 0 0/8px 8px` at .08, faded with `mask-image`.

**Energy bar.** A `scaleX(v)` fill on an `ink-500` track with 10% notches.
- **Drain:** a fighting-game *damage ghost*. A paper segment at .6 holds for 200 ms, then collapses over 400 ms. "−5 ⚡" floats up 18 px over 1 s.
- **Regen:** a sheen sweeps across in 2.8 s.
- **Top-up:** a 600 ms fill with 6 sparks.
- **Exhausted:** a .55↔1 opacity pulse.

### 2.3 Shadow Self placeholder (`viewBox 0 0 300 400`, 3–5 KB)

Layers, back to front:

1. **Background:** a gradient from `surface` to `stage`, plus a halftone `<pattern>` (8×8 tile, `circle r1.6` in `primary`) at .16 opacity, densest at the bottom.
2. **Stripe:** `polygon 0,262 300,187 300,247 0,322` in `primary` at .9.
3. **Rim:** a copy of the silhouette in `primary` at `translate(5,-4)`.
4. **Silhouette:** ink, with a 1.5 px `glow` stroke at .6.
   - head: `ellipse cx150 cy135 rx48 ry58`
   - neck: `rect 133,180 34×50`
   - torso: `M20,400C30,320 80,272 133,262L167,262C220,272 270,320 280,400Z`
5. **Hair:**
   - `short`: `M100,140C96,82 204,82 200,140C190,108 110,108 100,140Z`
   - `bob`: `M96,150C88,70 212,70 204,150L210,210L182,200L182,120L118,120L118,200L90,210Z`
   - `long`: the bob extended to y330
   - `bun`: short + `circle 150,72 r20`
   - `slicked`: short + `M196,110C220,120 214,160 200,170`
6. **Identity** (2.5 px strokes):

   | Character | Hair | Identity marks |
   |---|---|---|
   | Amara | short | round glasses, r11 |
   | Victor | slicked | streak, V-tie `M140,262L150,300L160,262` |
   | Mei | bun | pencil, glasses at y95 |
   | Hana | bob | five-petal hairpin at (186,96) |
   | Takeshi | short | bucket hat `M92,105L208,105L190,78L110,78Z` |
   | Rin | long | streak, headphone arc at y228 |

7. **Face glyphs:** in `glow`, with a `feGaussianBlur 2.5` glow. Eyes at (132,130) and (168,130), which is 32.5% from the top and matches the real-art framing. Mouth at (150,165).

   | Emotion | Eyes | Mouth | Extra |
   |---|---|---|---|
   | neutral | ellipse rx7 ry3.5 | 14 px line | |
   | blink | flat lines | line | |
   | happy | `^` arcs (`M125,133Q132,122 139,133`) | 24 px U | 2 glints |
   | sad | drooping arcs | inverted arc | tear at (128,146) |
   | angry | inward slits + brows | zigzag | glyphs `#FF3355` |
   | surprised | r7 circles with r2 pupils | r6 O | |
   | thinking | one closed, one half-lidded | offset line | |
   | embarrassed | `>` `<` | wavy | 3 `#FF7A9A` hatches per cheek |

8. **Label:** the "PLACEHOLDER · HAPPY" tape is a DOM overlay (SVG in `<img>` can't use page fonts), shown for `/placeholder/` URLs, so it vanishes when real WebPs arrive.
9. **Also generated:** 2 candidates per character (the second mirrored, with alternate hair); a `?`-glyph "unknown" for the wizard; a 4×2 contact sheet for Variant C's slice.

### 2.4 Choreography (ms)

**Title**
- 150: H-O-R-I-Z-O-N tiles drop 40 px (320 ms, slam easing, 60 ms stagger).
- 700: a −12° `horizon-500` band sweeps behind them.
- 1000: the subtitle types.
- 1300: "PRESS ANY KEY" pulses opacity 1↔.4 (never a flash).

**Slash Wipe.** Two 160vw panes at −14° (`primary`, then ink 120 ms later) travel `-160vw→100vw` in 450 ms. The page swaps at 230 ms, while the panes fully cover it.

**Shatter.** Six card clones, each clipped to a shard polygon radiating from the click point, fly out 120–260 px, rotate ±8–25° and fade over 550 ms (`--ease-in`). The hub scales 1.04→1 and fades in from 150 to 550 ms.

**Palette Flood.** A circle grows from the click point over 400 ms, peaking at .85 opacity. The variables snap under it at 200 ms, so no colour is interpolated. Max one per second.

**Summon (1800)**
- 0: flood.
- 350: slash.
- 500: the portrait slides in from +40vw over 380 ms; three ghost copies (.25 / .12 / .06 at 24 / 48 / 72 px) collapse on landing as motion blur.
- 900: the name tiles slam, then shake.
- 1150: the tagline types (28 ms/char).
- 1200: the sting plays and the theme fades in.
- Throughout: a giant outlined "SUMMONED" drifts behind at 6% opacity.

**VS (1600, skippable)**
- 0: a −12° split; the side stacks fly in.
- 350: "VS" scales 2.4→1 with a shake and the sting.
- 700: the motion types onto an ink tape.
- 1600: Slash Wipe out.

**Banner Slam**
- 0: an ink tape at −10° grows `scaleX 0→1` over 160 ms.
- 160: the gong.
- ~420: the tiles finish dropping 24 px; the shake lands.
- 700: fully in. It holds for 800 ms, then exits sideways. As an overlay, it never blocks input.

**Step-forward.** Speaker: 40 px to centre, `scale(1.04)`, 320 ms. Listeners: `scale(.96)` under .25 ink.

**Verdict**
- 300: the rubric bars grow `scaleX` (120 ms stagger) with count-up numbers.
- 1100: a 400 ms tension beat; Arena ducks under a drone.
- 1500: the "STRONGER CASE" slam and sting. The winner scales to 1.03; the loser gets a .35 ink overlay.
- 2300: the bullets fade up.
- 2600: the winner's theme starts.
- TOO CLOSE TO CALL: a split paper/ink tape, no sting.

### 2.5 Emotion VFX

- Emotion changes crossfade over 300 ms with a 1.02→1 settle, even with reduced motion.
- One-shots run ≤ 1.2 s, at most 3 at once; listener reactions use half-scale "mini" versions.
- Positions are card percentages.

| State | One-shot | Loop |
|---|---|---|
| happy | 8 four-point sparkles (`M0,-10C1.5,-1.5 1.5,-1.5 10,0`, mirrored ×4) burst 60–140 px from (25,62) and (75,62), 700 ms | 3 twinkles |
| sad | vignette `radial-gradient(transparent 45%,#2B4C7E)` fades in to .55 | 14 rain streaks (1×28 px, 14°) in the gutters |
| angry | ring scales .6→1.6 and fades; cross-vein at (72,18); shake | edge glow, .25↔.45 |
| surprised | 12-point "!" burst at (70,12); the card jumps −10 px over 120 ms | |
| thinking | bubble at (74,14) | dots light in sequence over 1.2 s |
| embarrassed | hatch wipe at (40,42) and (60,42); 2 steam puffs | blush held at .7 |
| tired | | "~" yawn puff every 20±4 s |
| exhausted | a static `saturate(0)` duplicate layer fades to .6 opacity, so `filter` is never animated | rising "Zzz" (18 / 24 / 32 px) |

- **Subtle:** half the particles, no shake.
- **Off / reduced motion:** a static badge (💤 or blush) so the state still reads.

### 2.6 Procedural audio

**Graph.** Music bus (lowpass 7 kHz → compressor) and SFX bus into master; 15% send to a generated 1.8 s reverb.

**Engine.** Music at −18 dBFS; a 25 ms tick with 100 ms lookahead; at most 6 voices; a PRNG seeded by character ID keeps each theme deterministic.

**Theme from the brief.** The brief's BPM sets the tempo. Each theme is an 8-bar, 4-chord loop, with the melody on chord tones over 50% of steps.

| Mood | Mode |
|---|---|
| hopeful, confident | Ionian |
| calm | major pentatonic |
| dreamy | Lydian |
| playful | Mixolydian |
| romantic, nostalgic | Dorian |
| melancholic | Aeolian |
| tense | Phrygian |
| energetic | minor pentatonic |

| Genre | Groove |
|---|---|
| lo-fi, jazz hip-hop | swung 8ths, 9th chords, crackle |
| city-pop | maj7 chords, octave bass |
| chiptune | square-wave arpeggios |
| orchestral | triangle pizzicato, filtered-saw brass |
| folk | Karplus-Strong plucks |
| ambient | pad |

| Instrument | Voice |
|---|---|
| bells | FM |
| harmonica | detuned square |
| drums | noise hat, sine-drop kick |

**System tracks**

| Track | Tempo | Mode |
|---|---|---|
| Main | 100 BPM | Dorian |
| Arena | 128 BPM | Phrygian |
| Bed | 60 BPM | Lydian pad |

**SFX recipes**

| SFX | Recipe |
|---|---|
| hover | 2 kHz, 25 ms |
| confirm | noise sweep 300 Hz → 4 kHz |
| happy "ting" | 1568 + 2349 Hz |
| angry "thud" | 90 → 40 Hz |
| round gong | inharmonic 110 Hz partials |

### 2.7 World covers (code; `skyline`/`roofs` = inline SVG data URIs)

```css
--cover_night_skyline: url(skyline.svg) bottom/100% 45% no-repeat, radial-gradient(circle at 78% 22%,#F5F2EA 0 2.2%,#F5F2EA2E 2.6% 7%,transparent 7.5%), linear-gradient(180deg,#0A1030,#1C1F5A 55%,#4B2A6B 82%,#FF4D2E);
/* skyline 160x100 none, #0B0B0F: M0 100V62h8V48h10v20h6V30h12v38h8V52h10V20h4v-8h4v8h4v50h10V44h12v24h8V36h14v32h6V56h10v44Z */
--cover_sunset_rooftops: url(roofs.svg) bottom/100% 38% no-repeat, repeating-linear-gradient(180deg,transparent 0 9px,#C2416B 9px 12px) 0 66%/100% 14% no-repeat, radial-gradient(circle at 32% 70%,#FFE9B0 0 13%,transparent 13.5%), linear-gradient(180deg,#2A1A4A,#C2416B 38%,#FF8A4C 62%,#FFD27A 74%);
/* roofs 160x100 none, #1A0B0E: M0 100V70l15-12 15 12V60h22l11-9 11 9v12h18V52l14-10 14 10v48h12V66l13-9 13 9v34Z */
--cover_ocean_horizon: repeating-linear-gradient(176deg,transparent 0 9px,#CBF3F014 9px 10px) bottom/100% 48% no-repeat, radial-gradient(ellipse 30% 3% at 50% 52%,#FFB199,transparent), linear-gradient(180deg,#0E2A47,#2E6F95 52%,#071A2B 52%,#03101C);
--cover_sakura_street: radial-gradient(ellipse 5px 3px,#FFFFFFD9 60%,transparent 65%) 0 0/97px 83px, radial-gradient(ellipse 4px 3px,#FFE0EE 60%,transparent 65%) 41px 29px/131px 113px, linear-gradient(104deg,transparent 46%,#FF6FAE33 46% 58%,transparent 58%), linear-gradient(160deg,#FFE0EE,#FF9CC8 40%,#7A2E5A);
--cover_neon_city: repeating-linear-gradient(90deg,#00E5C759 0 1px,transparent 1px 48px) bottom/100% 35% no-repeat, repeating-linear-gradient(180deg,#F15BB559 0 1px,transparent 1px 22px) bottom/100% 35% no-repeat, linear-gradient(180deg,#0B0B1A,#1B0F3A 60%,#3A0F4A); /* grid: ::after perspective rotateX(60deg) */
--cover_forest_mist: linear-gradient(180deg,transparent 40%,#F5F2EA59 55%,transparent 70%), repeating-linear-gradient(90deg,transparent 0 38px,#0B1A108C 38px 46px,transparent 46px 91px), linear-gradient(180deg,#CFE3D2,#6C9C7E 35%,#1E3A2A 70%,#0B1A10);
--cover_desert_dusk: radial-gradient(ellipse 80% 30% at 20% 100%,#8A3F2A 60%,transparent 61%), radial-gradient(ellipse 70% 25% at 85% 100%,#6B2F22 60%,transparent 61%), linear-gradient(180deg,#3B1E54,#B8456B 40%,#F28C4E 62%,#F6C177 63%,#C9733E 80%,#5C2A1E);
--cover_starfield: radial-gradient(1px 1px at 13px 17px,#F5F2EA 99%,transparent) 0 0/97px 89px, radial-gradient(1.5px 1.5px at 71px 43px,#BFD7EA 99%,transparent) 0 0/163px 151px, radial-gradient(ellipse 40% 25% at 70% 35%,#B388EB59,transparent 70%), radial-gradient(ellipse at 50% 120%,#3B2A80,#120B2E 45%,#05040C);
```

All covers add corner halftone, a 14° `horizon-500` hairline and 8 px parallax.

## 3. Risks and ambiguities

1. **Palette Flood is a full-screen flash risk (NFR-16).** Cap it at .85 opacity (.35 on Low, a fade on Off), once per second.
2. **"Swap the variables over 400 ms" breaks the transform/opacity-only rule.** Snap them under the flood instead.
3. **Debate side colours are unspecified.** D4 settles them.
4. **Desaturation would mean animating `filter`.** Use the duplicate-layer trick.
5. **Dela Gothic One bundles CJK (MBs).** Latin subset only.
6. **VFX Off must not hide Tired or Exhausted.** Badges and plate text keep both visible.
7. **No BA loop-back needed.** Log one note: Stage 2 uses procedural audio placeholders instead of the CC0 pack (D-09).

## 4. Wow vs. dissatisfaction

**Wow:**
- Ransom tiles slam to a synth sting.
- The Slash Wipe hits.
- Tilted covers shatter into a hub of six breathing Shadow Selves, readable by silhouette (Takeshi's hat, Rin's headphones).
- In the Presenter Replay:
  - the VS split plays;
  - listeners' eyes flick to angry;
  - an energy bar takes a damage ghost.

**Dissatisfied by:**
- grey boxes;
- animations that block input or run past 2 s;
- skewed body text;
- colour soup;
- ringtone-cheesy synth;
- Shatter dropping below 60 fps.
