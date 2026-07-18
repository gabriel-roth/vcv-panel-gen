# AGENTS.md — vcv-panel-gen reference

**This file is the complete reference for coding agents using this tool.** Layout judgment and workflow recipes (spacing math, vertical rhythm, cluster gutters, sign-off checklist) live in `skills/vcv-panel/SKILL.md` — read that too if it is available.

vcv-panel-gen turns a YAML spec into a VCV Rack / MetaModule front-panel SVG. The scripts do mechanical arithmetic and validation only — grid math, bounds checking, overlap detection, text baking, SVG assembly. They have no opinion about what makes a good layout; that judgment is applied by whoever writes the spec.

Pipeline: `load_spec` → theme resolution → font resolution → `resolve` (all positions to absolute mm) → `run_checks` (bounds = errors, overlaps = warnings) → `build_svg` → `validate_svg` → write. Bounds errors abort before anything is written.

---

## 1. CLI

```bash
.venv/bin/python panelgen.py SPEC [--out OUT.svg] [--check] [--theme FILE.yaml]
                                  [--library DIR] [--preview] [--open] [--version]
```

| Flag | Behavior |
|---|---|
| `SPEC` | path to the spec YAML (positional, required) |
| `--out OUT.svg` | output path; required unless `--check`. **Refused inside the vcv-panel-gen checkout itself** (symlinks are resolved before the comparison) — a module's panel belongs in the module's own repo; temp directories are fine. Missing parent directories are created. |
| `--check` | run the entire pipeline — spec, theme, layout, checks, SVG build, SVG validation — but write nothing. Prints `OK: <spec> builds (nothing written).` on success. |
| `--theme FILE.yaml` | use this theme file instead of the conventional `~/.config/vcv-panel-gen/theme.yaml`, for this run only |
| `--library DIR` | VCV ComponentLibrary directory for `--preview`/`--open` (default `$VCV_COMPONENT_LIBRARY`, else a conventional per-OS Rack install location) |
| `--preview` | after a successful generate, write `<out-stem>.preview.svg` and `<out-stem>.preview.html` beside `--out`, compositing real ComponentLibrary art onto the panel. A missing ComponentLibrary is a `note:` on stderr, **not** a failure — the panel SVG is written either way. Unknown widget classes draw a magenta ring marker and are listed in a `WARNING:` instead of being silently dropped. |
| `--open` | like `--preview`, and also opens the preview HTML in a browser |

Exit codes and output streams:

- Warnings (suppressible overlaps) print to stderr prefixed `WARNING:` and **do not** affect the exit code.
- Errors — bounds violations, unknown widget classes, a spec/theme that won't parse, a bad connector, the output-location guard — print to stderr prefixed `ERROR:` and exit 1. Nothing is written when there are errors.
- A clean run (warnings or not) exits 0.

`PANELGEN_THEME_FILE`, if set in the environment, replaces the conventional `~/.config/vcv-panel-gen/theme.yaml` lookup path outright (read at import time). The test suite uses it so tests never read a real user config; normal invocations don't set it.

---

## 2. Spec format

A YAML mapping. **Unknown keys at any level are errors** — the message names the offending key(s) and their context, so a typo fails loudly instead of being ignored.

### 2.1 Top level

| Key | Required | Meaning |
|---|---|---|
| `slug` | yes | non-empty string; used for messages and by convention as the output SVG basename |
| `name` | yes | non-empty string; default title text |
| `hp` | yes | positive integer; panel width = `hp × 5.08` mm. Height is always 128.5 mm. |
| `elements` | yes | non-empty list of placed things (§2.4) |
| `theme` | no | inline theme overrides, same field set as the theme file (§3) |
| `title` | no | title block (§2.10) |
| `grids` | no | map of grid name → grid definition (§2.2) |
| `zones` | no | decorative tint rects (§2.6) |
| `glyphs` | no | baked external SVG assets (§2.7) |
| `connectors` | no | explicit vertical bars between components (§2.8) |
| `overlaps_ok` | no | deliberate overlap suppressions (§2.9) |
| `side_margin` | no | positive number, default 8.0 mm; used **only** as the default column span for grids that omit `from`/`to` |

### 2.2 Grids

A grid is nothing but named x values (columns, referenced by 1-based index) and named y values (rows, referenced by name). No bands, no sizing, no content model.

```yaml
grids:
  main:
    cols: {count: 4, from: 9.87, to: 51.09}   # evenly spaced centers, endpoints inclusive
    # cols: [11.9, 38.1, 59.845]              # or an explicit x list
    rows:                                     # literal name -> y map...
      labels: 33.48
      knobs: 42.088
    # rows: {from: 31.5, to: 101.7, count: 8, names: [a, b, ...]}   # ...or evenly spaced
```

`cols` (required) is either:

- an explicit non-empty list of numbers — used verbatim; or
- `{count, from?, to?}` — `count` a positive integer; `from`/`to` must be given together, with `to > from`. When omitted, the span defaults to `side_margin .. width − side_margin`. `count: 1` places the single column at the **midpoint** of the span; otherwise columns are evenly spaced with both endpoints included.

`rows` (required, rows are always referenced by name) is either:

- a literal map of non-empty unique names → y numbers (must be non-empty); or
- the evenly-spaced form `{from, to, count, names}` — all four keys required; `names` must be unique, non-empty strings with `len(names) == count`; `to > from` unless `count == 1` (which yields just `from`). The presence of `count` or `names` selects this form.

### 2.3 Element positioning

Every positioned element takes **exactly one x-source and exactly one y-source**, freely mixed:

- x: either `grid:` + `col:` (1-based integer, validated against the grid's column count), or absolute `x:` in mm. Giving both, or neither, is an error.
- y: either `grid:` + `row:` (a row name in that grid), or absolute `y:` in mm. Same exactly-one rule.
- `col:` and `row:` each require `grid:`; the grid name must exist.
- Optional `dx:` / `dy:` offsets (mm, default 0) are added after grid resolution, on either axis regardless of source.

So `{name: X_PARAM, grid: main, col: 2, y: 96.5, dy: -0.3}` is valid: grid x, absolute y, nudged.

### 2.4 Elements

Each entry in `elements:` is one of four shapes, dispatched by key:

| Present key(s) | Element |
|---|---|
| `ring:` | value ring (§2.4.3) |
| `row:` + `place:` | shorthand expanding to a row of components/texts (§2.4.4) |
| `name:` | component (§2.4.1) |
| `text:` | text (§2.4.2) |

#### 2.4.1 Components

Allowed keys: `name, kind, widget, grid, col, row, x, y, dx, dy, rect, label`.

- `name` — required, non-empty; this exact string becomes the SVG component id prefix, so use the module's **full C++ enum name** (`TIME_PARAM`, `SIZE_CV_INPUT`, …). Duplicate names are an error.
- `kind` — `param` / `input` / `output` / `light` / `widget`. Inferred from a name suffix: `_PARAM` → param, `_INPUT` → input, `_OUTPUT` → output, `_LIGHT` → light. An explicit `kind:` overrides the suffix; a name with no recognized suffix and no `kind:` is an error.
- `widget` — VCV widget class name. Defaults per kind from `components.yaml`: param → `RoundBlackKnob`, input/output → `PJ301MPort`, light → `MediumLight<RedLight>`; kind `widget` has no default. The class (or a substring alias of it, §5) must be in the size database or checks fail with "unknown widget class".
- Position: per §2.3, **or** `rect:` — see below.
- `rect: {x, y, w, h}` — all four required, `w`/`h` positive; x/y is the top-left corner in mm. Only valid with `kind: widget` (screens/displays); mutually exclusive with every position key (`grid/col/row/x/y/dx/dy`). Emitted into the components layer as a `<rect>` with these exact bounds (its center is used for connector/label geometry). `widget:` is optional alongside `rect:`; without it the id suffix is the literal `Widget`.
- `label:` — sugar for one text element tied to the component. **Mapping form only** (a bare string is rejected): `{text, dy, dx?, size?, color?, casing?}` with `text` and `dy` required — there is no default offset; the baseline lands at the component center + `dy` (and center x + `dx`).

#### 2.4.2 Text

Allowed keys: `text, grid, col, row, x, y, dx, dy, size, color, casing, tracking`.

- `text` — required, non-empty. Rendered with the theme casing applied (overridable per element with `casing:`), baked to vector paths, anchored **middle** at x, with y the **baseline**.
- `size` — positive mm cap size, default 3.0.
- `color` — spec color (§2.11), default the theme's resolved text color.
- `tracking` — non-negative extra letter-spacing in mm, default 0.
- Position per §2.3. Labels are ordinary text elements; a "label row" is just a grid row of them.

#### 2.4.3 Value rings

`{ring: [...], around: NAME, gap?}` — allowed keys exactly `ring, around, gap`.

- `ring` — non-empty list of label strings, one per snap position of a stepped knob.
- `around` — must name a component **declared in this spec** whose widget has a known circular size (rings need a true knob radius); anything else is an error.
- `gap` — non-negative mm between the drawn knob edge and the label boxes, default 0.65.

Placement: labels sweep VCV's round-knob arc of ±0.83π (±149.4°) around the center — first label at the counter-clockwise limit, last at the clockwise limit, nothing at the bottom for even counts; a single label sits straight up. Each label sits just outside `knob_radius + gap`, pushed out by its own text box's projection so the box clears the ring at every angle. Ring labels render at 1.8 mm in the theme's value color (§3) and go to the `values` layer, not `panel`.

#### 2.4.4 `row:` / `place:` shorthand

Pure syntax sugar for consecutive columns of one grid row — no layout logic of its own:

```yaml
- row: {grid: main, at: labels}                    # at: row name
  place: [TIME, DENSITY, ~, SIZE]                  # bare string = text element; ~ skips that column
- row: {grid: main, at: knobs, widget: Trimpot}    # shared keys apply to every item
  place: [{name: TIME_PARAM}, {name: DENSITY_PARAM}, {name: PITCH_PARAM, widget: RoundBlackKnob}]
```

- Entry keys: exactly `row` and `place`. The `row` block requires `grid` and `at` (row name) and may carry shared keys `widget, kind, size, color, casing, dx, dy, label` applied to every placed item (item keys win on conflict; `widget`/`kind` are dropped for text items).
- `place` is a non-empty list; item i lands in column i (1-based). `~` (YAML null) skips a column. A bare string or `{text: ...}` mapping is a text element; a mapping with `name:` is a component; anything else is an error.

### 2.6 Zones

Decorative background tint rects, drawn in the panel layer above the background. Never checked for bounds or overlap.

`{x, y, w, h, rx?, fill?, opacity?}` — `x/y/w/h` required (`w`/`h` positive; x/y top-left), `rx` corner radius default 2.0, `fill` default `#ffffff`, `opacity` default 0.14, must be in (0, 1]. An 8-digit `#rrggbbaa` fill carries its own alpha, which **replaces** `opacity`.

### 2.7 Glyphs

Baked decorative SVG assets (waveform icons, tick scales, arrows), in their own `glyphs` layer. Never checked.

`{src, at: [x, y], scale?}` — `src` is resolved **relative to the spec file's directory** and must exist; `at` puts the asset's viewBox *center* at (x, y) mm; `scale` is a single non-zero number mapping viewBox units to mm, default 1.0 (negative mirrors). Asset contents are baked to absolute mm — only `path`/`line`/`polyline`/`polygon` elements are accepted (`rect`/`circle`/`ellipse`/`text`/`image` are rejected; convert shapes to paths first). Each element keeps its authored fill/stroke; internal transforms are folded in and stroke widths rescale with the placement.

### 2.8 Connectors

A non-empty list of `[NAME_A, NAME_B]` pairs of declared component names. Each pair draws one vertical bar, 0.3 mm wide, `#808080`, between the two components' centers. **Explicit only** — list every bar you want; nothing is ever connected automatically.

- The endpoints must share an x position within 0.1 mm tolerance (enough to absorb sub-0.02 mm column rounding noise); otherwise the run fails with a connector error.
- If either endpoint carries value-ring labels, the bar stops 0.6 mm clear of the nearest ring label on the side it approaches from, so it never runs through a ring caption. If clamping consumes the whole bar, no bar is drawn.
- Connectors are decorative: no bounds or overlap checks.

### 2.9 `overlaps_ok`

A non-empty list of entries, each a list of **one or two** matcher strings. A two-name entry suppresses overlap warnings between that pair (order-free); a one-name entry suppresses **every** overlap involving anything it matches.

Matcher forms:

| Form | Matches |
|---|---|
| a component name | that component (must be declared in this spec, or the entry is a parse error) |
| `title` | the panel title (text or logo) |
| `text:<content>` | a text element by its **rendered** content — after theme casing, so `text:OUT` for a label written as `Out` under an upper-casing theme. Empty content is an error. |
| `screw` | any mounting screw |
| `screw@x,y` | the screw at those coordinates; both sides are rounded to 2 decimals before comparing, so `screw@7.5,3` matches the warning's `screw@7.50,3.00` |

Warnings print exactly the labels these matchers compare against (`OVERLAP text:CV ~ LEVEL_CV_INPUT depth 0.42mm`), so a suppression can be copied from the warning. Convention: give every suppression a YAML comment saying why it is deliberate.

### 2.10 Title

`title: {text?, logo?, size?, tracking?, valign?, x?, y?, dx?, dy?}` — all optional; omit the block entirely for the defaults.

- `text` defaults to `name` (theme casing applies). `logo:` — a path to an SVG wordmark, resolved relative to the spec, mutually exclusive with `text` — replaces the text: the asset is scaled (aspect preserved) to the cap height of the title size, recolored to the title color, and baked.
- `size` — cap size in mm, default 5.0. `tracking` — mm, default 0.
- The title lives in the top 10 mm band by convention. `valign: baseline` (default) puts the baseline at `size + 1.0` mm; `valign: center` centers the cap height in the band (`baseline = (10 + cap_height) / 2`).
- Default x is the panel's horizontal center. Explicit `x:`/`y:` (y = baseline) override; `dx:`/`dy:` offset either.
- The title renders in the theme's `title_font` (falling back to `font`) and title color.

### 2.11 Colors

Every spec-level color (zone fill, text/label color) must match `#rrggbb` or `#rrggbbaa` — 6 or 8 hex digits, no 3-digit shorthand. (Theme-file colors are different: `#rgb` or `#rrggbb`, no alpha.)

---

## 3. Theme

Three layers merge in order, each **field** falling back to the previous layer only when unset:

1. built-in defaults;
2. the theme file — the conventional `~/.config/vcv-panel-gen/theme.yaml` if it exists, replaced wholesale by `--theme FILE` for one run, or by `$PANELGEN_THEME_FILE` (path substitution, used by tests);
3. the spec's inline `theme:` block.

| Field | Values | Default | Notes |
|---|---|---|---|
| `background` | hex color | `#e8e8e8` | panel fill |
| `font` | list of family names | `["DejaVu Sans"]` | first *installed* family wins (system font dirs are scanned); final fallback is the bundled `fonts/DejaVuSans.ttf`, so output builds on any machine |
| `title_font` | list of family names | = `font` | title only |
| `casing` | `upper` / `lower` / `title` / `preserve` | `preserve` | applied to title, labels, texts, ring labels (per-element `casing:` overrides) |
| `text_color` | hex color | auto | when unset, computed from background luminance ((0.2126R + 0.7152G + 0.0722B)/255): `#000000` if > 0.5, else `#ffffff` |
| `title_color` | hex color | = resolved text color | |
| `value_color` | hex color | auto | ring labels; when unset, the resolved text color blended 55 % / 45 % toward the background (quieter than labels) |
| `screws` | `light` / `dark` / `none` | `light` | `light` = silver `#c0c0c0`, `dark` = charcoal `#333333`, `none` = no screws |

Unknown theme fields are errors. Unless `screws: none`, four screw markers are placed at (7.5, 3.0) and (7.5, 125.5) plus mirrors at `width − 7.5` — drawn as r = 1.6 circles, checked (§4) with a 2.0 mm keep-out radius.

All text is baked to vector paths via fontTools; no font dependency ships in the output SVG.

---

## 4. Checks

Run on every generate and `--check`. Two categories:

**Bounds — errors.** Every checkable element must sit entirely inside `0..width × 0..128.5`; a violation reports the overhang in mm (`LEVEL_PARAM extends 1.20mm outside the panel bounds (0..50.8 x 0..128.5)`) and nothing is written. An element whose widget class has no size data is also an error.

**Overlaps — warnings.** Every intersecting pair of extents warns with both labels and the overlap depth in mm (`OVERLAP a ~ b depth 0.42mm`), unless suppressed by `overlaps_ok` (§2.9). Warnings never affect the exit code; the expectation is that every surviving warning at sign-off is either fixed or deliberately suppressed with a reason comment.

Extents are the **true drawn** sizes:

| Element | Extent |
|---|---|
| circle-widget component | circle of the widget's `components.yaml` diameter at its center |
| rect-widget / `rect:` component | its rect (a `rect:` always has this extent, regardless of any widget name) |
| text / label / ring label | width × cap-height box sitting on the baseline (fontTools metrics) |
| screw | circle, r = 2.0 mm |
| title | its text box, or the logo's scaled rect |
| zones, glyphs, connectors | **no extent — exempt from all checks** |

Overlap depth: circle/circle = `r1 + r2 − distance`; rect/rect = smaller axis overlap; circle/rect = radius minus the distance to the nearest clamped point.

---

## 5. Component size database

`components.yaml` (repo root) maps widget class → true drawn size in mm — the actual on-panel graphic, not a padded footprint. These numbers back the bounds/overlap checks and ring geometry.

| Widget | Size (mm) | | Widget | Size (mm) |
|---|---|---|---|---|
| RoundBlackKnob | d 9.6 | | VCVButton | d 6.1 |
| RoundSmallBlackKnob | d 7.68 | | VCVBezel / LEDBezel | d 7.2 |
| RoundBigBlackKnob | d 15.24 | | CKSS | 4.74 × 6.99 |
| RoundHugeBlackKnob | d 18.24 | | CKSSThree | 4.56 × 9.6 |
| Trimpot | d 6.05 | | Small/Medium/LargeLight | d 2 / 3 / 5 |
| PJ301MPort | d 8.03 | | ScrewSilver / ScrewBlack | d 5.08 |

Lookup order for a widget class: exact name; then with any C++-style `<Template>` argument stripped (`MediumLight<RedLight>` → `MediumLight`); then the longest matching substring alias from the file's `aliases:` table (so `RoundSmallBlackSnapKnob` resolves via the `RoundSmallBlack` needle to `RoundSmallBlackKnob`'s size, and any `*Port` hits `PJ301MPort`). A class that matches nothing is a check error — add it to `components.yaml` rather than guessing a size. The file's `defaults:` section supplies the per-kind default widgets (§2.4.1).

`tools/measure_components.py` regenerates the table by measuring an installed Rack ComponentLibrary's SVGs directly (px at 75 dpi → mm; the Light assets are authored in mm and detected as such); `--check` prints without writing.

---

## 6. The SVG contract

What the output promises — this is what VCV's `helper.py` and this repo's `mm_sync.py` / `preview.py` consume:

- `width`/`height` in mm with a 1:1 mm `viewBox`.
- Layer `panel` (Inkscape-style `<g inkscape:label="panel" inkscape:groupmode="layer">`): background rect, zones, screw circles, connector bars, title, all panel text — text always baked to `<path>` outlines, never `<text>`.
- Layer `values` (present only when a spec has rings): value-ring labels, kept out of `panel` so a MetaModule faceplate export (`SvgToPng.py --layer panel`) omits them.
- Layer `glyphs` (when present): baked decorative assets.
- Layer `components`, `style="display:none"`: one marker per placed component with `id="NAME#WidgetClass"` (`NAME#Widget` when no class is known) and fill encoding the kind — `#ff0000` param, `#00ff00` input, `#0000ff` output, `#ff00ff` light, `#ffff00` widget. Point components are `r="2"` circles at the true center; `rect:` components are `<rect>`s with their real bounds.
- Forbidden anywhere in the output: `<text>`, `<style>`, `<image>`, `<filter>`, `<mask>`, `<clipPath>`, and any `transform=` attribute. `validate.py` enforces this on every build — NanoSVG, the renderer Rack and MetaModule share, can't handle them.

VCV's SDK `helper.py` (`python helper.py createmodule <Slug> res/<Slug>.svg src/<Slug>.cpp`) reads the hidden components layer — position from the shape, kind from the fill, and the id verbatim (splitting off `#Widget...`) — which is why component `name`s must be the real C++ enum names. **Because the components layer is hidden, the raw SVG renders as background + labels only; never judge a panel from it — use the preview (§7).**

---

## 7. Preview

`--preview` / `--open` (or standalone: `.venv/bin/python preview.py PANEL.svg [--out P.svg] [--library DIR] [--open]`) composites real VCV ComponentLibrary art — knobs, jacks, buttons, switches — onto a copy of the panel at each component's position, so you see what the module will look like in Rack without a Rack build.

- Library resolution: `--library`, else `$VCV_COMPONENT_LIBRARY`, else conventional install locations (macOS: `/Applications/VCV Rack 2 Free.app/Contents/Resources/res/ComponentLibrary`, then Pro; equivalent paths on Windows/Linux).
- Widget classes resolve to assets by longest-substring match, so subclasses work; each unique asset is embedded once and reused.
- Lights draw as a red dot; `rect:` screens as a dark placeholder rect (Rack draws live content at runtime); an unknown class draws a magenta ring marker and is reported, never silently dropped.
- Via `panelgen.py`, a missing library is a non-fatal note — the panel SVG itself is always written first.

---

## 8. MetaModule header sync (`mm_sync.py`)

```bash
.venv/bin/python mm_sync.py --header <Slug>_info.hh --svg res/<Slug>.svg [--map map.yaml] [--strict]
```

Position-syncs a hand-maintained MetaModule `_info.hh` from a generated panel SVG. The header stays the source of truth for **structure** (element names, order, wrapper types, defaults, menu-only alt-params — a contract with the DSP code); the SVG is the source of truth for **geometry**. The tool rewrites only the x/y mm floats of each matched element literal (plus width/height for display rects), and on **any** mismatch exits nonzero without writing anything.

Matching: each SVG component id `NAME#WidgetClass` derives a header enum name by convention — strip one `_PARAM`/`_INPUT`/`_OUTPUT`/`_LIGHT` suffix, CamelCase the remaining underscore-separated words, then append a suffix: params by widget (`RoundBlackKnob`/`RoundBigBlackKnob`/`RoundSmallBlackKnob`/`RoundBlackSnapKnob`/`Trimpot` → `Knob`, `VCVButton` → `Button`, `CKSS` → `Switch`; any other param widget needs a `--map` entry), inputs → `In`, outputs → `Out`, lights → `Light`, widgets → nothing. So `TIME_PARAM#RoundBlackKnob` → `TimeKnob`, `SIZE_CV_INPUT#PJ301MPort` → `SizeCvIn`.

`--map FILE.yaml` wires up anything off-convention:

```yaml
FreezeButton: FREEZE_INPUT        # EnumName: SVG_ID
AltParam: null                    # menu-only element, deliberately position-less
Display: {id: SCREEN, mm_aspect: "16:9"}   # rect displays only: reshape w/h around the synced geometry
ignore: [VCV_ONLY_PARAM]          # SVG components with deliberately no header element
```

Rules: an SVG component with no match is always an error (a panel control must never silently stop syncing); two components resolving to the same enum is an error; header elements with no match are left untouched and reported — with `--strict`, an element that is neither synced nor explicitly mapped to `null` is an error instead. Circle components require `Center` coordinates in the header element literal; rect components accept `TopLeft` or `Center`.

For the faceplate image itself, regenerate the PNG from the same SVG with the MetaModule SDK's `SvgToPng.py --layer panel` (which is why ring labels live in the `values` layer).

---

## 9. Worked example

A minimal but complete, actually-generatable spec — one knob with a stacked CV input, each labeled, joined by a connector bar:

```yaml
slug: Example
name: DEMO
hp: 10

elements:
  - {text: Level, x: 25.4, y: 40}
  - {name: LEVEL_PARAM, x: 25.4, y: 50}
  - {name: LEVEL_CV_INPUT, x: 25.4, y: 65}
  - {text: CV, x: 25.4, y: 73.5}

connectors:
  - [LEVEL_PARAM, LEVEL_CV_INPUT]
```

```bash
.venv/bin/python panelgen.py example.yaml --check
.venv/bin/python panelgen.py example.yaml --out /tmp/demo/Demo.svg --preview --open
```

This builds clean — `--check` reports no errors or warnings — and writes `Demo.svg` with a `LEVEL_PARAM#RoundBlackKnob` circle at (25.4, 50.0) and a `LEVEL_CV_INPUT#PJ301MPort` circle at (25.4, 65.0) in its hidden components layer, plus `Demo.preview.svg`/`Demo.preview.html` when ComponentLibrary art is available. It is pinned as a regression test: `tests/test_readme_example.py` builds this exact YAML and asserts zero errors/warnings and both component ids — keep the two in sync if either changes.

## 10. Canonical examples

The four specs in `tests/fixtures/robotboy/` regenerate shipped RobotBoy panels with exact component parity (see `tests/test_parity_*.py`) and are the best documentation-by-example:

| Spec | Demonstrates |
|---|---|
| `mf20filter.yaml` | 3-column grid, hero (`RoundBigBlackKnob`) knobs, trimpot+jack stacks with connectors, stereo I/O pairs |
| `lop.yaml` | `logo:` title, value ring around a snap knob, button+trig stacks, zone tint, overlap suppression with a reason comment |
| `loooop.yaml` | multi-grid repetition at scale, tints-as-zones, `row:`/`place:` shorthand throughout |
| `particules.yaml` | multiple grids plus deliberate off-grid absolute placement, decorative glyphs, `screws: none`, kind inference |

## 11. The razor

When a panel needs polish, in strict order:

1. **Fix the spec's numbers** (grid rows/cols, absolute x/y) — the spec should read as the layout's derivation.
2. **`dx:`/`dy:` offsets** — for one deliberate deviation from an otherwise-right grid.
3. **Only then** consider requesting a new tool feature — and only if a second panel would want it too.

Never hand-edit a generated SVG — regenerate from the spec. Never invent controls: component names come from the module's C++ (enum names, `config*` calls) or from the user; if a control list is ambiguous, ask.
