# DESIGN.md — SERAPH Design System

**Authoritative for:** all SERAPH interface work — C11 decision support, C12 dashboard, and the report's figures.
**Derives:** `V0-PROMPT.md` takes its tokens from this file. If the two disagree, this file wins.
**Constrains:** SPEC FR39–FR49, NFR21 (interpretability), NFR22 (retail comprehensibility).

---

## 1. PRINCIPLES

Apple's design language rests on clarity, deference and depth. SERAPH inherits all three and adds a fourth, because it reports a quantity that is never known exactly.

### Clarity
One reading, unmistakable, at a glance. Type is legible at every size. Every number states what it is and what it is measured in. Negative space is not empty — it is what makes the important thing important.

### Deference
The interface recedes so the data can be the interface. No chrome competing with content. No decorative gradients, no drop shadows for their own sake, no borders where whitespace would do. If a rule, box or fill is not carrying information, delete it.

### Depth
Layers communicate hierarchy and state. A raised surface means "this is a distinct object." A dimmed layer means "this is still true but no longer current." Motion explains what changed and where it came from — it never merely entertains.

### Candour
**The interface never implies more confidence than the model has.**

This is SERAPH's own principle and it outranks aesthetics. A score without its interval is a lie of omission. A degraded reading that looks identical to a complete one is a design defect, not a cosmetic issue. Where the system does not know, the interface shows that it does not know — plainly, without hedging language, and without hiding it in a tooltip.

Every rule in §7 descends from this principle.

---

## 2. THE SIGNATURE — uncertainty as material

The one memorable element, and the one place boldness is spent.

The Composite Systemic Risk Score sits on a **material whose optical softness scales with the model's variance.** At high confidence the material is crisp, its edges defined. As `Var(CSRS)` grows, the material's backdrop blur increases and its edges diffuse — so a viewer registers uncertainty pre-attentively, before reading a single digit.

```
blur_radius = clamp(0, 16, 40 · sqrt(variance))   // px
edge_opacity = clamp(0.15, 1.0, 1 − 3 · sqrt(variance))
```

**The numerals themselves are never blurred.** Text sits crisply on top at full contrast; only the material behind it softens. This keeps the treatment legible and accessible.

**Fallback, mandatory:** where backdrop blur is unavailable or `prefers-reduced-transparency` is set, the same information is carried by the width of the confidence band. The design must be complete without the blur; the blur is an amplifier, not the channel.

Nothing else on the page uses blur. Spend it here.

---

## 3. COLOUR

Dark-first. Justified: SERAPH is a monitoring instrument used for long sessions, and a dark field lets muted semantic colour carry meaning without shouting.

### Surfaces — elevation is meaning, not decoration

| Token | Hex | Use |
|---|---|---|
| `--bg-base` | `#0B1014` | Page field. Near-black, cold blue-green cast. Never pure `#000`. |
| `--bg-raised` | `#141B21` | Panels, cards — a distinct object |
| `--bg-overlay` | `#1C252D` | Popovers, tooltips, modals |
| `--bg-sunken` | `#070B0E` | Inset wells, chart plot areas |
| `--separator` | `#212C34` | Hairline, 1px, default |
| `--separator-strong` | `#2E3A44` | Structural division between regions |

Elevation is expressed by surface value and a hairline — **never by shadow.** Shadows imply physical light this interface does not have.

### Ink

| Token | Hex | Contrast on base | Use |
|---|---|---|---|
| `--ink-primary` | `#E8EDF0` | 15.2:1 | Values, headings |
| `--ink-secondary` | `#97A5AF` | 7.1:1 | Labels, axis text |
| `--ink-tertiary` | `#64727C` | 3.6:1 | Captions, non-essential metadata |
| `--ink-quaternary` | `#414D56` | 2.0:1 | **Statistically insignificant marks only.** Never text. |

`--ink-quaternary` is the "noise" value. It is what the Marchenko–Pastur bulk is drawn in, and what sub-threshold contagion arcs are drawn in. Low contrast is the point: present, subordinate, not hidden.

### Semantic — regime colours

These three are bound to market regimes. **Never use them decoratively, never for emphasis, never for a button.**

| Token | Hex | Fill (12% α) | Regime |
|---|---|---|---|
| `--tranquil` | `#4A9D7E` | `rgba(74,157,126,.12)` | Regime 1 |
| `--stressed` | `#C9A227` | `rgba(201,162,39,.12)` | Regime 2 |
| `--crisis` | `#C4462F` | `rgba(196,70,47,.12)` | Regime 3 |
| `--dormant` | `#55707E` | `rgba(85,112,126,.12)` | Monitoring / no active signal |

**⚠ Accessibility defect in the source palette, and its remedy.** Green–amber–red is the single worst hue triple for deuteranopia and protanopia — roughly 8% of men cannot reliably separate regime 1 from regime 3. Therefore:

1. **Regime is always encoded at least twice.** Colour plus one of: fixed stack position (tranquil left, crisis right — always), an explicit text label, or distinct fill pattern.
2. **The palette survives greyscale.** Lightness values are deliberately separated (L\* ≈ 60 / 68 / 47), so the three remain distinguishable when desaturated. Test every regime view in greyscale before shipping it.
3. **An alternate palette ships behind a preference:** `--tranquil-alt: #3E8FA0` (teal-blue), `--crisis-alt: #C4406B` (magenta-red). Hue separation widens; semantics are unchanged.

### System accent — reserved

| Token | Hex | Use |
|---|---|---|
| `--accent` | `#5B9DD9` | Focus rings, selection, active control state — **and nothing else** |

The accent is deliberately outside the semantic set so that "the thing you are interacting with" can never be confused with "the market is in trouble." No data mark is ever drawn in `--accent`.

**Total palette: 4 surfaces, 4 inks, 4 semantics, 1 accent.** Adding a colour requires deleting one.

---

## 4. TYPOGRAPHY

One superfamily — **IBM Plex** — across three roles. A single family, precisely deployed, reads as more considered than a fashionable display pairing, and Plex's mono has genuine character in the numerals where this interface lives.

| Role | Family | Applied to |
|---|---|---|
| Display | IBM Plex Sans Condensed | Headings, the hero value |
| Text | IBM Plex Sans | Body, labels, controls |
| Data | IBM Plex Mono | **Every numeral, without exception** |

### Scale

| Token | Size / line | Weight | Tracking | Use |
|---|---|---|---|---|
| `display` | 44 / 1.05 | 600 | −0.02em | The CSRS value. **Once per view.** |
| `title` | 24 / 1.20 | 600 | −0.01em | Region headings |
| `heading` | 17 / 1.30 | 600 | 0 | Panel titles |
| `body` | 15 / 1.50 | 400 | 0 | Prose. The explainer, and little else. |
| `callout` | 13 / 1.40 | 500 | 0 | Control labels, legends |
| `label` | 11 / 1.20 | 600 | 0.08em, uppercase | Panel eyebrows **only** |
| `data-xl` | 32 / 1.10 | 500 | 0 | Pillar sub-scores |
| `data` | 15 / 1.40 | 400 | 0 | Table figures |
| `data-sm` | 12 / 1.35 | 400 | 0 | Axis ticks, captions |

### Numeral rules — non-negotiable

```css
font-variant-numeric: tabular-nums;
font-feature-settings: "tnum" 1, "zero" 1;
```

Applied to **every** numeral in the system. A figure that changes width as it updates makes a panel twitch, and a twitching panel reads as unreliable. `"zero" 1` enables the slashed zero — this is a quantitative instrument and `0`/`O` must never be ambiguous.

Uppercase is reserved for the `label` role. Nowhere else. Sentence case throughout.

---

## 5. SPACE, SHAPE, LAYOUT

**4pt base grid.** Every dimension is a multiple: `4 · 8 · 12 · 16 · 24 · 32 · 48 · 64`.

Optical rhythm within a panel: 24px outer padding, 16px between element groups, 8px within a group, 4px between a label and its value.

### Radius

| Token | Value | Use |
|---|---|---|
| `--r-sm` | 6px | Inputs, chips, badges |
| `--r-md` | 10px | Panels, cards |
| `--r-lg` | 16px | Modals, the hero material |
| `--r-full` | 9999px | Status dots, toggles |

Where the platform supports it, prefer continuous (superelliptical) corners over circular arcs — the curvature transition is what makes Apple's rounding read as considered rather than merely rounded.

### Grid

12-column, 24px gutter, 32px page margin. The dashboard's three regions are fixed-width rail (240px) / fluid centre / fixed panel (320px), and the centre column is where the eye lands first.

### Density

This interface is dense, and density is not an excuse for crowding. Every panel needs at least 24px of breathing room on its long edge. If a layout requires less, the layout has too much in it — remove a panel rather than tighten the spacing.

---

## 6. MOTION

| Token | Duration | Curve | Use |
|---|---|---|---|
| `--m-micro` | 120ms | `cubic-bezier(.4,0,.2,1)` | Hover, focus, toggle |
| `--m-standard` | 240ms | `cubic-bezier(.32,.72,0,1)` | Panel change, value transition |
| `--m-transition` | 400ms | `cubic-bezier(.32,.72,0,1)` | Role switch, epoch jump |
| `--m-ambient` | 3000ms | `linear`, infinite | Contagion arc travel only |

### Rules

1. **Motion explains causality.** A value that changes because new data arrived animates. A value that changes because the user switched views cross-fades. These must look different.
2. **Never animate a data mark's position in a way that implies movement in the underlying quantity.** The CSRS band animates its *width* on a variance change, not its position — because the score did not move, the confidence did.
3. **Ambient motion is limited to one element.** The contagion arcs. Everything else is still until something happens.
4. `prefers-reduced-motion` disables arc travel and all width transitions; state changes become instantaneous. **The interface must be fully comprehensible with every animation removed.**

---

## 7. DATA DISPLAY RULES

These descend from Candour (§1) and are binding.

1. **No point estimate without its interval.** Anywhere the CSRS appears — dashboard, report figure, export — the confidence band appears with it. There is no compact variant that drops it.
2. **Precision ladder.** CSRS and sub-scores: 2 decimals. p-values: 3 decimals, or `< 0.001`. Counts: integer. Percentages: 1 decimal. Never render more precision than the estimator supports.
3. **A masked pillar is visible as masked.** Diagonal hatch (2px, 45°, `--ink-quaternary` at 20%) across affected marks; the row remains present with a struck-through label and a zero-length bar. **Never omit the row** — a missing pillar and a pillar reading zero must never look the same.
4. **Staleness is continuous, not binary.** A pillar's row opacity falls from 1.0 toward 0.45 as its observation noise approaches saturation. At saturation it is also excluded from the mask, and the hatch applies.
5. **Insignificance is drawn, not hidden.** Sub-threshold arcs, in-bulk eigenvalues and non-significant contributions render in `--ink-quaternary`. Absence of evidence must look different from evidence of absence.
6. **Colour never carries state alone.** Every colour-encoded state has a label, a position, or a shape carrying the same information.
7. **No gradients on data marks.** A gradient implies a continuum the data may not have. Gradients are permitted only on the hero material.
8. **Degraded readings are never plotted on a shared axis with complete ones** without visible annotation. A 2008 CSRS (two pillars) and a 2020 CSRS (three) are different quantities.
9. **Every reading carries provenance** on demand: which weights artefact, which reconciliation mode, which mask. Not prominent, never absent.

---

## 8. COMPONENTS

### CSRS Band — the hero
Full centre width, 140px. Horizontal axis 0→1. Point marker at full opacity; CI envelope at 12% fill in the dominant regime colour; hero material behind, blurred per §2. Threshold gridlines hairline `--separator`, labelled in `--ink-tertiary`. 60px sparkline below: 1px point-estimate line, CI envelope behind at 15% `--ink-quaternary`.
**Degraded state:** hatch across the full band, label `Degraded — {pillar} unavailable · scored on {n} of 3 pillars` in `callout`/`--stressed`.

### Pillar Readout Row
`label` name · `data-xl` value · 40px sparkline · staleness in `data-sm`/`--ink-tertiary`. Row opacity per rule 4. 56px tall, 8px internal gap.

### Regime Stack
100% horizontal stacked bar, 32px, `--r-sm`. **Order is fixed: tranquil, stressed, crisis, left to right, always** — position is the redundant encoding required by §3. Percentage inside any segment ≥ 15% wide; outside with a leader line otherwise.

### Shapley Bars
Three diverging horizontal bars from a centre baseline. Positive contribution right, negative left. Bar in the current regime colour at 80%. Masked pillar: zero-length bar, struck label, hatch on the axis segment.

### Contagion Graph
SVG radial. 12 sector nodes on a circle. Directed arcs as quadratic Béziers bowing toward centre. Stroke 0.5–3px by excitation strength; colour `--ink-quaternary` → `--stressed` → `--crisis`. Node radius by branching ratio; flagged nodes get a 2px `--stressed` ring. Hover dims non-incident arcs to 10%. Arc travel dash on `--m-ambient`.

### MP Spectrum
280×90. Bulk filled `--ink-quaternary`; beyond-bound region filled `--crisis`. Hairline rule at λ₊. Caption in `data-sm`.

### Explainer Card
`--bg-raised`, `--r-md`, 24px padding. Eyebrow `Why this reading` in `label`. One sentence in `body` at 15px. **The only prose on the page** — give it room.

### Empty and error states
Empty: a statement of fact, `label`-styled, in `--ink-tertiary`, centred in the region — *"No contagion above threshold in this window."* Not an apology, not an illustration.
Error: what happened and what to do, in `callout`. *"Kite feed unreachable. Showing data to 15:20."* Never "Oops." Never a bare code.

---

## 9. ACCESSIBILITY FLOOR

Not a checklist item — part of the quality bar.

- **Contrast:** body text ≥ 7:1, large text and UI ≥ 4.5:1, non-text marks ≥ 3:1. `--ink-quaternary` fails these bounds by design and is therefore restricted to non-essential marks only, never text.
- **Focus:** 2px `--accent` ring, 2px offset, on every interactive element. Never `outline: none` without a replacement.
- **Keyboard:** every control reachable and operable. The pillar mask, role switcher and epoch selector are the critical paths.
- **Colour independence:** §3 and rule 6. Verify in greyscale and under a deuteranopia simulation before any review.
- **Motion:** `prefers-reduced-motion` fully honoured; `prefers-reduced-transparency` disables the hero blur with band width carrying the load.
- **Screen readers:** every chart has a text alternative stating the current value, its interval, and the mask state. The CSRS band's alternative is a sentence, not a data dump.

---

## 10. ANTI-PATTERNS

Things that will look like an improvement and are not.

| Don't | Why |
|---|---|
| Show CSRS as a large bare number | Violates Candour. The interval is not optional. |
| Add a fourth accent colour | The palette is closed. Adding requires deleting. |
| Use regime colours for buttons or emphasis | They mean market state. Overloading them destroys the meaning. |
| Drop shadows for elevation | Implies a light source this interface doesn't have. Use surface value and hairlines. |
| Hide insignificant data | Absence of evidence must not look like evidence of absence. |
| Animate on every update | Ambient motion is one element. Everything else is still until something happens. |
| Round to more decimals for a "precise" look | Fabricated precision is the failure mode this whole system exists to avoid. |
| Icon libraries | Simple geometric marks, drawn deliberately. No emoji, ever. |
| A gauge, dial or speedometer | Radial gauges are hard to read precisely and imply a mechanical certainty the model lacks. |
| A globe or map | SERAPH covers one exchange. Geography would be decoration pretending to be data. |

---

## 11. OPEN

| # | Decision | Blocks |
|---|---|---|
| 1 | Streamlit / Dash / React (SPEC OQ15 + NFR36). React changes C11's boundary to HTTP; Streamlit does not. | All component implementation |
| 2 | Does the hero blur survive the chosen renderer? Streamlit + Plotly cannot backdrop-blur natively — the §2 fallback may become the primary. | The signature element |
| 3 | Report figures: same tokens, or a print-adapted light variant? Dark figures on white paper waste ink and read poorly. | Report §7.7 |
| 4 | Retail role type scale — NFR22 requires comprehension without a quant background. May need a larger floor than 15px body. | C11 retail view |

Item 2 is the one to settle early. If the renderer cannot blur, the signature moves entirely to band width — still good, but it should be a decision rather than a discovery.
