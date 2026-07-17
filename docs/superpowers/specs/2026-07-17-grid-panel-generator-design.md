# Grid-based VCV panel generator (v2) — design

**Date:** 2026-07-17
**Status:** Approved for implementation (autonomous run; decisions documented inline)
**Supersedes:** \~/Dev/vcv-panel-gen (v1), which stays in place untouched — other modules
(onbetap, ondes, yellowjacket) still build with it.

## 1. Problem

v1 (\~/Dev/vcv-panel-gen) produced good panels for RobotBoy but is too opinionated to be
broadly useful. Its layout engine (`layout.py`, 35 KB) owns vertical band stacking, gap
distribution, weighted columns, jack-row justification, stereo-pair idioms, cv/trig
companion placement, param-group stacking, and value-ring label dodging. Escaping any of
these requires `nudges:` arithmetic against positions the tool computed and never shows
you (see the MF-20 spec's four-paragraph nudge comment block).

What v1 got right and this design keeps:

- Global + user + per-panel theme defaults (colors, fonts), field-by-field merge.
- Text baked to vector paths via fontTools (no Inkscape, no `<text>`, NanoSVG-safe).
- Accurate browser preview compositing real VCV ComponentLibrary art — no Rack build.
- Knowledge of true component sizes, used for validation and preview.
- The SVG↔VCV contract: mm viewBox, hidden `components` layer, kind-colored placeholder
  shapes, `id="NAME#WidgetClass"`, no transforms/text/filters — consumed by VCV's
  `helper.py` and by `mm_sync.py`.

## 2. Goals / non-goals

**Goals**

1. Grid-based layout as a *convenience*, never an enforcement: a grid gives evenly
   spaced columns across a horizontal span and named rows at explicit or evenly spaced
   y values. Any element can instead sit at absolute mm, or mix (grid column, absolute y),
   with per-element dx/dy offsets.
2. Multiple grids per panel, each usually full-width but any vertical extent
   (Particules = three grids: transport, main 8-row, io).
3. Bounds checking is an **error** (drawn extent off the panel edge); overlap between
   two drawn elements is a **warning**, suppressible per-pair in the spec.
4. All layout *judgment* — what goes together, how close, vertical rhythm — lives in a
   SKILL, not in scripts. Scripts do only deterministic arithmetic.
5. Regenerate all four RobotBoy panels (Loooop, Löp, MF-20, Particules) with new specs:
   component centers must match the shipped SVGs exactly (C++ `mm2px` coordinates are
   hardcoded against them).

**Non-goals**

- No row types, no automatic band heights, no automatic gap distribution, no pair/cv/trig
  idioms, no automatic connectors, no label-fit errors, no constraint solving.
- No preservation of the v1 spec format. v1 itself is not modified or deleted.

## 3. Architecture

New repo `~/Dev/vcv-panel-gen-redux`. Flat Python modules (matching v1's style), Python
3.10+, deps `fonttools` + `PyYAML` only.

```
panelgen.py        CLI: generate / check / preview
spec.py            YAML parse + schema validation (dataclasses; unknown keys are errors)
resolve.py         grid resolution + element placement → absolute mm (pure arithmetic)
checks.py          bounds (error) + overlap (warning) using true drawn extents
components.py      widget-size table loader (data in components.yaml)
svgdoc.py          SVG assembly (layers: panel / values / glyphs / components)
glyphs.py          TextRenderer: text → path d  [ported from v1 unchanged]
fontresolve.py     family → font file           [ported from v1 unchanged]
theme.py           3-layer theme merge          [ported from v1, same schema + file]
logo.py            baked SVG wordmark           [ported from v1 unchanged]
images.py          baked external glyph assets  [ported from v1 unchanged]
validate.py        forbidden-element guard      [ported from v1 unchanged]
preview.py         VCV-art compositor           [ported from v1, adapted to new resolver]
mm_sync.py         MetaModule header sync       [ported from v1 unchanged]
components.yaml    widget class → true drawn size (mm) + kind defaults
tools/measure_components.py   regenerates components.yaml from an installed Rack
fonts/DejaVuSans.ttf
skills/vcv-panel/SKILL.md     the layout-judgment skill (installed to ~/.claude/skills)
tests/             pytest; includes RobotBoy parity fixtures
```

Pipeline: `load_spec → resolve_theme → resolve (grids→mm) → checks → build_svg →
validate_svg`. Ported modules keep their v1 tests.

User theme file stays at `~/.config/vcv-panel-gen/theme.yaml` (same schema — the user's
existing defaults carry over: `#3d3d3d` background, white text, Futura, Shuttleblock
title, dark screws, upper casing).

## 4. Spec format

YAML mapping. Unknown keys at any level are errors (kept from v1 — catches typos).

### Top level

| Key | Req | Meaning |
|---|---|---|
| `slug`, `name`, `hp` | ✓ | as v1 |
| `theme` | | inline theme overrides (v1 schema) |
| `title` | | `{text?, size, tracking, valign, logo, x, y, dx, dy}`; default text = `name`, default position = centered in top 10 mm band. `logo:` path replaces text (Löp); valign defaults to baseline (v1-compatible). |
| `grids` | | map of grid name → grid def (below) |
| `elements` | ✓ | flat list of element defs (below) |
| `zones` | | decorative rects `{x, y, w, h, rx, fill, opacity}` (v1 semantics) |
| `glyphs` | | baked external SVG assets `{src, at: [x, y], scale?}` |
| `connectors` | | explicit list of `[NAME_A, NAME_B]` — vertical bar between the two elements' centers (same-x required, 0.3 mm wide, `#808080`; matches v1 rendering) |
| `overlaps_ok` | | list of `[A, B]` pairs, or single names (`[A]` = anything may overlap A). Suppresses overlap warnings. Entries may also be `text:<content>`, `screw` / `screw@<x>,<y>`, or `title` to suppress warnings involving non-component elements. |
| `side_margin` | | default 8 mm — used **only** as the default grid column span; nothing else consults it |

### Grids

```yaml
grids:
  main:
    cols: {count: 4, from: 12.6, to: 63.6}   # evenly spaced centers, OR
    # cols: [11.9, 38.1, 59.845]             # explicit x list
    # cols: {count: 4}                       # even across [side_margin, W - side_margin]
    rows:                                     # named y values (map), OR
      knobs_a: 42.088
      cv_a: 53.746
    # rows: {from: 31.5, to: 101.7, count: 8, names: [...]}  # evenly spaced;
    #        `names` (length == count) is required — rows are always referenced by name
```

A grid is nothing but a set of named x values (columns, referenced by 1-based index) and
named y values (rows, referenced by name). No sizing, no bands, no content model.

### Elements

Every element is positioned by exactly one of these per axis, freely mixed:

- `grid: main, col: 2` (x from grid) and/or `row: knobs_a` (y from same grid)
- `x: 20.4` / `y: 74.15` (absolute mm)
- plus optional `dx:` / `dy:` offsets (replaces v1 `nudges`, but visible in place)

Element forms:

```yaml
elements:
  # component: kind inferred from name suffix (_PARAM/_INPUT/_OUTPUT/_LIGHT),
  # overridable with kind:; widget: defaults per kind from components.yaml
  - {name: TIME_PARAM, widget: RoundBlackKnob, grid: main, col: 1, row: knobs_a}
  - {name: FREEZE_INPUT, x: 11.9, y: 15.875}

  # screen/custom widget: rect bounds (top-left + size), kind: widget
  - {name: SCREEN, kind: widget, rect: {x: 1.5, y: 10.4, w: 57.96, h: 22.35}}

  # text: standalone label (this is how label rows work)
  - {text: TIME, grid: main, col: 1, row: labels_a}
  - {text: Peak, x: 25.4, y: 74.857, size: 3.0, color: "#ffffff", casing: preserve}

  # value ring: labels swept around a knob (values layer; mechanical placement,
  # evenly spaced across VCV's ±149.4° sweep at true radius + gap; no dodge logic)
  - {ring: ["Ø", "4", "8", "16", "32", "64"], around: GRID_PARAM, gap: 0.65}
```

Sugar — a `row` shorthand that assigns consecutive columns (pure syntax, no layout
logic; `~` skips a column):

```yaml
  - row: {grid: main, at: knobs_a, widget: RoundBlackKnob}
    place: [{name: TIME_PARAM}, {name: DENSITY_PARAM}, {name: PITCH_PARAM}, {name: SIZE_PARAM}]
  - row: {grid: main, at: labels_a}
    place: [TIME, DENSITY, PITCH, SIZE]        # bare strings = text elements
```

Attached-label sugar on components: `label: {text: Drive, dy: 8.2}` — places a text
element at the component center + offset. Zero judgment: the offset is explicit.

Text rendering: theme font/casing/color apply; per-element overrides allowed. Labels are
never auto-shrunk and never error on width — overlap/bounds checks catch real problems.

## 5. Resolution & validation semantics

`resolve.py` maps every element to an absolute mm center (or rect) in document order.
No element may reference another element's position (no relative-to-element placement;
`connectors`, `ring`, and `label:` sugar are the only cross-references, and they resolve
after placement). No topological sort, no solver.

`checks.py`, using **true drawn extents** (text: fontTools width × cap height;
components: `components.yaml` true sizes; screens: their rects):

- **Error** — any drawn extent outside `[0, W] × [0, 128.5]`; unknown widget class
  (no size data); duplicate `name`; unknown grid/row/col reference.
- **Warning** — any two drawn extents intersecting (circle/circle, circle/rect,
  rect/rect; text as rect), including screws and title, unless suppressed by
  `overlaps_ok`. Zones, glyphs, and connectors are decorative and exempt.

`--check` runs everything but writes nothing. Warnings print pair names + overlap depth
in mm so fixes are one arithmetic step.

## 6. Rendering contract (unchanged from v1)

- `width/height` in mm, `viewBox` 1:1 mm.
- Layer `panel`: background, zones, screw circles (theme: light/dark/none), connectors,
  title (text path or baked logo), text paths.
- Layer `values`: ring labels (excluded from MetaModule PNG export).
- Layer `glyphs`: baked decorative assets.
- Layer `components` (`display:none`): `r="2"` circles / rects, fill by kind
  (`#ff0000` param, `#00ff00` input, `#0000ff` output, `#ff00ff` light, `#ffff00`
  widget), `id="NAME#WidgetClass"`.
- Output contains no `<text>/<style>/<image>/<filter>/<mask>/<clipPath>` and no
  `transform=` (validate.py guard, ported).
- Refuses to write output inside its own checkout (ported guard).

## 7. Component size data

`components.yaml`: widget class → `{shape: circle|rect, d|w/h (true drawn mm), kind
default}` — the v1 true-diameter numbers (RoundBlackKnob 9.6, RoundBigBlackKnob 15.24,
RoundSmallBlackKnob 7.68, PJ301MPort ≈8.5, Trimpot, buttons, lights, screws…), measured
from Rack's 75-dpi SVGs. `tools/measure_components.py` regenerates the table from an
installed Rack's ComponentLibrary. Kind defaults: param→RoundBlackKnob,
input/output→PJ301MPort, light→MediumLight\<RedLight\>.

## 8. Preview

Ported `preview.py`: reads the generated SVG's components layer, composites real VCV
art (base64-embedded once, `<use>`-referenced), emits `<slug>.preview.svg` +
`.preview.html`, `--open` launches the browser. Unknown widget → magenta marker +
report. Unchanged behavior; it already depends only on the SVG contract, not on layout.

## 9. The skill (`skills/vcv-panel/SKILL.md`)

All judgment lives here. Contents:

1. **Workflow**: gather controls (never invent) → compute layout on paper (grids + y
   values) → write spec → `--check` → generate → preview in browser → sign-off →
   `helper.py` / MetaModule handoff.
2. **Vertical rhythm recipe**: 10 mm title band, ~3 mm bottom margin, typical band
   heights per content type, how to distribute leftover height across grid gaps.
3. **Going-together math** (the v1 constants, now guidance): label 1.0 mm above the
   drawn top of its control; control↔jack stack gap 2.0 mm edge-to-edge; stereo pair
   1.0 mm edge gap (= 9.7 mm centers for PJ301M); intra-cluster gaps must be visibly
   smaller than inter-cluster gaps (≥4 mm gutters between groups).
4. **Jack-row justification recipe**: how to compute even *gaps* between units of
   unequal width (the arithmetic v1 did in `_column_slots`, now done by the model when
   wanted).
5. **Component size table** (mirrors components.yaml) so spacing math has real numbers.
6. **Overlap policy**: warnings are expected during drafting; suppress only with a
   reason comment.
7. Pointer to v1's razor, adapted: fix the spec's numbers > add dx/dy > only then ask
   for a new script feature.

The old `vcv-panel-generate` skill is left untouched (other modules use v1). The new
skill is installed as `vcv-panel`; its description marks it as superseding the old one
for new work.

## 10. Acceptance: RobotBoy parity

New specs live in `tests/fixtures/robotboy/` (plus Particules' glyph assets copied from
the RobotBoy panel-refactor worktree, and lop-logo.svg). A pytest compares generated
output against reference SVGs copied from `~/Dev/RobotBoy/res/`:

- **Component centers**: exact match (≤0.001 mm) for every id in the components layer —
  Loooop (38 HP, 4 tinted heads), Löp (12 HP, logo title), MF-20 (10 HP, nudged
  heroes), Particules (15 HP, vs the hand-built original's components layer / the
  `mm2px` coordinates in Particules.cpp).
- **Panel layer**: for the three v1-generated modules, label/title path geometry should
  match v1 output (same glyph renderer + same positions ⇒ same `d` strings); compared
  by path bounding boxes ≤0.01 mm. Particules original is hand-built Inkscape, so
  parity there = component centers + zones + visual preview review.
- Zones/tints: exact geometry and colors.

These specs double as the tool's best documentation-by-example.

## 11. Testing

- Ported modules keep their v1 pytest suites.
- New: spec schema (rejects unknown keys, bad refs), resolver (grid math, mixing,
  dx/dy, row sugar), checks (bounds error, overlap warning, suppression), svgdoc
  (layer structure, id contract), CLI (`--check`, exit codes), RobotBoy parity (§10).
- TDD throughout (superpowers:test-driven-development).

## 12. Decisions made autonomously (flag for review)

1. **Grid rows are named, columns are indexed.** Rows carry meaning (knobs_a, cv_a);
   columns rarely do. Mixing axes (`grid`+`col` with absolute `y`) is allowed.
2. **Labels are ordinary text elements** (matching how the user described Particules —
   "a row of labels" *is* a grid row), with optional attached-label sugar for
   MF-20-style below-the-knob captions.
3. **Kind inference from `_PARAM/_INPUT/_OUTPUT/_LIGHT` suffixes** with explicit
   override — the names are already VCV enum names.
4. **Value rings kept as a mechanical feature** (Loooop's Grid knob needs them); the
   opinionated dodge logic is dropped — overlap warnings replace it.
5. **`row`/`place` shorthand kept** — pure syntax sugar, no layout logic; without it
   Particules' spec would be ~120 near-identical lines.
6. **User theme file path reused** so existing defaults apply without migration.
7. **mm_sync.py ported verbatim** so the new repo is self-sufficient for the
   MetaModule flow, though RobotBoy's sync scripts currently point at v1.
8. **Connectors draw center-to-center exactly as v1 did**, endpoints tolerant
   to 0.1mm of shared-x drift and clamped short of either endpoint's value-ring
   labels if it has one — parity with shipped RobotBoy SVGs governs over the
   earlier "edge-trimmed"/"tightened tolerance" wording (RobotBoy's
   Yellowjacket needs both: its Blend knob's CV-input connector spans two
   components 0.0167mm apart, both exact per the shipped panel, and the bar
   must stop above the Blend ring's "N" label rather than run through it).
9. **Title valign defaults to baseline, matching v1's default**, so specs
   omitting valign regenerate v1-identical titles.
