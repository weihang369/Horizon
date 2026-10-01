# 04: Visual, Motion & Audio Direction

**Inspiration:** Persona 5 (stakeholder's pick) for the UI language; modern Japanese romantic-comedy anime for the characters. **Game-like, not a game:** React + CSS/SVG/Canvas/WebAudio, no game engine.

## 1. Design principles

1. **Ink, paper and one loud colour.** Near-black ink, warm paper white, and **one** accent from the active character's palette (or the Horizon brand accent in the hub). At most 3 colours on screen besides the portrait.
2. **Nothing is level.** Panels, plates, buttons and banners sit at −8° to −14°, or use diagonal clip-paths. **Text inside is always horizontal; body text is never skewed.**
3. **Motion is punctuation.** Big kinetic moments happen at boundaries (screen change, round start, emotion change, Summon). The steady state is calm: just idle breathing.
4. **Readability beats style for content.** Style lives in the chrome, not in paragraphs (Readable Mode).
5. **Inspired by, not copied from.** Use the *techniques* (diagonal cuts, ransom-note tiles, halftone, cut-ins) but no Persona 5 fonts, assets, logos, exact colours, traced layouts or wording. The public verb for approving a character is **"Summon"**.
6. **Make the AI visible.** The Insight drawer, probability bars and the cost HUD are first-class UI, not debug views.

## 2. House tokens (independent of character)

| Token | Hex | Use |
|---|---|---|
| `ink-900` | `#0B0B0F` | App background |
| `ink-700` | `#1A1A22` | Panels |
| `ink-500` | `#2C2C38` | Borders, dividers |
| `paper-50` | `#F5F2EA` | Primary text on dark |
| `paper-300` | `#BDB8AC` | Secondary text |
| `horizon-500` | `#FF4D2E` | Brand accent (hub, moderator, system UI) |
| `horizon-300` | `#FFB199` | Brand accent, light |
| `signal-ok` | `#3DDC97` | Success |
| `signal-warn` | `#FFC53D` | Warning |
| `signal-err` | `#FF3355` | Error tape |
| `on-brand` / `on-signal` | `#0B0B0F` (= `ink-900`) | **All text on brand or signal tapes is ink**: paper text on these colours fails WCAG (e.g. 2.95:1 on `horizon-500`) |
| `energy-amber` | `#FFC53D` | Energy bar < 40% |
| `energy-red` | `#FF3355` | Energy bar < 20% (Tired) |

**Typography** (OFL fonts, **self-hosted in the repo**, no runtime calls to Google Fonts):
- Display and banners: **Anton**.
- Ransom-note tiles (titles and banners only): mix **Anton**, **Dela Gothic One** and **Bowlby One SC** per letter, with ±6° rotation and alternating ink/paper/accent backgrounds.
- UI and body: **Inter** (14–16 px body, 1.55 line height).
- Insight and monospace: **JetBrains Mono**.

## 3. Fixed palette catalogue (12)

Characters pick **one** palette from this fixed list (an AI may *choose* from it, never invent one). The UI swaps CSS variables over 400 ms. A Palette Flood plays only on a **committed** change (palette clicked, character switched). Hover previews are an instant colour swap with no flood (photosensitivity).

Every palette shares `text = #F5F2EA`. All values below were checked against WCAG: `onPrimary`/`primary` ≥ 4.5:1, `primary` vs `ink-900` ≥ 3:1 (UI components), and paper text on `stage` ≥ 15.9:1.

| id | Name | primary | secondary | accent | stage | surface | onPrimary | glow | Fit |
|---|---|---|---|---|---|---|---|---|---|
| `pal_crimson_rebel` | Crimson Rebel | `#E63946` | `#FFD6D9` | `#FFD23F` | `#1A0B0E` | `#2A1418` | `#1A0B0E` | `#FF6B76` | Bold leaders |
| `pal_sakura_pop` | Sakura Pop | `#FF6FAE` | `#FFE0EE` | `#7A2E5A` | `#1C0F17` | `#2D1825` | `#1C0F17` | `#FF9CC8` | Sweet, romantic |
| `pal_ocean_clinic` | Ocean Clinic | `#2EC4B6` | `#CBF3F0` | `#FF9F80` | `#071A1F` | `#0F2A31` | `#071A1F` | `#6FE3D8` | Calm, medical |
| `pal_royal_verdict` | Royal Verdict | `#6E5FE6` | `#D9D4FF` | `#F2C14E` | `#100C26` | `#1C1740` | `#FFFFFF` | `#9488F0` | Authority, law |
| `pal_golden_ledger` | Golden Ledger | `#D4A017` | `#FFF3C4` | `#2F5D8A` | `#17130A` | `#262014` | `#17130A` | `#F0C64A` | Analytical, academic |
| `pal_citrus_spark` | Citrus Spark | `#FF9F1C` | `#FFE8C2` | `#2EC4B6` | `#1A1308` | `#2A2010` | `#1A1308` | `#FFC066` | Energetic builders |
| `pal_forest_sage` | Forest Sage | `#3A9D5D` | `#D4EDC2` | `#F4A259` | `#0B1A10` | `#14291B` | `#0B1A10` | `#6CCB8C` | Grounded elders |
| `pal_midnight_ink` | Midnight Ink | `#6286BA` | `#BFD7EA` | `#EE6C4D` | `#0A111C` | `#142033` | `#0A111C` | `#8FAEDB` | Serious, strategic |
| `pal_lavender_dream` | Lavender Dream | `#B388EB` | `#F1E3FF` | `#FF8FAB` | `#150F1F` | `#241A33` | `#150F1F` | `#D2B5FF` | Dreamy, artistic |
| `pal_neon_arcade` | Neon Arcade | `#00E5C7` | `#C9FFF6` | `#F15BB5` | `#0B0B1A` | `#16162E` | `#0B0B1A` | `#5CFFE6` | Gamer, techy |
| `pal_ember_ash` | Ember Ash | `#FF5E3A` | `#FFD0C2` | `#8A8A99` | `#170D0A` | `#281814` | `#170D0A` | `#FF8A6B` | Intense, rebellious |
| `pal_frost_byte` | Frost Byte | `#7FD1FF` | `#E6F6FF` | `#A06CD5` | `#0A1520` | `#132536` | `#0A1520` | `#B5E6FF` | Cool, precise |

Rules:
- Paper text sits on `stage`, `surface` or ink, never on `primary` (except name plates and buttons, which use `onPrimary`).
- Accent colours are decorative (sparks, VFX). Focus rings use `glow`.

## 4. Character presentation

- **Portraits are opaque (D-45).** The cheap image models cannot output transparent backgrounds, so **design the framed card as the primary treatment**: a 3:4 card with a skewed palette-coloured frame, or a soft radial mask that fades the plain background into the stage. Do not design layouts that depend on cut-out characters.
- **Layer stack (back → front):**
  1. Stage: `stage` colour + halftone dots in `primary` at 8% + a 14° stripe.
  2. Stage VFX **around** the card: rain streaks, glow, Zzz drift. *(They can't sit behind an opaque portrait.)*
  3. Portrait card (framed or radially masked).
  4. Front VFX over the card: symbols, sparkles, blush hatching.
  5. Name plate + **energy bar**.
- **Framing:** waist-up, 3:4, eyes at 30–35% from the top. Pose, framing and outfit are **identical across emotions** (a constraint on generation).
- **Sprite size:** ~768–1024 px tall WebP, ≤ 250 KB.
- **House art style** (used in every image prompt; **does not name any anime or IP**): *"Modern Japanese anime illustration, clean confident line art, soft cel shading with subtle gradients, bright saturated but natural colours, expressive eyes with glossy highlights, fashionable contemporary clothing with fabric detail, slice-of-life romantic-comedy aesthetic, adult character with adult proportions, waist-up portrait, plain background."* It is versioned as `StylePreset` (doc 05).
- **Idle life:** breathing (scale 1.000→1.008, 4 s loop), parallax (6–10 px opposite the cursor), blink (neutral only, if the asset exists).

## 5. Transitions catalogue

| Name | Use | Spec |
|---|---|---|
| **Slash Wipe** | Default route change | A 14° band in `primary` sweeps L→R in 220 ms; content swaps underneath; an ink band follows at 120 ms; ~450 ms total |
| **Shatter** | World card → Hub | The card splits into 5–7 shards that fly out while the hub fades in; 550 ms |
| **Cut-in** | Speaker change | A horizontal strip (18% of viewport height) with an eyes crop + name; 300 ms in / 500 ms hold / 200 ms out (can be turned off) |
| **Palette Flood** | Committed theme change (palette click, character switch). **Never on hover** | A radial flood of the new `primary` from the click point; 400 ms |
| **Banner Slam** | Round, VS, verdict | Black tape slides in at −10°; tiles drop staggered by 30 ms; 2-frame shake; 700 ms |
| **Summon reveal** | Approve character | Palette flood → slash → portrait slides in with motion blur → name tiles slam → tagline types; ~1.8 s |

**Easing:**
- `cubic-bezier(0.7, 0, 0.2, 1)` for wipes.
- `cubic-bezier(0.2, 0.9, 0.3, 1.3)` for slams and plates.

**Performance and safety:**
- Animate only `transform` and `opacity`.
- At most 3 flashes per second, and flash intensity is configurable.
- Reduced motion replaces all transitions with fades of ≤ 200 ms.

## 6. Emotion VFX & SFX

| Emotion | One-shot VFX (on change) | Loop while active | SFX |
|---|---|---|---|
| neutral | none | none | none |
| happy | 6–10 four-point sparkles burst from the shoulders | faint shimmer | bright "ting" |
| sad | blue vignette fades in | slow rain streaks around the card | low piano note |
| angry | red pulse ring + cross-vein symbol (SVG) + 2-frame shake | subtle red edge glow | short thud |
| surprised | "!" burst + 120 ms jump (−10 px) | none | "pop" |
| thinking | "…" bubble near the head | dots pulse in sequence | soft tick |
| embarrassed | blush hatching on the cheeks + 2 steam puffs | blush stays | "fwip" |
| *exhausted* (energy state, not an emotion) | neutral face desaturated 60% + "Zzz" letters drifting up | slow Zzz loop; bar pulses red | soft snore "hmm" |
| *tired* (energy < 20%) | none | occasional small yawn puff (every ~20 s) | none |

**Crossfade:** starts ≤ 100 ms after the emotion event, completes ≤ 300 ms, with a 1.02→1.0 scale settle. **All participants' sprites are preloaded on session open.**

### 6.1 Energy bar (ENG-01)
- A slim skewed bar (−8°) directly under the name plate: 6 px tall on stage portraits, 10 px on chat and profile, with a `⚡ 640 / 1000` label in JetBrains Mono.
- Fill: palette `primary`; `energy-amber` below 40%; `energy-red` below 20%.
- **Regenerating:** a slow diagonal shimmer moves along the fill.
- **Drain:** the bar shrinks over 400 ms and a "−5 ⚡" label floats up and fades (1 s).
- **Top-up:** the bar refills with a spark burst along its length (600 ms) and a "recharge" SFX.
- **Rush hour chip:** a small `horizon-500` tape with ink text, "RUSH HOUR · 2× ⚡", next to the bars on stage and in the chat header.

## 7. Audio

### 7.1 Sources (stakeholder decision D-09)
| Audio | Source |
|---|---|
| **Character theme songs** | **AI-generated** per character (provider: OQ-AI-11) |
| System tracks: Horizon main theme, debate **Arena** track, ambient fallback bed | **Free / royalty-free library** (CC0 preferred), with credits in `ASSETS.md` |
| UI SFX (~20) | **Free CC0 pack** (e.g. Kenney audio packs; verify licence), with credits in `ASSETS.md` |

### 7.2 SFX catalogue (each ≤ 600 ms, normalised)
Hover tick · Confirm slash · Back/cancel · Toggle · Message send · First token received · Name-plate cut-in · Emotion change (×6) · Generation complete chime · Generation failed buzz · VS sting · Round gong · Verdict sting · Summon sting · Toast (per variant) · Pause menu open/close. A subtle per-token stream tick is **off by default**.

### 7.3 Music behaviour
- One **music bus** + one **SFX bus** (WebAudio), with master volume over both. Created after the first user gesture.
- **Loudness:** all tracks and SFX normalised to about −16 LUFS, so AI tracks don't jump in volume between characters.
- Fade-in 1.5 s; crossfade ≤ 2 s; ducking to 40% under stings with a 600 ms release.
- The same track continues across a character's profile ↔ chat.
- Multi sessions:
  - Group and Watch follow the speaker (minimum dwell 20 s) or the scene bed.
  - Debate plays Arena, then the verdict sting, then the theme of the highest-scoring debater on the stronger side. With no winner, Arena continues.
  - Follow speaker starts with the first speaker's theme. If a speaker has no theme, the current track keeps playing.
- Only one music track plays at a time. Mute and volume apply instantly. Nothing plays before the first interaction.

## 8. Insight drawer visual language

- A skewed panel from the right, in ink with a `horizon-500` header tape. Monospace values.
- Probability bars always show a **band** (HIGH ≥ 0.7, MED 0.4–0.7, LOW < 0.4) next to the number (e.g. `0.71 · HIGH`).
- The context budget is one horizontal stacked bar (system / persona / memory / knowledge / history / user / mode).
- A forced speaker shows a `FORCED BY YOU` tag instead of probabilities.
- Sections without data are not rendered.
- The Model section shows a **cache-hit chip** (e.g. `CACHE 80%`) and a `PEAK` / `OFF-PEAK` tag. The Energy section shows `−5 ⚡ · 742 / 1000` with a mini bar.
