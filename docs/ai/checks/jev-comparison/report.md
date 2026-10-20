# Jev comparison: typesafe/jev-1.13 vs typesafe/jev-1.14

- manifest `evals/baselines/jev-1.13-requests.json`; base runs 20261020T115058-decisions-87bccd, 20261020T115511-decisions-531247, 20261020T115515-deep-check-5010de, 20261020T115516-safety-f53e92; candidate runs 20261020T115517-decisions-f95225, 20261020T122058-decisions-e14ef8, 20261020T123958-deep-check-798eb8, 20261020T124020-safety-5019c8
- b: items only the base got right; c: only the candidate. A set **moves** only at McNemar p < 0.05.
- English items are scored (the English-first rule). Re-tuned: the candidate's value chosen on its dev rows, then read on test once, against the base at its live values.

## Canary
- typesafe/jev-1.13: 20/20 within tolerance of its own baseline
- typesafe/jev-1.14: 18/20 within tolerance of typesafe/jev-1.13's answers (its first run)
  - emotion-2: emotion:chr_seedAmara: choice neutral → thinking; emotion:chr_seedAmara: p[neutral] 0.62 → 0.42
  - message-18: standalone: p[p] 0.16 → 0.05

## Accuracy per set (paired)

| Set | Group | Live | Drop-in, test | Re-tuned, test (candidate's value) |
|---|---|---|---|---|
| emotion | emotion | floor 0.2 | 42/57 (0.61–0.83) vs 42/57 (0.61–0.83); b 2, c 2, McNemar p 1.000: no difference shown (the smallest 57 items could show: 0.11) | 0.2: 42/57 (0.61–0.83) vs 42/57 (0.61–0.83); b 2, c 2, McNemar p 1.000: no difference shown (the smallest 57 items could show: 0.11) |
| emotion | emotion (debate slice) | floor 0.2 | 12/19 (0.41–0.81) vs 12/19 (0.41–0.81); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 19 items could show: 0.32) | 0.5: 12/19 (0.41–0.81) vs 12/19 (0.41–0.81); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 19 items could show: 0.32) |
| reactions | reaction | floor 0.2 | 16/19 (0.62–0.94) vs 16/19 (0.62–0.94); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 19 items could show: 0.32) | 0.2: 16/19 (0.62–0.94) vs 16/19 (0.62–0.94); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 19 items could show: 0.32) |
| reactions | reaction (debate slice) | floor 0.2 | 3/3 (0.44–1.00) vs 3/3 (0.44–1.00); b 0, c 0, McNemar p 1.000: no difference shown | 0.2: 3/3 (0.44–1.00) vs 3/3 (0.44–1.00); b 0, c 0, McNemar p 1.000: no difference shown |
| who_speaks | who_first | floor 0.2 | 16/16 (0.81–1.00) vs 16/16 (0.81–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 16 items could show: 0.38) | 0.2: 16/16 (0.81–1.00) vs 16/16 (0.81–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 16 items could show: 0.38) |
| who_speaks | who_second | floor 0.3 | 17/19 (0.69–0.97) vs 17/19 (0.69–0.97); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 19 items could show: 0.32) | 0.3: 17/19 (0.69–0.97) vs 17/19 (0.69–0.97); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 19 items could show: 0.32) |
| who_speaks | who_scene | floor 0.2 | 46/75 (0.50–0.72) vs 45/75 (0.49–0.70); b 3, c 2, McNemar p 1.000: no difference shown (the smallest 75 items could show: 0.08) | 0.3: 46/75 (0.50–0.72) vs 45/75 (0.49–0.70); b 3, c 2, McNemar p 1.000: no difference shown (the smallest 75 items could show: 0.08) |
| who_speaks | who_next | floor 0.2 | 15/20 (0.53–0.89) vs 15/20 (0.53–0.89); b 2, c 2, McNemar p 1.000: no difference shown (the smallest 20 items could show: 0.30) | 0.2: 15/20 (0.53–0.89) vs 15/20 (0.53–0.89); b 2, c 2, McNemar p 1.000: no difference shown (the smallest 20 items could show: 0.30) |
| debate_member | debate member | floor 0.5 | 22/31 (0.53–0.84) vs 19/31 (0.44–0.76); b 3, c 0, McNemar p 0.250: no difference shown (the smallest 31 items could show: 0.19) | 0.5: 22/31 (0.53–0.84) vs 19/31 (0.44–0.76); b 3, c 0, McNemar p 0.250: no difference shown (the smallest 31 items could show: 0.19) |
| talk_finished | talk_finished | t_end 0.5 | 31/33 (0.80–0.98) vs 30/33 (0.76–0.97); b 3, c 2, McNemar p 1.000: no difference shown (the smallest 33 items could show: 0.18) | 0.5: 31/33 (0.80–0.98) vs 30/33 (0.76–0.97); b 3, c 2, McNemar p 1.000: no difference shown (the smallest 33 items could show: 0.18) |
| docs | docs | t_gate 0.45 | 22/26 (0.66–0.94) vs 22/26 (0.66–0.94); b 1, c 1, McNemar p 1.000: no difference shown (the smallest 26 items could show: 0.23) | 0.55: 22/26 (0.66–0.94) vs 22/26 (0.66–0.94); b 1, c 1, McNemar p 1.000: no difference shown (the smallest 26 items could show: 0.23) |
| docs | docs (t_confident) | t_confident 0.8 | 22/26 (0.66–0.94) vs 22/26 (0.66–0.94); b 2, c 2, McNemar p 1.000: no difference shown (the smallest 26 items could show: 0.23) | 0.9: 22/26 (0.66–0.94) vs 21/26 (0.62–0.91); b 2, c 1, McNemar p 1.000: no difference shown (the smallest 26 items could show: 0.23) |
| standalone | standalone | t_standalone 0.35 | 27/28 (0.82–0.99) vs 27/28 (0.82–0.99); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 28 items could show: 0.21) | 0.2: 27/28 (0.82–0.99) vs 27/28 (0.82–0.99); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 28 items could show: 0.21) |
| english | english | english 0.5 | 3/3 (0.44–1.00) vs 3/3 (0.44–1.00); b 0, c 0, McNemar p 1.000: no difference shown | —: 3/3 (0.44–1.00) vs 3/3 (0.44–1.00); b 0, c 0, McNemar p 1.000: no difference shown (no rule to tune: the drop-in figure repeats) |
| importance | importance (exact level) | levels 0 | 15/27 (0.37–0.72) vs 13/27 (0.31–0.66); b 2, c 0, McNemar p 0.500: no difference shown (the smallest 27 items could show: 0.22) | —: 15/27 (0.37–0.72) vs 13/27 (0.31–0.66); b 2, c 0, McNemar p 0.500: no difference shown (the smallest 27 items could show: 0.22) (no rule to tune: the drop-in figure repeats) |
| memory_guard | memory_guard | t_keep 0.35 | 47/48 (0.89–1.00) vs 45/48 (0.83–0.98); b 2, c 0, McNemar p 0.500: no difference shown (the smallest 48 items could show: 0.12) | 0.3: 47/48 (0.89–1.00) vs 44/48 (0.80–0.97); b 3, c 0, McNemar p 0.250: no difference shown (the smallest 48 items could show: 0.12) |
| earlier | earlier | t_gate 0.15 | 21/36 (0.42–0.73) vs 26/36 (0.56–0.84); b 5, c 10, McNemar p 0.302: no difference shown (the smallest 36 items could show: 0.17) | 0.05: 21/36 (0.42–0.73) vs 20/36 (0.40–0.70); b 1, c 0, McNemar p 1.000: no difference shown (the smallest 36 items could show: 0.17) |
| recall | recall | t_recall 0.5 | 30/38 (0.64–0.89) vs 30/38 (0.64–0.89); b 1, c 1, McNemar p 1.000: no difference shown (the smallest 38 items could show: 0.16) | 0.45: 30/38 (0.64–0.89) vs 31/38 (0.67–0.91); b 1, c 2, McNemar p 1.000: no difference shown (the smallest 38 items could show: 0.16) |
| same_fact | same_fact | t_same 0.5 | 40/41 (0.87–1.00) vs 40/41 (0.87–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 41 items could show: 0.15) | 0.05: 40/41 (0.87–1.00) vs 41/41 (0.91–1.00); b 0, c 1, McNemar p 1.000: no difference shown (the smallest 41 items could show: 0.15) |
| safety:input | tSteer | tSteer 0.7 | 96/100 (0.90–0.98) vs 94/100 (0.88–0.97); b 2, c 0, McNemar p 0.500: no difference shown (the smallest 100 items could show: 0.06) | 0.15: 96/100 (0.90–0.98) vs 96/100 (0.90–0.98); b 3, c 3, McNemar p 1.000: no difference shown (the smallest 100 items could show: 0.06) (leave-one-out (safety has no split)) |
| safety:care | tCare | tCare 0.3 | 35/35 (0.90–1.00) vs 35/35 (0.90–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 35 items could show: 0.17) | 0.3: 35/35 (0.90–1.00) vs 34/35 (0.85–0.99); b 1, c 0, McNemar p 1.000: no difference shown (the smallest 35 items could show: 0.17) (leave-one-out (safety has no split)) |
| safety:output | tFlag | tFlag 0.5 | 45/56 (0.68–0.89) vs 48/56 (0.74–0.93); b 0, c 3, McNemar p 0.250: no difference shown (the smallest 56 items could show: 0.11) | 0.8: 45/56 (0.68–0.89) vs 54/56 (0.88–0.99); b 1, c 10, McNemar p 0.012: **moves** (leave-one-out (safety has no split)) |
| safety:output | tBlock | tBlock 0.9 | 55/56 (0.91–1.00) vs 55/56 (0.91–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 56 items could show: 0.11) | 0.8: 55/56 (0.91–1.00) vs 54/56 (0.88–0.99); b 2, c 1, McNemar p 1.000: no difference shown (the smallest 56 items could show: 0.11) (leave-one-out (safety has no split)) |
| safety:motion | tMotion | tMotion 0.7 | 30/30 (0.89–1.00) vs 30/30 (0.89–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 30 items could show: 0.20) | 0.1: 30/30 (0.89–1.00) vs 30/30 (0.89–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 30 items could show: 0.20) (leave-one-out (safety has no split)) |
| safety:image | tImageLikeness | tImageLikeness 0.5 | 70/70 (0.95–1.00) vs 70/70 (0.95–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 70 items could show: 0.09) | 0.9: 70/70 (0.95–1.00) vs 70/70 (0.95–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 70 items could show: 0.09) (leave-one-out (safety has no split)) |
| safety:image | tImageNudity | tImageNudity 0.5 | 60/60 (0.94–1.00) vs 60/60 (0.94–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) | 0.1: 60/60 (0.94–1.00) vs 60/60 (0.94–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) (leave-one-out (safety has no split)) |
| safety:image | tImageGore | tImageGore 0.5 | 70/70 (0.95–1.00) vs 70/70 (0.95–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 70 items could show: 0.09) | 0.9: 70/70 (0.95–1.00) vs 70/70 (0.95–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 70 items could show: 0.09) (leave-one-out (safety has no split)) |
| safety:image | tImageYoung | tImageYoung 0.5 | 70/70 (0.95–1.00) vs 70/70 (0.95–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 70 items could show: 0.09) | 0.9: 70/70 (0.95–1.00) vs 70/70 (0.95–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 70 items could show: 0.09) (leave-one-out (safety has no split)) |
| safety:song | tSong | tSong 0.6 | 30/30 (0.89–1.00) vs 30/30 (0.89–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 30 items could show: 0.20) | 0.9: 30/30 (0.89–1.00) vs 30/30 (0.89–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 30 items could show: 0.20) (leave-one-out (safety has no split)) |

- sets that move: safety:output/tFlag
- the base's own dev re-tune today differs from its live value on: emotion (debate slice) (0.4 vs 0.2), debate member (0.6 vs 0.5), recall (0.3 vs 0.5), same_fact (0.05 vs 0.5)

### Drop-in by mode (test, every set with the item's `kind`)

- changed: 14/14 (0.78–1.00) vs 13/14 (0.69–0.99); b 1, c 0, McNemar p 1.000: no difference shown (the smallest 14 items could show: 0.43)
- changed_lossy: 4/4 (0.51–1.00) vs 3/4 (0.30–0.95); b 1, c 0, McNemar p 1.000: no difference shown
- debate: 38/55 (0.56–0.80) vs 35/55 (0.50–0.75); b 3, c 0, McNemar p 0.250: no difference shown (the smallest 55 items could show: 0.11)
- extend: 12/12 (0.76–1.00) vs 12/12 (0.76–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 12 items could show: 0.50)
- extended: 11/11 (0.74–1.00) vs 11/11 (0.74–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 11 items could show: 0.55)
- greeting: 4/4 (0.51–1.00) vs 4/4 (0.51–1.00); b 0, c 0, McNemar p 1.000: no difference shown
- group: 81/93 (0.79–0.92) vs 82/93 (0.80–0.93); b 2, c 3, McNemar p 1.000: no difference shown (the smallest 93 items could show: 0.06)
- line: 22/26 (0.66–0.94) vs 21/26 (0.62–0.91); b 1, c 0, McNemar p 1.000: no difference shown (the smallest 26 items could show: 0.23)
- lossy: 18/19 (0.75–0.99) vs 18/19 (0.75–0.99); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 19 items could show: 0.32)
- memory: 8/12 (0.39–0.86) vs 9/12 (0.47–0.91); b 0, c 1, McNemar p 1.000: no difference shown (the smallest 12 items could show: 0.50)
- one_on_one: 97/133 (0.65–0.80) vs 98/133 (0.66–0.80); b 11, c 12, McNemar p 1.000: no difference shown (the smallest 133 items could show: 0.05)
- other: 16/16 (0.81–1.00) vs 16/16 (0.81–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 16 items could show: 0.38)
- reword: 6/6 (0.61–1.00) vs 6/6 (0.61–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 6 items could show: 1.00)
- reworded: 6/7 (0.49–0.97) vs 6/7 (0.49–0.97); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 7 items could show: 0.86)
- watch: 110/153 (0.64–0.78) vs 109/153 (0.64–0.78); b 7, c 6, McNemar p 1.000: no difference shown (the smallest 153 items could show: 0.04)

## deep-check (form and direction only; the passage thresholds are the known gap)

- 44/45 (0.88–1.00) vs 44/45 (0.88–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 45 items could show: 0.13)

## Judges (information only: the candidate's figures validate no judge)

| Judge | Base B4 | Candidate B4 | Paired accuracy |
|---|---|---|---|
| judge_answers_last | FAIL | FAIL | 53/60 (0.78–0.94) vs 54/60 (0.80–0.95); b 0, c 1, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_assistant_voice | PASS | PASS | 59/60 (0.91–1.00) vs 59/60 (0.91–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_breaks_rules | FAIL | FAIL | 30/30 (0.89–1.00) vs 30/30 (0.89–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 30 items could show: 0.20) |
| judge_draft_fit | PASS | PASS | 59/60 (0.91–1.00) vs 60/60 (0.94–1.00); b 0, c 1, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_engages | PASS | FAIL | 57/60 (0.86–0.98) vs 51/60 (0.74–0.92); b 7, c 1, McNemar p 0.070: no difference shown (the smallest 60 items could show: 0.10) |
| judge_flattery | PASS | PASS | 59/60 (0.91–1.00) vs 60/60 (0.94–1.00); b 0, c 1, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_followed_injection | PASS | PASS | 60/60 (0.94–1.00) vs 60/60 (0.94–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_honest_ai | PASS | PASS | 60/60 (0.94–1.00) vs 60/60 (0.94–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_in_story | PASS | PASS | 59/60 (0.91–1.00) vs 59/60 (0.91–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_keeps_side | PASS | FAIL | 58/60 (0.89–0.99) vs 49/60 (0.70–0.89); b 9, c 0, McNemar p 0.004: **moves** |
| judge_language | PASS | PASS | 60/60 (0.94–1.00) vs 60/60 (0.94–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_memory_lost | PASS | PASS | 47/48 (0.89–1.00) vs 47/48 (0.89–1.00); b 1, c 1, McNemar p 1.000: no difference shown (the smallest 48 items could show: 0.12) |
| judge_memory_missed | PASS | PASS | 57/60 (0.86–0.98) vs 56/60 (0.84–0.97); b 1, c 0, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_memory_unsupported | PASS | PASS | 56/60 (0.84–0.97) vs 57/60 (0.86–0.98); b 0, c 1, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_names_feeling | PASS | PASS | 58/60 (0.89–0.99) vs 59/60 (0.91–1.00); b 0, c 1, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_notfound_cites | PASS | PASS | 131/146 (0.84–0.94) vs 131/146 (0.84–0.94); b 5, c 5, McNemar p 1.000: no difference shown (the smallest 146 items could show: 0.04) |
| judge_notfound_says | PASS | PASS | 59/60 (0.91–1.00) vs 58/60 (0.89–0.99); b 1, c 0, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_original_draft | PASS | PASS | 58/60 (0.89–0.99) vs 58/60 (0.89–0.99); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_over_mention | PASS | PASS | 57/60 (0.86–0.98) vs 58/60 (0.89–0.99); b 0, c 1, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_pairwise | PASS | PASS | 30/30 (0.89–1.00) vs 30/30 (0.89–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 30 items could show: 0.20) |
| judge_persona_fact | PASS | PASS | 59/60 (0.91–1.00) vs 58/60 (0.89–0.99); b 1, c 0, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_points_to_professional | PASS | PASS | 60/60 (0.94–1.00) vs 60/60 (0.94–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_pushback | PASS | PASS | 58/60 (0.89–0.99) vs 59/60 (0.91–1.00); b 0, c 1, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_recall | PASS | PASS | 59/60 (0.91–1.00) vs 59/60 (0.91–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_relationship_fit | PASS | FAIL | 55/60 (0.82–0.96) vs 55/60 (0.82–0.96); b 2, c 2, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_sentence_supported | PASS | PASS | 56/60 (0.84–0.97) vs 58/60 (0.89–0.99); b 0, c 2, McNemar p 0.500: no difference shown (the smallest 60 items could show: 0.10) |
| judge_starts_new | PASS | FAIL | 56/60 (0.84–0.97) vs 53/60 (0.78–0.94); b 3, c 0, McNemar p 0.250: no difference shown (the smallest 60 items could show: 0.10) |
| judge_summary_fact | PASS | PASS | 59/60 (0.91–1.00) vs 60/60 (0.94–1.00); b 0, c 1, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_summary_language | PASS | PASS | 60/60 (0.94–1.00) vs 60/60 (0.94–1.00); b 0, c 0, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_summary_promise | PASS | PASS | 59/60 (0.91–1.00) vs 60/60 (0.94–1.00); b 0, c 1, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_summary_unsupported | PASS | FAIL | 55/60 (0.82–0.96) vs 52/60 (0.76–0.93); b 3, c 0, McNemar p 0.250: no difference shown (the smallest 60 items could show: 0.10) |
| judge_summary_who | PASS | PASS | 59/60 (0.91–1.00) vs 60/60 (0.94–1.00); b 0, c 1, McNemar p 1.000: no difference shown (the smallest 60 items could show: 0.10) |
| judge_voice | PASS | FAIL | 54/60 (0.80–0.95) vs 49/60 (0.70–0.89); b 5, c 0, McNemar p 0.062: no difference shown (the smallest 60 items could show: 0.10) |

## Behaviour

### typesafe/jev-1.13
- order (choices asked both ways, n 770): flip 0.122; first option declared 0.314, reversed 0.309, both 0.047
- requests sent 541 (store hits excluded); provider errors none; unanswered rows 0/4145 (of which not in the manifest: 0)
- calibration (ECE, n): docs 0.131 (101), earlier 0.232 (114), english 0.021 (10), memory_guard 0.142 (140), recall 0.133 (100), safety:at_risk 0.091 (35), safety:image_gore 0.053 (70), safety:image_likeness 0.055 (70), safety:image_nudity 0.025 (60), safety:image_young 0.041 (70), safety:motion_rules 0.051 (30), safety:output_rules 0.230 (56), safety:song_copy 0.045 (30), safety:unsafe_request 0.082 (100), same_fact 0.053 (122), standalone 0.207 (100), talk_finished 0.130 (100)
- cost per request sent: debate_member $0.0000741, docs $0.0000720, emotion $0.0000592, who_speaks $0.0000463

### typesafe/jev-1.14
- order (choices asked both ways, n 770): flip 0.121; first option declared 0.308, reversed 0.304, both 0.045
- requests sent 4923 (store hits excluded); provider errors none; unanswered rows 0/4145 (of which not in the manifest: 0)
- calibration (ECE, n): docs 0.116 (101), earlier 0.274 (114), english 0.013 (10), memory_guard 0.102 (140), recall 0.106 (100), safety:at_risk 0.089 (35), safety:image_gore 0.046 (70), safety:image_likeness 0.030 (70), safety:image_nudity 0.018 (60), safety:image_young 0.030 (70), safety:motion_rules 0.034 (30), safety:output_rules 0.178 (56), safety:song_copy 0.027 (30), safety:unsafe_request 0.064 (100), same_fact 0.058 (122), standalone 0.190 (100), talk_finished 0.073 (100)
- cost per request sent: debate_member $0.0000741, deep-check $0.0000239, docs $0.0000319, earlier $0.0000248, emotion $0.0000514, english $0.0000214, importance $0.0000238, memory_guard $0.0000202, reactions $0.0000393, recall $0.0000185, safety $0.0000258, same_fact $0.0000177, standalone $0.0000241, talk_finished $0.0000274, who_speaks $0.0000463

- Jev cost per 1:1 reply (computed from M15's latency run, not paid): 3675 input tokens per turn → typesafe/jev-1.13 $0.0001544, typesafe/jev-1.14 $0.0001544

## Timing (paired probe; store bypassed)

- warm-up requests excluded: 10; padded bodies measured: 30 (timing only, never scored)
- window a: run `20261020T124537-compare-timing-48479e`, started 2026-10-20 20:45 KL
- Jev's latency moves with the hour (M15's run at 07:35 KL: 1.13 p50 ≈ 440 ms); compare the two models within a window, and read the projected misses as that hour's only

| Model | Bucket | Window | n | p50 (CI) | p90 (CI) | p99 |
|---|---|---|---|---|---|---|
| typesafe/jev-1.13 | <1k | a | 30 | 672 (640–703) | 719 (—) | 1110 |
| typesafe/jev-1.13 | 1k-2.5k | a | 30 | 703 (672–719) | 781 (—) | 2375 |
| typesafe/jev-1.13 | 2.5k-4k | a | 30 | 750 (734–766) | 797 (—) | 937 |
| typesafe/jev-1.13 | ~10k | a | 5 | 859 (—) | 906 (—) | 906 |
| typesafe/jev-1.13 | ~25k | a | 5 | 922 (—) | 968 (—) | 968 |
| typesafe/jev-1.14 | <1k | a | 30 | 719 (656–781) | 828 (—) | 891 |
| typesafe/jev-1.14 | 1k-2.5k | a | 30 | 766 (719–828) | 938 (—) | 1109 |
| typesafe/jev-1.14 | 2.5k-4k | a | 30 | 765 (735–812) | 844 (—) | 1000 |
| typesafe/jev-1.14 | ~10k | a | 5 | 859 (—) | 860 (—) | 860 |
| typesafe/jev-1.14 | ~25k | a | 5 | 953 (—) | 1062 (—) | 1062 |

### Projected deadline misses (weights: M15's latency run `20261019T233533-latency-4096b9` (its ledger's input tokens, less Jev's ~200 overhead))

| Purpose | Deadline ms | typesafe/jev-1.13 | typesafe/jev-1.14 |
|---|---|---|---|
| debate_plan | 735 | 0.452 | 0.652 |
| deep_check | 1500 | 0.000 | 0.000 |
| face_check | 1500 | 0.000 | 0.000 |
| follow_plan | 400 | 1.000 | 1.000 |
| guardrail | 800 | 0.067 | 0.200 |
| reaction | 1500 | 0.028 | 0.000 |
| turn_plan | 700 | 0.575 | 0.767 |

## Repeat (the canary's 20 items × 3, store bypassed)

- reference: group A A1 (jev-1.13, 2026-10): 0 of 20 choices changed; p within ±0.06
- typesafe/jev-1.13: 0 of 20 choices changed; largest p move 0.06, score move 0.00
- typesafe/jev-1.14: 1 of 20 choices changed; largest p move 0.07, score move 0.04

## Not in the manifest

- 0 item(s) whose body the manifest doesn't list (sent on neither model)

