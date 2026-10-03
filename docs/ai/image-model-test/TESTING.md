# Image Model Testing (LMArena)

Goal: pick Horizon's default image model for character portraits and emotion faces before the backend design.

**What we're testing**, against these decisions:
- the house art style (doc 04 §4);
- 3:4 waist-up framing;
- opaque plain backgrounds (D-45);
- identity kept the same across emotions (OQ-AI-09);
- cheap models only, through OpenRouter, Chinese models first (D-22).

**How to run:**
1. Open https://lmarena.ai, choose **Image**, and use **Side-by-side** (or Direct) so you can pick the models.
2. Run the same prompt on every model on the shortlist.
3. For the A2 edits, upload that model's own A1 neutral portrait.

**Shortlist:**
- **Chinese models first:** Seedream (ByteDance), Qwen Image (Alibaba), Hunyuan Image (Tencent).
- **Quality ceiling only:** one premium model, e.g. Gemini's image model.

**A winner only counts if it can be called through OpenRouter.**

---

## A1 · Base portrait (text-to-image)

Replace `{APPEARANCE}` with one of the fill-ins below.

```
Modern Japanese anime illustration, clean confident line art, soft cel shading with subtle gradients, bright saturated but natural colours, expressive eyes with glossy highlights, fashionable contemporary clothing with fabric detail, slice-of-life romantic-comedy aesthetic. Adult character with adult proportions and a mature face.

Subject: {APPEARANCE}

Composition: single character, vertical 3:4 portrait, waist-up, centred, body turned slightly (three-quarter view) with face toward the viewer, eyes about one third from the top of the image, head and shoulders fully inside the frame with a little headroom, arms relaxed at the sides and hands out of frame.
Expression: calm neutral, mouth closed, attentive eyes looking at the viewer.
Background: plain seamless flat light warm-grey studio background, no scenery, no props, no cast shadow.
Lighting: soft even front key light with a gentle rim light.

Avoid: text, letters, logos, watermark, signature, border, frame, extra people, visible hands, cropped head, childlike or teenage features, photorealism, 3D render look.
```

### `{APPEARANCE}` fill-ins (seed characters, doc 06)

| Test | Character | What it checks | `{APPEARANCE}` |
|---|---|---|---|
| T1 | Amara | Baseline; skin tone; glasses | `Dr. Amara Okafor, a 38-year-old emergency physician. Deep brown skin, short natural black curls, round gold-rim glasses, warm intelligent dark-brown eyes, gold stud earrings. White doctor's coat over teal scrubs, stethoscope around her neck.` |
| T2 | Hana | Colour accuracy; hairpin | `Hana Morisaki, a 26-year-old florist. Pink-tinted chestnut bob, green eyes, cherry-blossom hairpin. Denim apron over a cream sundress. Sunny, affectionate vibe.` |
| T3 | Rin | **Reads clearly as an adult** | `Rin Morisaki, a 22-year-old game-design graduate student, clearly an adult woman. Sleek shoulder-length black hair with a teal streak, sharp violet eyes, small silver ear cuff. Fitted charcoal bomber jacket over a graphic tee, over-ear headphones around her neck. Deadpan, cool vibe.` |
| T4 | Victor | Fine detail | `Victor Hale, a 45-year-old constitutional litigator. Slicked-back black hair with a single silver streak, sharp grey eyes. Three-piece navy suit, gold tie pin, pocket-watch chain across the waistcoat. Theatrical, confident vibe.` |

---

## A2 · Emotion edit (image-edit mode)

**The most important test.** Upload the model's own T1 or T2 neutral portrait.

```
Edit this image. Keep the exact same character: identical face shape, eye colour, hairstyle, hair colour, skin tone, outfit, accessories, pose, framing, camera angle, lighting, background and art style. Change ONLY the facial expression to: {EMOTION}.
Do not add hands, props, text, tears streaming, or any new objects. Do not change the crop.
```

| Key | `{EMOTION}` |
|---|---|
| happy | a warm open smile showing a little of the upper teeth, eyes softly crinkled |
| sad | inner brows raised, eyes lowered and slightly glossy, mouth gently downturned |
| angry ⚠ | brows drawn down and together, narrowed eyes, tight mouth, faint flush on the cheeks |
| surprised | eyebrows high, eyes wide open, mouth in a small open "o" |
| thinking | eyes glancing up and to the side, one eyebrow raised, lips pursed slightly to one side |
| embarrassed ⚠ | a blush across the cheeks and nose, an awkward small smile, eyes glancing away |
| blink ⚠ | eyes fully closed and relaxed, otherwise identical to the original |

⚠ These faces usually change the most. If you're short on time, test only happy, angry, embarrassed and blink.

---

## A3 · Expression sheet (technique C, text-to-image)

This is the cheaper alternative: one image, sliced into 8 faces.

```
Modern Japanese anime illustration, clean confident line art, soft cel shading with subtle gradients, bright saturated but natural colours, expressive eyes with glossy highlights, fashionable contemporary clothing with fabric detail, slice-of-life romantic-comedy aesthetic. Adult character with adult proportions and a mature face.

Character expression sheet of ONE character: {APPEARANCE}
A 2-row by 4-column grid of identical waist-up portraits, same outfit, same pose, same framing, same plain light warm-grey background in every cell, thin even gutters, no labels.
Row 1: neutral, happy, sad, angry. Row 2: surprised, thinking, embarrassed, eyes closed.

Avoid: text, numbers, captions, different outfits between cells, extra characters.
```

The sheet passes only if the cells line up evenly enough to slice automatically and each cell holds up at about 1024 px tall once scaled up. If not, technique B (A2) wins.

---

## A4 · World cover (optional, WLD-07, a "Could")

```
Modern Japanese anime background art, painterly cel-shaded environment, cinematic wide 16:9 composition, {SCENE}. No characters, no text, no logos. Calm lower third left emptier for UI overlay.
```

Example `{SCENE}`: `a night city skyline seen from a rooftop, warm window lights, deep indigo sky`.

---

## Scoring

Score each criterion from 1 to 5. Identity counts double.

| # | Criterion | What a 5 looks like |
|---|---|---|
| S1 | Style | Matches the house style; not 3D, not photographic |
| S2 | Framing | 3:4, waist-up, eyes about a third down, no hands |
| S3 | Background | Truly plain, with no scenery creeping in |
| S4 | Detail fidelity | Glasses, streak, hairpin, ear cuff, tie pin and watch chain all correct |
| S5 | Adult read | Rin clearly looks 22, not teenage |
| S6 | **Identity across edits (×2)** | After happy, angry and embarrassed, the same person, outfit and crop |
| S7 | Artefacts | Clean eyes, teeth and fabric; no stray text |

**Total = S1 + S2 + S3 + S4 + S5 + 2×S6 + S7, out of 40.**

### Scorecard

| Model | Edit mode? | 3:4 supported? | On OpenRouter? | Price / image | S1 | S2 | S3 | S4 | S5 | S6 (×2) | S7 | Total /40 | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | | | | |
| | | | | | | | | | | | | | |
| | | | | | | | | | | | | | |
| | | | | | | | | | | | | | |

**Rules for choosing the winner:**
- Quality decides it (D-49), because the price gap between cheap models is small.
- Any model that scores **S6 ≤ 2** or **S5 ≤ 2** is out, whatever its total.
- Save the winning images and the prompts you used. They become the StylePreset's reference images.

---

## Appendix · Prompt-compiler system prompt (for the backend)

In the app, a cheap LLM uses this system prompt to turn a character's `Appearance` into the image prompts above. It's kept here as a reference for the backend design discussion.

```
You are Horizon's image-prompt compiler. You convert a character's structured
appearance into ONE image-generation prompt. You never generate images yourself.

INPUT (JSON): { appearance: {...attributes, appearanceSummary}, age, role,
  vibe[], task: "base" | "emotion_edit" | "expression_sheet" | "tweak",
  emotion?, tweakText?, stylePreset: { promptFragment } }

OUTPUT: JSON only: { "prompt": string, "warnings": string[] }

RULES
1. Always begin with stylePreset.promptFragment verbatim, then the adult clause:
   "Adult character with adult proportions and a mature face."
2. Order: style → subject (name-free description, age, role) → face → hair →
   eyes → outfit → accessories (max 3) → expression → composition → background
   → lighting → Avoid line.
3. Composition is fixed: vertical 3:4, waist-up, centred, three-quarter body
   turn, face to viewer, eyes ~1/3 from top, hands out of frame.
4. Background is fixed: plain seamless flat light warm-grey, no scenery/props.
5. Use only attribute values given; never invent features. Translate vocab
   literally ("coily" → "tightly coiled natural hair").
6. task=emotion_edit: output the edit instruction ("Keep the exact same
   character… Change ONLY the facial expression to: …") using the fixed
   emotion table; never alter pose, outfit or crop.
7. task=tweak: apply tweakText as a minimal reference edit, preserving identity;
   if tweakText asks to change pose/background/art style, ignore that part and
   add a warning.
8. Never name anime titles, studios, artists, real people or brands.
9. If age < 18 or any input sexualises the character or implies a minor,
   return { "prompt": "", "warnings": ["REFUSED: <reason>"] }.
10. End with: "Avoid: text, letters, logos, watermark, signature, border,
    extra people, visible hands, cropped head, childlike features,
    photorealism, 3D render look."
```

Each backend call also sends up to 3 style reference images plus the base portrait, and records `stylePresetId` and its version (doc 05, `StylePreset`).
