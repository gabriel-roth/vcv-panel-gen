# vcv-panel-gen-redux

A grid-based VCV Rack / MetaModule front-panel SVG generator. This is v2 of
`vcv-panel-gen`: same rendering contract, same rough workflow, but a
deliberately **unopinionated** engine underneath.

Scripts here do mechanical arithmetic and validation only — grid math,
bounds checking, overlap detection, SVG assembly. They have no opinion about
what makes a good layout. All of that judgment (which controls belong
together, how close, vertical rhythm, jack-row justification, and so on)
lives in the companion **`vcv-panel` skill**
(`skills/vcv-panel/SKILL.md`, installed to `~/.claude/skills`) — read that
if you're actually laying out a panel. This README covers the tool; it does
not duplicate the skill's recipes.

Design background: `docs/superpowers/specs/2026-07-17-grid-panel-generator-design.md`.

---

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Dependencies are `fonttools` and `PyYAML` only. Python 3.10+.

---

## CLI usage

```bash
panelgen.py SPEC [--out OUT.svg] [--check] [--theme FILE.yaml]
                 [--library DIR] [--preview] [--open]
```

- `SPEC` — path to a spec YAML file (see below).
- `--out OUT.svg` — where to write the panel SVG. Required unless `--check`
  is given. **The generator refuses to write inside its own checkout** — a
  module's panel belongs in the module's own repo (a system temp directory
  is exempted, so demos and `pytest`'s `tmp_path` still work).
- `--check` — validate the spec and its layout without writing anything.
  Prints `OK: ... builds (nothing written).` on success.
- `--theme FILE.yaml` — use this theme file instead of the conventional
  `~/.config/vcv-panel-gen/theme.yaml` for this run only.
- `--library DIR` — VCV ComponentLibrary directory for `--preview`/`--open`
  (default: `$VCV_COMPONENT_LIBRARY` or a conventional per-OS install
  location).
- `--preview` — after a successful generate, composite real ComponentLibrary
  art onto the written SVG, producing `<out-stem>.preview.svg` and
  `<out-stem>.preview.html` beside `--out`. A missing ComponentLibrary is a
  note on stderr, not a failure — the panel SVG is written either way.
- `--open` — like `--preview`, and also opens the preview HTML in a browser.

Warnings (suppressible overlaps) print on stderr prefixed `WARNING:` and do
**not** affect the exit code. Errors (bounds violations, bad refs, a spec
that won't parse) print prefixed `ERROR:` and set exit code 1; `--check`
follows the same rule, so a clean `--check` run always exits 0.

`PANELGEN_THEME_FILE`, if set in the environment, replaces the conventional
`~/.config/vcv-panel-gen/theme.yaml` lookup path outright (used by this
repo's own test suite so tests never read a real user config; not something
a normal invocation needs to set).

---

## Spec format

Condensed reference — the authoritative version is design doc §4.

YAML mapping. **Unknown keys at any level are errors** (catches typos early).

### Top level

| Key | Required | Meaning |
|---|---|---|
| `slug`, `name`, `hp` | yes | slug is a bare identifier; `hp` sets panel width = `hp × 5.08` mm; height is fixed at 128.5 mm |
| `elements` | yes | flat list of placed things (below) |
| `theme` | no | inline theme overrides, same schema as the theme file |
| `title` | no | `{text?, size, tracking, valign, logo, x, y, dx, dy}` — default text is `name`, default position centered in the top 10 mm band at baseline valign; `logo:` replaces text with a baked SVG wordmark |
| `grids` | no | map of grid name → grid def (below) |
| `zones` | no | decorative rects `{x, y, w, h, rx, fill, opacity}` |
| `glyphs` | no | baked external SVG assets `{src, at: [x, y], scale?}` |
| `connectors` | no | list of `[NAME_A, NAME_B]` — a vertical 0.3 mm `#808080` bar between the two named elements' centers (same x required); explicit only, never automatic |
| `overlaps_ok` | no | list of pairs (or single names) suppressing overlap warnings — see below |
| `side_margin` | no | default 8 mm; used only as the default span for a grid's columns when a grid doesn't specify `from`/`to` |

A **grid** is nothing but named x values (columns, referenced by 1-based
index) and named y values (rows, referenced by name) — no bands, no sizing,
no content model:

```yaml
grids:
  main:
    cols: {count: 4, from: 12.6, to: 63.6}   # evenly spaced centers, or:
    # cols: [11.9, 38.1, 59.845]             # an explicit x list
    rows:
      knobs: 42.088
      cv: 53.746
    # rows: {from: 31.5, to: 101.7, count: 8, names: [...]}   # evenly spaced
```

Every **element** is positioned by exactly one of `grid:`/`col:`/`row:` or
absolute `x:`/`y:` per axis, freely mixed, plus optional `dx:`/`dy:`
offsets. Kind (`param`/`input`/`output`/`light`) is inferred from a
`_PARAM`/`_INPUT`/`_OUTPUT`/`_LIGHT` name suffix, overridable with `kind:`;
`widget:` defaults per kind from `components.yaml`. A bare string in a `row:`
+ `place:` list is a text element; `row:`/`place:` is pure syntax sugar for
consecutive columns, no layout logic of its own. See the design doc and the
skill's spec crib for the full element grammar (`ring:`, `label:` sugar,
screen `rect:`, etc.).

### Worked example

A minimal but complete, actually-generatable spec — one knob with a stacked
CV input, each labeled, joined by a connector bar:

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
.venv/bin/python panelgen.py example.yaml --out /tmp/demo/Demo.svg --preview --open
```

This builds clean — `--check` reports no errors or warnings — and writes
`Demo.svg` with a `LEVEL_PARAM#RoundBlackKnob` circle at (25.4, 50.0) and a
`LEVEL_CV_INPUT#PJ301MPort` circle at (25.4, 65.0) in its hidden components
layer, plus `Demo.preview.svg`/`Demo.preview.html` when ComponentLibrary art
is available. I generated this exact spec to a scratch directory and
confirmed all three files, and its component ids/positions, as part of this
task's smoke test (see below). It's also pinned as a regression test:
`tests/test_readme_example.py` builds this exact YAML and asserts zero
errors/warnings and both component ids — keep the two in sync if either
changes.

### Overlap policy

Bounds violations are errors. Overlaps between two drawn extents are
warnings, printed with pair names and depth in mm. Suppress a specific one
deliberately, with a reason comment:

```yaml
overlaps_ok:
  - [text:OUT, "screw@53.46,125.50"]   # matches rendered text / a screw by coords
  - [RING_A, RING_B]                    # a pair of element names
  - [SCREEN]                            # single name: anything may overlap SCREEN
```

Matcher forms: element `name`s; `text:<content>` (the rendered text, after
theme casing); `screw` (any screw) or `screw@x,y`; `title`. Zones, glyphs,
and connectors are decorative and never warn.

---

## Theme file

`~/.config/vcv-panel-gen/theme.yaml` — same path and schema as v1, so an
existing v1 theme file carries over unchanged. Three layers merge in order,
each field falling back to the previous layer only when unset:

1. built-in defaults (`#e8e8e8` background, DejaVu Sans, `preserve` casing,
   light screws)
2. the theme file (`--theme FILE` substitutes a different file for one run;
   `PANELGEN_THEME_FILE` substitutes the conventional path itself, for
   tests)
3. the spec's own inline `theme:` block

Fields: `background`, `font` (family list), `title_font` (family list,
defaults to `font`), `casing` (`upper`/`lower`/`title`/`preserve`),
`text_color`, `title_color`, `screws` (`light`/`dark`/`none`), `value_color`
(for ring labels).

---

## The SVG / VCV contract

Unchanged from v1 — this is what `helper.py` (VCV Rack SDK) and this repo's
`mm_sync.py` both read:

- `width`/`height` in mm, `viewBox` a 1:1 mm mapping.
- Layer `panel`: background, zones, screw circles, connectors, title, text —
  all baked to vector paths (via `fontTools`), never `<text>`.
- Layer `values` (when present): value-ring labels, kept out of `panel` so a
  MetaModule faceplate export (`SvgToPng.py --layer panel`) omits them.
- Layer `glyphs` (when present): baked decorative SVG assets.
- Layer `components`, `style="display:none"`: one marker per placed
  component — a `circle` (or `rect` for a `rect:`-defined widget) with
  `id="NAME#WidgetClass"` and fill by kind (`#ff0000` param, `#00ff00`
  input, `#0000ff` output, `#ff00ff` light, `#ffff00` widget). `helper.py`
  reads this layer to generate VCV's `.svg` component metadata; `mm_sync.py`
  reads it to sync a hand-maintained MetaModule `_info.hh`'s x/y/width/height
  to match.
- No `<text>`/`<style>`/`<image>`/`<filter>`/`<mask>`/`<clipPath>` and no
  `transform=` anywhere in the output (`validate.py` enforces this —
  NanoSVG, which Rack and MetaModule both use to render panels, can't
  handle them).

---

## Preview

The bare panel SVG's components layer is `display:none`, so it renders as
background + labels only — **never judge a panel from the raw SVG.**
`--preview`/`--open` composite real VCV ComponentLibrary art (knobs, jacks,
buttons, lights) onto a copy of the SVG so you see what the panel will
actually look like in Rack, without needing a Rack build. An unknown widget
class draws a magenta marker and is reported, rather than failing silently.

---

## Component sizes

`components.yaml` maps widget class → true drawn size (mm, not a padded
footprint) plus a substring-alias table so subclasses (e.g.
`RoundSmallBlackSnapKnob`) resolve without their own entry, and kind
defaults (`param`→`RoundBlackKnob`, `input`/`output`→`PJ301MPort`,
`light`→`MediumLight<RedLight>`). These numbers back both the bounds/overlap
checks and the skill's spacing recipes. `tools/measure_components.py`
regenerates the table by measuring an installed Rack's ComponentLibrary SVGs
directly (75 dpi px → mm, with a special case for the Light assets, which
are the one ComponentLibrary class already authored in mm); re-run it if
you need to refresh against a different Rack build.

---

## Canonical examples: the RobotBoy fixtures

`tests/fixtures/robotboy/` holds four specs — `mf20filter.yaml`, `lop.yaml`,
`loooop.yaml`, `particules.yaml` — that regenerate RobotBoy's four shipped
panels (MF-20, Löp, Loooop, Particules) using this tool. They're both the
best documentation-by-example (multi-column grids, hero knobs, stacked
control+jack pairs with connectors, stereo I/O pairs, a `logo:` title, value
rings, zone tints, deliberate overlap suppression, multi-grid panels,
off-grid absolute placement, `screws: none`) and a parity guarantee: the
matching `tests/test_parity_*.py` files assert that every component center
in the generated SVG matches the corresponding shipped reference SVG
(`tests/fixtures/robotboy/reference/`) to within 0.001 mm, since RobotBoy's
C++ hardcodes `mm2px` coordinates against those exact positions — and, for
the three originally v1-generated panels, that panel-layer path geometry
(labels, title) matches to within 0.01 mm bounding-box tolerance, since same
glyph renderer + same positions should mean identical path data. Particules
was hand-built in Inkscape, so its parity is components + zones + visual
preview review rather than path-for-path.

---

## Relationship to v1

v1 (`~/Dev/vcv-panel-gen`) is untouched and stays in place — other modules
(onbetap, ondes, yellowjacket) still build their panels with it, and nothing
here modifies or removes it.

Philosophically, v1's layout engine (`layout.py`) owned real layout
judgment: band stacking, gap distribution, weighted columns, jack-row
justification, stereo-pair idioms, cv/trig companion placement,
value-ring dodge logic. Escaping any of it meant fighting the tool with
`nudges:` arithmetic against positions it computed and never showed you.
This redux drops all of that from the scripts: a grid is just named x/y
values, elements place freely against any grid or absolute coordinate, and
the *only* automatic checks are bounds (error) and overlap (warning). The
judgment v1 used to apply for you now lives explicitly in the
`vcv-panel` skill, applied by whoever is writing the spec — see
`docs/superpowers/specs/2026-07-17-grid-panel-generator-design.md` §1–2 for
the full rationale and the non-goals this rules out.

What v1 got right and this tool keeps unchanged: the theme system, baked
text via fontTools, real-art preview, true component-size data, and the
SVG/VCV rendering contract itself.

---

## Testing

```bash
.venv/bin/python -m pytest -q
```
