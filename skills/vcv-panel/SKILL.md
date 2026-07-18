---
name: vcv-panel
description: Use when creating or editing a VCV Rack or MetaModule panel SVG from a spec, with the vcv-panel-gen grid-based generator (this skill ships inside its repo).
---

# VCV Panel Layout (grid-based)

The generator (`panelgen.py`, in the vcv-panel-gen repo this skill ships with) is
deliberately unopinionated: grids are just named x/y values, and the only checks are
bounds (error) and overlap (warning). **All layout judgment lives here and is applied
by you at spec-writing time.** Compute every position with the recipes below — never
eyeball, never guess.

Locate the tool first: this skill lives at `skills/vcv-panel/` inside the generator's
checkout. If you only have the skill, find or clone the repo
(`https://github.com/gabriel-roth/vcv-panel-gen`) and set `PG` to that checkout.

## Workflow

1. **Gather controls — NEVER invent any.** Read the module's C++ (enum names,
   `config*` calls) or ask the user. Note each control's full enum name
   (`TIME_PARAM`, `SIZE_CV_INPUT`…), widget class if non-default, and label.
   Ambiguous? Ask — do not guess.
2. **Compute the layout on paper first**: group controls into functional clusters,
   choose grids, derive every row y and column x with the recipes below. Only then
   write YAML.
3. **Write the spec** in the *module's* repo (e.g. `vcv/panel-spec.yaml`). The
   generator refuses to write output inside its own checkout.
4. `--check` until clean (or every warning is deliberately suppressed with a comment).
5. **Generate**, then **preview in a browser** — never judge the raw SVG (its
   components layer is `display:none`; it reads as background + labels only).
6. **Iterate on the spec** (never hand-edit the SVG) until the user signs off on the
   preview.
7. **Hand off**: `python helper.py createmodule <Slug> res/<Slug>.svg src/<Slug>.cpp`
   for a new module (see `vcv-add-module`). MetaModule builds: regenerate the
   faceplate PNG from the same SVG with the SDK's `SvgToPng.py --layer panel`, and
   sync a hand-maintained `_info.hh` with the repo's `mm_sync.py`.

## Commands

```bash
PG=<path to the vcv-panel-gen checkout>   # this skill lives at $PG/skills/vcv-panel
$PG/.venv/bin/python $PG/panelgen.py spec.yaml --check                       # validate only
$PG/.venv/bin/python $PG/panelgen.py spec.yaml --out res/Slug.svg            # generate
$PG/.venv/bin/python $PG/panelgen.py spec.yaml --out res/Slug.svg --preview --open
```

(First use: `python3 -m venv $PG/.venv && $PG/.venv/bin/pip install -r $PG/requirements.txt`.)

Theme defaults merge from `~/.config/vcv-panel-gen/theme.yaml`, overridable per-run
with `--theme FILE` or per-panel with the spec's `theme:` block.

## Personal defaults — save them, don't repeat them

When the user states a preference meant to outlast one panel ("my panels are dark,"
"always Futura labels," "I like silver screws"), write it to
`~/.config/vcv-panel-gen/theme.yaml` instead of copying it into every spec — create
the file if it doesn't exist, and confirm with the user before overwriting an
existing field. Fields (all optional; full schema in the repo's `AGENTS.md`):
`background`, `font` (family-name list, first installed wins), `title_font`,
`casing` (`upper|lower|title|preserve`), `text_color`, `title_color`, `value_color`,
`screws` (`light|dark|none`). A spec's `theme:` block should carry only what is
genuinely panel-specific (e.g. `screws: none` for a module that draws its own);
everything else belongs in the user file. If a spec repeats the same `theme:` values
you saw in the last spec, that's the signal to offer saving them. Tests set `PANELGEN_THEME_FILE` to
bypass the user file. Preview needs the VCV ComponentLibrary (`--library` or
`$VCV_COMPONENT_LIBRARY` if not at the default install path).

## Fixed geometry

Panel height 128.5 mm; width = HP × 5.08. Screws (unless `theme: {screws: none}`) at
(7.5, 3.0) and (7.5, 125.5) plus mirrors at width − 7.5, each with a 2.0 mm keep-out
radius the overlap check enforces. Title band = top 10 mm (default title baseline =
size + 1.0; `valign: center` centers the cap height in the band).

## Component true drawn sizes (mm)

From `components.yaml` (measured from Rack's ComponentLibrary; this is the drawn
graphic, not a padded footprint). Spacing math uses these numbers.

| Widget | Size | | Widget | Size |
|---|---|---|---|---|
| RoundBlackKnob | d 9.6 | | VCVButton | d 6.1 |
| RoundSmallBlackKnob | d 7.68 | | VCVBezel / LEDBezel | d 7.2 |
| RoundBigBlackKnob | d 15.24 | | CKSS | 4.74 × 6.99 |
| RoundHugeBlackKnob | d 18.24 | | CKSSThree | 4.56 × 9.6 |
| Trimpot | d 6.05 | | Small/Medium/LargeLight | d 2 / 3 / 5 |
| PJ301MPort | d 8.03 | | ScrewSilver/Black | d 5.08 |

Kind defaults: param → RoundBlackKnob, input/output → PJ301MPort, light →
MediumLight\<RedLight\>. Subclasses resolve by substring (RoundSmallBlackSnapKnob →
RoundSmallBlackKnob's size); a truly unknown class is an error — add it to
components.yaml (or re-run `tools/measure_components.py`) rather than guessing.

## Going-together math (the crux)

Objects in one functional cluster sit measurably closer to each other than to
anything else. Encode the relationship in the distance:

| Relationship | Rule | Worked number |
|---|---|---|
| Label above its control | baseline = control_cy − d/2 − 1.0 | RoundBlackKnob at cy 46.0 → baseline 40.2 |
| Label below a jack row | baseline ≈ jack_cy + 8.5 (3.0 mm text) | the bundled example panels use 8.35–10.0 |
| Control stacked over its CV/trig jack | centers = r_top + r_bottom + 2.0 (edge gap 2.0) | knob→PJ301M ≥ 10.8 |
| Stereo L/R pair | centers 9.7 apart (PJ301M), one shared label at the midpoint | edge gap 1.67 |
| Cluster ↔ cluster | gutter ≥ 4.0, and always visibly larger than every intra-cluster gap | |

Notes:
- The stack/label rules are floors. The bundled example panels breathe a little more
  (knob→jack centers 12.35, label 7.0 above knob cy); anything between the floor and
  that still reads as one cluster, provided the gutters stay clearly bigger.
- A stereo pair, or a button+trig stack, is **one unit** with **one label** — never
  two labeled jacks.
- Stacked control+jack pairs get a `connectors:` bar (0.3 mm, `#808080`, same x
  required). Connectors are explicit only — list every bar you want; side-by-side
  pairs at the same y get none (see the `loooop.yaml` example's bottom row).

## Vertical rhythm recipe

1. Fixed: 10 mm title band at top; keep drawn content ≈3 mm off the bottom edge
   (and clear of the 125.5 screw line).
2. Budget each content band (label + control + intra-cluster gaps, from the size
   table): knob row with label ≈ 22; jack row with label below ≈ 15; button/switch
   row ≈ 15; light row ≈ 8; standalone label row ≈ 5; knob+CV stack with label ≈ 27.
3. Leftover = 128.5 − 10 − 3 − Σ bands. Distribute it as the inter-cluster gaps:
   gap = leftover / (n_bands + 1) for even rhythm, or weight the gaps you want
   bigger. **Compute the split; don't eyeball it.**
4. Walk down accumulating: each row's y (control center or label baseline) falls out
   of the running total. Those y values become grid `rows:`.

Example: three bands of 22 + 27 + 15 = 64 → leftover = 128.5 − 13 − 64 = 51.5 over
4 gaps ≈ 12.9 each — too airy, so give the panel more content, spend slack on a
screen/zone, or weight gaps toward group boundaries. If leftover < ~4 per gap, the
panel needs more HP or fewer rows.

## Jack-row justification recipe

For a horizontal row of units with unequal widths (a stereo pair or button+trig pair
counts as one unit), equalize the **gaps**, not the centers:

```
unit width  = drawn diameter        (single control)
            = center_spacing + d    (pair: 9.7 + 8.03 = 17.73 for PJ301M)
gap = (usable_width − Σ unit_widths) / (n_units + 1)
```

Then walk left to right: first unit's left edge at `gap`, each next unit's left edge
one `gap` after the previous unit's right edge; centers follow from edges + radii.

Worked example — two stereo PJ301M pairs across 10 HP (50.8 mm), full width usable:
Σ widths = 2 × 17.73 = 35.46; gap = (50.8 − 35.46) / 3 = 5.11; centers land at
9.13 / 18.83 and 31.97 / 41.67. (The `mf20filter.yaml` example's row —
9.35 / 19.05 / 31.75 / 41.45 — is this same recipe over a slightly narrower span.)

## Spec crib

Given a control list, derive grids from the clusters — one grid per region that
shares columns/rows. A panel often decomposes conceptually into transport/main/io
clusters; the bundled `particules.yaml` example defines two grids (main, labels) and
places its transport and io rows at absolute coordinates:

```yaml
slug: Example
name: EXAMPLE
hp: 12
theme: {screws: none}            # only if the module draws its own screws
title: {size: 6.35, tracking: 0.74}   # text defaults to `name`; logo: replaces text
zones:
  - {x: 1.5, y: 28, w: 58, h: 60, rx: 2, fill: "#cf99a5", opacity: 0.5}
grids:
  main:
    cols: {count: 4, from: 9.87, to: 51.09}   # or explicit list: [12.6, 29.6, ...]
    rows:              # computed by the rhythm recipe; rows are ALWAYS named
      labels: 33.48
      knobs: 42.088
      cv: 53.746
elements:
  # kind inferred from _PARAM/_INPUT/_OUTPUT/_LIGHT suffix; widget defaults by kind
  - {name: FREEZE_INPUT, x: 11.9, y: 15.875}       # off-grid transport: absolute mm
  - {name: SCREEN, kind: widget, rect: {x: 1.5, y: 10.4, w: 57.96, h: 22.35}}
  - row: {grid: main, at: labels}                   # row/place shorthand;
    place: [TIME, DENSITY, PITCH, SIZE]             # bare strings = text elements
  - row: {grid: main, at: knobs, widget: RoundBlackKnob}
    place: [{name: TIME_PARAM}, {name: DENSITY_PARAM}, {name: PITCH_PARAM}, {name: SIZE_PARAM}]
  - row: {grid: main, at: cv}
    place: [{name: TIME_INPUT}, {name: DENSITY_INPUT}, {name: PITCH_INPUT}, {name: SIZE_INPUT}]
  - {text: Peak, x: 25.4, y: 74.857, size: 3.0}     # standalone label, absolute
  # value ring around a stepped knob (must name an element in this spec);
  # labels sweep VCV's ±149.4° arc at the drawn radius + gap
  - {ring: ["Ø", "4", "8", "16", "32", "64"], around: TIME_PARAM}
glyphs:
  - {src: assets/ticks-even.svg, at: [24.269, 48.025]}   # baked decorative SVG
connectors:                       # explicit only — one entry per bar you want
  - [TIME_PARAM, TIME_INPUT]
```

Any element mixes axes freely (`grid`+`col` with absolute `y`, etc.) plus `dx:`/`dy:`
offsets. Unknown keys anywhere are errors. Labels are ordinary text elements — a
"label row" is just a grid row of them.

## Overlap policy

Bounds violations are errors — fix them. Overlaps are warnings, printed with pair
names and depth in mm, so the fix is one arithmetic step. Warnings are *expected*
while drafting. Before sign-off, every surviving warning must be either fixed or
deliberately suppressed via `overlaps_ok:` **with a YAML comment saying why**:

```yaml
overlaps_ok:
  # "Out" sits 0.2mm inside the screw keep-out circle; drawn art doesn't touch.
  - [text:OUT, "screw@53.46,125.50"]
  - [RING_A, RING_B]        # pair of element names
  - [SCREEN]                # single name: anything may overlap SCREEN
```

Matcher forms: element `name`s; `text:<content>` (matches the RENDERED text — after
theme casing, so `text:OUT` for a label written as "Out" under an upper-casing
theme); `screw` (any screw) or `screw@x,y`; `title`. Zones, glyphs, and connectors
are decorative and never warn.

## The razor

When a panel needs polish, in strict order:

1. **Fix the spec's numbers** (grid rows/cols, absolute x/y) — recompute with the
   recipes; the spec should read as the layout's derivation.
2. **`dx:`/`dy:` offsets** — for one deliberate deviation from an otherwise-right
   grid (the `particules.yaml` example's DRY/WET label rides `dy: 0.32`).
3. **Only then** consider asking for a new script feature — and only if a second
   panel would want it too.

Never hand-edit the generated SVG. Never fix layout by editing output.

## Canonical examples

The example specs in `tests/fixtures/robotboy/` (inside the generator repo) are the
best documentation — real shipped panels from the Robot Boy plugin, kept as parity
regression tests:

| Spec | Demonstrates |
|---|---|
| `mf20filter.yaml` | 3-column grid, hero (RoundBigBlackKnob) knobs, trimpot+jack stacks with connectors, stereo I/O pairs |
| `lop.yaml` | `logo:` title, value ring around a snap knob, button+trig stacks, zone tint, overlap suppression with reason |
| `loooop.yaml` | multi-grid repetition at scale (4 identical head grids), tints-as-zones, `row`/`place` shorthand throughout |
| `particules.yaml` | multiple grids + deliberate off-grid transport row, decorative glyphs, `screws: none`, kind inference |

Full spec grammar and tool reference: `AGENTS.md` at the generator repo's root.
