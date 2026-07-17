# Grid Panel Generator (v2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A grid-based, unopinionated VCV Rack panel SVG generator (scripts) plus a layout-judgment skill, replacing \~/Dev/vcv-panel-gen (v1) and able to regenerate all four RobotBoy panels with exact component-center parity.

**Architecture:** Flat Python modules. `spec.py` validates a YAML spec; `resolve.py` does pure grid arithmetic to place every element at absolute mm; `checks.py` errors on panel-edge overflow and warns on element overlap; `svgdoc.py` emits the v1-compatible SVG (mm viewBox, hidden `components` layer, `id="NAME#WidgetClass"`, kind-colored shapes, everything baked to paths). Clean v1 modules (fonts, theme, logo, images, validate, preview, mm_sync) are ported verbatim or near-verbatim. All layout *judgment* goes in `skills/vcv-panel/SKILL.md`.

**Tech Stack:** Python 3.10+, `fonttools>=4.0`, `PyYAML>=5.1`, pytest. No other deps.

**Authoritative references (read them, they exist locally):**
- Design spec: `docs/superpowers/specs/2026-07-17-grid-panel-generator-design.md` (in this repo) — the schema and semantics source of truth. Read it before any task.
- v1 source: `/Users/gabrielroth/Dev/vcv-panel-gen/` — port source. Its `AGENTS.md` documents v1 behavior.
- RobotBoy: `/Users/gabrielroth/Dev/RobotBoy/` — reference SVGs in `res/`, v1 specs in `panel-specs/`, Particules extras in `.claude/worktrees/panel-refactor/panel-specs/`.

## Global Constraints

- Python 3.10+; dependencies exactly `fonttools>=4.0`, `PyYAML>=5.1` (requirements.txt).
- Run tests with the project venv: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest` (Task 1 creates it); afterwards always `.venv/bin/python -m pytest -q`.
- Output SVG contract (never violate): `width`/`height` in mm with 1:1 viewBox; layers `panel`, `values`, `glyphs`, `components` (components has `style="display:none"`); component fills `#ff0000` param / `#00ff00` input / `#0000ff` output / `#ff00ff` light / `#ffff00` widget; ids `NAME#WidgetClass`; no `<text>`, `<style>`, `<image>`, `<filter>`, `<mask>`, `<clipPath>`, no `transform=` attributes.
- Panel height always 128.5 mm; width = hp × 5.08.
- Unknown YAML keys at any level are `SpecError`s.
- User theme file: `~/.config/vcv-panel-gen/theme.yaml`, same schema as v1. Tests must never read the real user file — theme loading takes an explicit path or None.
- Commit after every task (short messages, ≤15 words, no AI attribution, no Co-Authored-By).
- Ported v1 files keep their v1 behavior; adapt imports only unless a task says otherwise.

---

### Task 1: Scaffold + verbatim ports of clean v1 modules

**Files:**
- Create: `requirements.txt`, `.gitignore`, `glyphs.py`, `fontresolve.py`, `theme.py`, `logo.py`, `images.py`, `validate.py`, `fonts/DejaVuSans.ttf`, `constants.py`
- Test: `tests/test_glyphs.py`, `tests/test_fontresolve.py`, `tests/test_theme.py`, `tests/test_logo.py`, `tests/test_images.py`, `tests/test_validate.py` (ported)

**Interfaces:**
- Produces: `glyphs.TextRenderer(font_path, font_number=0)` with `.text_to_path_d(text, x, y, size_mm, anchor, tracking_mm)`, `.text_width(text, size_mm, tracking_mm)`, `.cap_height(size_mm)`; `fontresolve.build_font_index()`, `fontresolve.resolve_font_stack(stack, index)`, `fontresolve.BUNDLED_FONT`; `theme.Theme`, `theme.resolve_theme(user_path, inline_mapping)`, `theme.apply_casing(text, casing)`, `theme.resolve_text_color/resolve_title_color/resolve_value_color/resolve_screw_color`; `logo.py` / `images.py` baked-path helpers; `validate.validate_svg(svg_text)`.

- [ ] **Step 1: Set up repo skeleton**

```bash
cd /Users/gabrielroth/Dev/vcv-panel-gen-redux
printf 'fonttools>=4.0\nPyYAML>=5.1\n' > requirements.txt
printf '.venv/\n__pycache__/\n*.pyc\n.pytest_cache/\n' > .gitignore
python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt pytest
```

- [ ] **Step 2: Port modules verbatim from v1**

Copy from `/Users/gabrielroth/Dev/vcv-panel-gen/`: `glyphs.py`, `fontresolve.py`, `theme.py`, `logo.py`, `images.py`, `validate.py`, `fonts/DejaVuSans.ttf`, and the corresponding `tests/test_*.py` files. Also create a **trimmed** `constants.py` containing ONLY the unopinionated constants v1 defines (copy values verbatim from v1 `constants.py`): `HP_MM`, `PANEL_H_MM`, `MOUNT_INSET_X`, screw y positions, screw drawn radius, `SIDE_MARGIN_MM`, `TITLE_BAND_MM`, `LABEL_FONT_MM`, `TITLE_FONT_MM`, `VALUE_FONT_MM`, `KNOB_SWEEP_RAD`, `VALUE_RING_GAP_MM`, `CONNECT_LINE_WIDTH`, `CONNECT_LINE_COLOR`, `COLORS` (kind→components-layer fill), `VALUE_TEXT_MIX`, `SCREW_COLORS`, `FONT_PATH`/bundled-font pointer, and the theme defaults `theme.py` imports. Do NOT copy `ROW_TYPES`, band heights, reserved diameters, pair/stack/gutter gaps, tint constants (those are v1 layout opinions; the true drawn diameters move to `components.yaml` in Task 2). Fix any imports the ported modules make into deleted constants by copying just those constants over too — the rule is: nothing row/band/idiom-related survives.

- [ ] **Step 3: Run ported tests**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass. If a ported test imports `layout` or `spec` from v1, drop that test file — it tests v1 behavior we're replacing.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "Port clean v1 modules: fonts, theme, logo, images, validate"
```

---

### Task 2: Component size database

**Files:**
- Create: `components.py`, `components.yaml`, `tools/measure_components.py`
- Test: `tests/test_components.py`

**Interfaces:**
- Produces: `components.WidgetSize(shape: str, d: float|None, w: float|None, h: float|None)` (frozen dataclass; shape `"circle"` or `"rect"`); `components.ComponentDB` with `.size_for(widget_class: str) -> WidgetSize|None` (longest-substring match, same technique as v1 `preview.py` `CLASS_ASSETS` so `RoundSmallBlackSnapKnob` matches `RoundSmallBlackKnob`) and `.default_widget(kind: str) -> str`; `components.load_component_db(path=None) -> ComponentDB` (default path = `components.yaml` beside the module).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_components.py
from components import load_component_db

def test_known_knob_true_diameter():
    db = load_component_db()
    s = db.size_for("RoundBlackKnob")
    assert s.shape == "circle" and abs(s.d - 9.6) < 0.01

def test_substring_match_for_subclass():
    db = load_component_db()
    assert db.size_for("RoundSmallBlackSnapKnob").d == db.size_for("RoundSmallBlackKnob").d

def test_unknown_class_returns_none():
    assert load_component_db().size_for("TotallyMadeUpWidget") is None

def test_default_widgets():
    db = load_component_db()
    assert db.default_widget("param") == "RoundBlackKnob"
    assert db.default_widget("input") == "PJ301MPort"
    assert db.default_widget("output") == "PJ301MPort"
    assert db.default_widget("light") == "MediumLight<RedLight>"
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_components.py -q` → import error.

- [ ] **Step 3: Implement**

`components.yaml` entries: for every widget class v1 knows (see v1 `constants.py` true diameters and v1 `preview.py` `CLASS_ASSETS` list), record **true drawn size in mm**. Sources: v1 `TRUE_KNOB_DIAM=9.6`, `TRUE_SMALL_KNOB_DIAM=7.68`, `TRUE_HERO_KNOB_DIAM=15.24`; for classes without a v1 TRUE_ constant (PJ301MPort, Trimpot, VCVButton, VCVBezel/LEDBezel, CKSS, lights, ScrewSilver/ScrewBlack), measure by reading the asset SVG px size from the installed Rack ComponentLibrary (`/Applications/VCV Rack 2 Free.app/Contents/Resources/res/ComponentLibrary`, or `Rack 2 Pro`) at `25.4/75` mm/px — write `tools/measure_components.py` to do this (reuse v1 `preview.py` `_px_size` logic) and run it once to fill the YAML; commit the resulting YAML. Include a `defaults:` section mapping kind→widget class. Lights: use the composite drawn size of the light class. `ComponentDB.size_for` strips template args for lookup after exact match fails (`MediumLight<RedLight>` → try exact, then `MediumLight`), then falls back to longest-substring match.

- [ ] **Step 4: Run tests** — expected PASS.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "Add component size database with Rack-measured true sizes"`

---

### Task 3: Spec parsing and validation

**Files:**
- Create: `spec.py`
- Test: `tests/test_spec.py`

**Interfaces:**
- Produces: `spec.SpecError(ValueError)`; dataclasses `GridSpec(cols, rows)` (cols: raw — explicit `list[float]` or `{count, from?, to?}` dict, stored normalized as `ColsSpec(count, x_from, x_to, explicit)`; rows: `dict[str, float]` after normalizing the `{from,to,count,names}` form); `Position(grid, col, row, x, y, dx, dy)`; `ComponentEl(name, kind, widget, pos, rect, label)` where `label` is `LabelSpec(text, dx, dy, size, color, casing)|None` and `rect` is `Rect(x, y, w, h)|None`; `TextEl(text, pos, size, color, casing, tracking)`; `RingEl(labels, around, gap)`; `Zone(x, y, w, h, rx, fill, opacity)`; `GlyphEl(src, x, y, scale)`; `TitleSpec(text, logo, size, tracking, valign, x, y, dx, dy)`; `PanelSpec(slug, name, hp, theme_mapping, title, grids, elements, zones, glyphs, connectors, overlaps_ok, side_margin)`; `spec.load_spec(path) -> PanelSpec` and `spec.parse_spec(mapping, base_dir) -> PanelSpec`.
- Schema definition: design doc §4. Follow it exactly, including the `row:`/`place:` shorthand, which `parse_spec` expands into ordinary `ComponentEl`/`TextEl` entries (col = 1-based position in `place`, `~`/None skips a column, bare string = TextEl).

**Validation rules (each is a test):** unknown keys anywhere → SpecError naming the key and its path; `slug`/`name`/`hp` required; `hp` positive int; element must have per-axis exactly one x-source (`grid`+`col` or `x`) and one y-source (`row` needs `grid`, or `y`); `col` is a 1-based int within the grid's column count; `row` must name a row in the referenced grid; component names must be unique and non-empty; `kind` inferred from name suffix `_PARAM/_INPUT/_OUTPUT/_LIGHT` (case-sensitive), else `kind:` required, allowed values `param|input|output|light|widget`; `rect:` only with `kind: widget` (or inferred none), and `rect` replaces pos (mutually exclusive with grid/x/y); `ring.around` must reference a declared component name; `connectors` entries are 2-lists of declared names; `overlaps_ok` entries are 1- or 2-lists of declared names; grid `rows` evenly-spaced form requires `names` with `len == count`; colors must match `^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$`.

- [ ] **Step 1: Write failing tests** — one test per rule above plus one happy-path test loading a small inline spec (write YAML to `tmp_path`) exercising: two grids, both `cols` forms, both `rows` forms, a component with grid pos + dy, a component with absolute pos, a rect widget, a text element, a ring, the row/place shorthand (including a `~` skip and bare-string labels), attached label, zones, glyphs, connectors, overlaps_ok. Assert the parsed dataclass contents, e.g.:

```python
def test_row_place_shorthand_expands():
    p = load(SPEC_YAML)  # helper writing YAML to tmp and calling load_spec
    knobs = [e for e in p.elements if isinstance(e, ComponentEl) and e.pos and e.pos.row == "knobs_a"]
    assert [k.pos.col for k in knobs] == [1, 2, 4]   # '~' skipped col 3

def test_unknown_key_rejected():
    with pytest.raises(SpecError, match="wobble"):
        load(SPEC_YAML.replace("hp: 15", "hp: 15\nwobble: 3"))

def test_kind_inferred_from_suffix():
    p = load(SPEC_YAML)
    assert next(e for e in p.elements if getattr(e, "name", "") == "TIME_PARAM").kind == "param"
```

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement `spec.py`.** Reuse v1 `spec.py`'s `_reject_unknown` pattern for unknown-key errors. Pure parsing/validation — no positions computed here.
- [ ] **Step 4: Run tests** — PASS. Run full suite too.
- [ ] **Step 5: Commit** — `"Add spec schema: grids, mixed positioning, row shorthand, validation"`

---

### Task 4: Resolver (grid arithmetic → absolute mm)

**Files:**
- Create: `resolve.py`
- Test: `tests/test_resolve.py`

**Interfaces:**
- Consumes: `spec.PanelSpec`, `theme.Theme`, `components.ComponentDB`, `glyphs.TextRenderer`.
- Produces: `resolve.PlacedComponent(name, kind, widget, x, y, rect)` (center mm, or rect for widget kind); `PlacedText(text, x, y, size, color, tracking, layer)` — `x` = anchor-middle center, `y` = **baseline**, `layer` in `{"panel","values"}`, casing already applied; `PlacedBar(x, y1, y2, width, color)` (connectors); `PlacedScrew(x, y)`; `Layout(width, height, components, texts, bars, screws, zones, glyphs, title)` where `title` is a `PlacedText` or a `PlacedLogo(src, x, y, height_mm)`; `resolve.resolve(spec, theme, db, renderer, title_renderer) -> Layout`; `resolve.ResolveError(ValueError)`.

**Semantics (each a test):**
- Grid cols `{count: n, from: a, to: b}` → centers `a + (b-a)*i/(n-1)` for i in 0..n-1; `count: 1` → `(a+b)/2`; omitted from/to → `side_margin` and `width - side_margin`. Explicit list used verbatim. Rows same math; evenly-spaced rows assigned to `names` in order.
- Element position = axis sources per spec + `dx`/`dy`.
- Widget default: `db.default_widget(kind)` when `widget` omitted.
- Attached label sugar → `PlacedText` at `(cx + label.dx, cy + label.dy)`, default size `LABEL_FONT_MM`, theme text color/casing unless overridden. **`label.dy` is required in the schema** (no default — that would be an opinion); Task 3 already enforces this.
- Ring: port v1 `layout._value_ring_labels` (v1 layout.py:222) minus the dodge logic: n labels at angles evenly spaced from `-KNOB_SWEEP_RAD` to `+KNOB_SWEEP_RAD` (0 = straight up), label center pushed outward from the knob center so its text box clears `true_radius + gap`; keep v1's exact radial-push math otherwise, text size `VALUE_FONT_MM`, color `resolve_value_color(theme)`, layer `"values"`.
- Connectors: port v1 `layout._add_explicit_connectors` (layout.py:625) trimming behavior: vertical bar between the two components' drawn edges (uses `db.size_for` radii), requires |xA − xB| < 0.01 else `ResolveError`, width `CONNECT_LINE_WIDTH`, color `CONNECT_LINE_COLOR`.
- Screws: port v1's mounting-marker placement exactly (positions from `MOUNT_INSET_X`/screw y constants, narrow-panel rule if v1 has one — read v1 layout.py/svgdoc.py to find where markers are computed); `screws: none` → empty list.
- Title: port v1's title placement math verbatim (band `TITLE_BAND_MM`, `valign` baseline|center, tracking, `title_logo` variant via `logo.py`). Then apply optional spec `x`/`y` overrides and `dx`/`dy`.
- Text elements: theme casing applied via `apply_casing`; default size `LABEL_FONT_MM`; default color `resolve_text_color(theme)`.

- [ ] **Step 1: Write failing tests.** Cover: even-col math (4 cols 12.6→63.6 gives [12.6, 29.6, 46.6, 63.6]); count-only span uses side_margin; explicit cols verbatim; mixed grid-x + absolute-y; dx/dy applied; default widget per kind; attached label placement; ring label count/angles symmetric and on the values layer; connector bar trimmed by both radii and same-x enforcement; screws none/dark; title default centering and valign. Example:

```python
def test_even_columns():
    lay = resolve_min(grids={"g": {"cols": {"count": 4, "from": 12.6, "to": 63.6},
                                   "rows": {"r": 40.0}}},
                      elements=[{"name": f"K{i}_PARAM", "grid": "g", "col": i, "row": "r"}
                                for i in (1, 2, 3, 4)])
    assert [round(c.x, 3) for c in lay.components] == [12.6, 29.6, 46.6, 63.6]
```

(`resolve_min` = test helper building a PanelSpec via `spec.parse_spec` with slug/name/hp boilerplate and a default theme with `screws: none`, bundled DejaVu renderer.)

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement `resolve.py`.** Pure arithmetic; read v1 `layout.py` ONLY for the four ported behaviors named above (ring, connectors, screws, title). Nothing else from v1 layout comes over.
- [ ] **Step 4: Run tests** — PASS; full suite green.
- [ ] **Step 5: Commit** — `"Add resolver: grid math, rings, connectors, screws, title"`

---

### Task 5: Checks (bounds error, overlap warning)

**Files:**
- Create: `checks.py`
- Test: `tests/test_checks.py`

**Interfaces:**
- Consumes: `resolve.Layout`, `spec.PanelSpec`, `components.ComponentDB`, `glyphs.TextRenderer`.
- Produces: `checks.Report(errors: list[str], warnings: list[str])`; `checks.run_checks(layout, spec, db, renderer) -> Report`.

**Semantics:**
- Drawn extents: circle components → circle of radius `size.d/2`; rect components/screens → their rect; texts → rect from `renderer.text_width(...)` × `renderer.cap_height(...)` sitting on the baseline (box top = y − cap_height, bottom = y); screws → circle at drawn screw radius; title text/logo → its rect. Zones, glyphs, bars: no extent (exempt).
- **Errors:** any extent outside `[0,width]×[0,128.5]` (message includes element name and overhang mm); unknown widget class (no `size_for` hit); duplicate placed-component name (defense in depth).
- **Warnings:** every intersecting pair among {components, screws, texts, title}, message `"OVERLAP <A> ~ <B> depth <d>mm"` where A/B are component names or `text:<content>`/`screw@x,y`/`title`; suppressed if `[A,B]` (order-free) or `[A]` or `[B]` in `overlaps_ok`. Circle/circle: `r1+r2−dist`; rect/rect: min axis overlap; circle/rect: clamp-point distance.
- Ring labels participate as texts. Two texts overlapping DO warn (catches crowded labels).

- [ ] **Step 1: Write failing tests** — off-panel circle errors; off-panel text errors; two overlapping knobs warn with depth; suppression by pair (either order) and by singleton; text-over-knob warns; non-overlapping quiet; unknown widget errors; zones never warn.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement `checks.py`** (pure geometry, ~120 lines).
- [ ] **Step 4: Run tests** — PASS; full suite green.
- [ ] **Step 5: Commit** — `"Add checks: bounds errors, suppressible overlap warnings"`

---

### Task 6: SVG document builder

**Files:**
- Create: `svgdoc.py`
- Test: `tests/test_svgdoc.py`

**Interfaces:**
- Consumes: `resolve.Layout`, `theme.Theme`, renderers.
- Produces: `svgdoc.build_svg(layout, theme, renderer, title_renderer) -> str`.

Adapt v1 `svgdoc.py` (read it first — reuse its element-emission helpers, Inkscape layer attributes, background/zone/screw/bar/title emission). Changes from v1: input is the new `Layout` (flat lists, no groups/tints — Loooop's tints are just `zones` now); texts render via `renderer.text_to_path_d(text, x, y, size, anchor="middle", tracking_mm=...)` with per-text color; `values`-layer texts go in the `values` layer; glyph assets baked via `images.py`; components layer emits `r="2"` circles (rects for rect widgets) with kind fill from `COLORS` and `id="{name}#{widget}"`.

- [ ] **Step 1: Write failing tests** — build a small layout via the Task 4 helper and assert: root has mm width/height and 1:1 viewBox; four layers present, `components` display:none; a knob circle carries `id="TIME_PARAM#RoundBlackKnob"` fill `#ff0000`; input jack fill `#00ff00`; text emitted as `<path` with expected fill and no `<text>` anywhere; `validate.validate_svg` passes on the output; ring text lands inside the `values` layer group; zone rect present with fill-opacity.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement by adapting v1 `svgdoc.py`.**
- [ ] **Step 4: Run tests** — PASS; full suite green.
- [ ] **Step 5: Commit** — `"Add SVG builder emitting v1-compatible layer contract"`

---

### Task 7: CLI

**Files:**
- Create: `panelgen.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `python panelgen.py SPEC.yaml --out OUT.svg [--theme PATH] [--check] [--preview] [--open] [--library DIR]`; module function `panelgen.generate(spec_path, out_path, theme_path=None) -> checks.Report` for tests. Exit codes: 0 success (warnings allowed, printed to stderr), 1 on errors (SpecError/ResolveError/check errors — all printed).

Pipeline: `load_spec → resolve_theme(user_or_flag_theme, spec.theme_mapping) → build_font_index → resolve fonts/renderers (v1 `panel_gen._render_svg` shows the recipe) → resolve → run_checks → (errors? abort) → build_svg → validate_svg → write`. `--check`: everything except write. Port v1's output-location guard (`panel_gen.py` `OutputLocationError`): refuse writing output inside this repo checkout, except paths under the system temp dir (so tests can write to `tmp_path`).

- [ ] **Step 1: Write failing tests** — happy path writes SVG to `tmp_path` and returns empty errors; check mode writes nothing; spec with off-panel element exits 1 via `subprocess` invocation; overlap-only spec exits 0 and prints `OVERLAP` on stderr; `--theme` with explicit background reflected in output; guard refuses `--out` inside the repo.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement `panelgen.py`** (argparse; mirror v1 CLI style).
- [ ] **Step 4: Run tests** — PASS; full suite green.
- [ ] **Step 5: Commit** — `"Add CLI: generate, check, theme flag, output guard"`

---

### Task 8: Preview port

**Files:**
- Create: `preview.py`
- Test: `tests/test_preview.py`

Port v1 `preview.py` and its test file. It reads the *generated SVG* (components layer), so it is layout-agnostic — expected changes: none beyond imports. Wire `--preview/--open` through `panelgen.py` (add to Task 7's argparse, calling `preview.build_preview`). Keep `$VCV_COMPONENT_LIBRARY` / `--library` / conventional-app-dir resolution.

- [ ] **Step 1: Copy `preview.py` + v1 `tests/test_preview.py`; adjust imports.**
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_preview.py -q` — PASS (v1 tests must not require an installed Rack; if any do, mark them `skipif` on library absence, matching v1's approach).
- [ ] **Step 3: Add `--preview`/`--open` passthrough in `panelgen.py` + a CLI test that `--preview` emits `<slug>.preview.svg` and `.preview.html` beside `--out` (use a fake library dir fixture with one dummy asset if needed).**
- [ ] **Step 4: Full suite green. Commit** — `"Port browser preview compositor"`

---

### Task 9: mm_sync port

**Files:**
- Create: `mm_sync.py`
- Test: `tests/test_mm_sync.py`

Verbatim port of v1 `mm_sync.py` + its tests (it consumes the SVG components layer, which is contract-identical). Adjust imports only.

- [ ] **Step 1: Copy files; run tests — PASS.**
- [ ] **Step 2: Commit** — `"Port MetaModule position sync tool"`

---

### Task 10: Reference extraction helper + parity harness

**Files:**
- Create: `tools/extract_reference.py`, `tests/parity.py`, `tests/fixtures/robotboy/reference/` (copies)
- Test: `tests/test_parity_utils.py`

**Interfaces:**
- Produces: `tests/parity.components_of(svg_path) -> dict[str, tuple]` mapping full id `NAME#Widget` → `("circle", cx, cy)` or `("rect", x, y, w, h)` parsed from the `components` layer (regex fine; v1 `preview._controls` shows the technique). `tests/parity.panel_paths_of(svg_path) -> list[str]` returning normalized `d` strings (strip whitespace runs, round every number to 3 decimals) of all `<path>` elements inside the `panel` layer. `tools/extract_reference.py SVG` prints both reports plus panel-layer rects/circles — the spec-writing aid for Tasks 11–14.
- Copy reference SVGs: from `/Users/gabrielroth/Dev/RobotBoy/res/`: `Loooop.svg`, `Lop.svg`, `MF20Filter.svg`, `Particules.svg` into `tests/fixtures/robotboy/reference/`. Also copy `lop-logo.svg` (find it: `ls /Users/gabrielroth/Dev/RobotBoy/panel-specs/`) and the Particules glyph assets from `/Users/gabrielroth/Dev/RobotBoy/.claude/worktrees/panel-refactor/panel-specs/glyphs/particules/*.svg` into `tests/fixtures/robotboy/assets/`.

- [ ] **Step 1: Write failing tests** — `components_of` on the copied `MF20Filter.svg` returns `CUTOFF_PARAM#RoundBigBlackKnob → ("circle", 11.80, 30.997)` (assert a handful of known ids/coords from the exploration report); `panel_paths_of` returns a non-empty normalized list.
- [ ] **Step 2: Run to verify failure; implement; PASS.**
- [ ] **Step 3: Commit** — `"Add parity harness and RobotBoy reference fixtures"`

---

### Task 11: MF-20 parity spec

**Files:**
- Create: `tests/fixtures/robotboy/mf20filter.yaml`
- Test: `tests/test_parity_mf20.py`

**Interfaces:**
- Consumes: everything above. The v1 spec `/Users/gabrielroth/Dev/RobotBoy/panel-specs/mf20filter.yaml` documents intent; the reference SVG is ground truth.

- [ ] **Step 1: Write the (initially failing) parity test**

```python
# tests/test_parity_mf20.py
REF = "tests/fixtures/robotboy/reference/MF20Filter.svg"

def test_component_centers_exact(tmp_path):
    out = tmp_path / "MF20Filter.svg"
    generate("tests/fixtures/robotboy/mf20filter.yaml", out, theme_path=ROBOTBOY_THEME)
    got, want = components_of(out), components_of(REF)
    assert got.keys() == want.keys()
    for k in want:
        assert got[k] == pytest.approx(want[k][1:], abs=1e-3), k

def test_panel_paths_match(tmp_path):
    ...  # sorted(panel_paths_of(out)) == sorted(panel_paths_of(REF))
```

`ROBOTBOY_THEME` = a committed fixture `tests/fixtures/robotboy/theme.yaml` **copied from** `~/.config/vcv-panel-gen/theme.yaml` (casing upper, background #3d3d3d, white text, screws dark, Futura, Shuttleblock Test Demi) so tests are deterministic; the Futura/Shuttleblock faces are installed on this machine — if a face is missing the test must fail loudly, not fall back.

- [ ] **Step 2: Write `mf20filter.yaml` in the NEW format.** Method: run `tools/extract_reference.py` on the reference; place every component at its exact center using a 3-column grid (`cols: [11.8, 25.4, 39.0]`) and named rows taken from the extracted y values (30.997, 46.997, 59.347, 74.857, 91.017, 113.69); I/O jacks at explicit x (9.35/19.05/31.75/41.45); zone `{x: 1.5, y: 15, w: 47.8, h: 92, fill: "#8a5a2c", opacity: 0.25}`; connectors `[[CUTOFF_PARAM, LP_CUTOFF_CV_PARAM], [HP_CUTOFF_PARAM, HP_CUTOFF_CV_PARAM]]`; labels as text elements at the y values recovered from reference panel paths (extract each label's baseline: uppercase text box top = baseline − cap_height; iterate until `panel_paths_match` passes); title `MF-20` size 9.5; theme inline: `screws: light` (this module ships silver screws — reference shows `#c0c0c0`).
- [ ] **Step 3: Iterate generate→compare until both tests PASS.** Overlap warnings that correspond to the reference design (none expected on MF-20) get `overlaps_ok` with a YAML comment.
- [ ] **Step 4: Full suite green. Commit** — `"MF-20 regenerates with exact parity from new spec"`

---

### Task 12: Löp parity spec

**Files:**
- Create: `tests/fixtures/robotboy/lop.yaml`
- Test: `tests/test_parity_lop.py` (same two assertions as Task 11 against `reference/Lop.svg`)

Same method as Task 11. Notables: `title: {logo: assets/lop-logo.svg, size: 9, valign: center}`; one zone (white, opacity 0.14); screen rect `{x: 1.5, y: 10.4, w: 57.96, h: 22.35}` kind widget named `SCREEN`; row 1 knob/CV stacks (knobs y 46.05, cv y 58.0, cols 9.87/23.61/37.35/51.09 — an even 4-col grid); Grid snap knob's value ring (`ring: ["Ø","4","8","16","32","64"], around: <grid knob name>` — take exact name and ring-values geometry from the reference; if ring `d` strings resist matching via the ported ring math, compare `values`-layer paths by bounding box ≤0.05 mm instead of exact `d` — note the choice in the test); audio row y 116.05 with labels below; connectors for the knob→CV stack bars and button→trig stacks (enumerate from reference bars: grey 0.3-wide rects in panel layer).

- [ ] Steps 1–4 as Task 11. Commit — `"Löp regenerates with exact parity from new spec"`

---

### Task 13: Loooop parity spec

**Files:**
- Create: `tests/fixtures/robotboy/loooop.yaml`
- Test: `tests/test_parity_loooop.py`

Same method. Notables: 38 HP; screen rect `{x: 1.5, y: 10.4, w: 190.04, h: 22.35}`; four head tints are plain `zones` (y 35.15, h 73.6, w 46.76, x 1.5/49.26/97.02/144.78; fills `#ff3b30`/`#fff70a` α 0.2/`#3f8cff`/`#ff5af0`, others α 0.14 — read exact rgba/opacity emission from the reference and match); per-head 3-col grids — define ONE grid per head (`head1..head4`, cols base+0/14.587/29.173 with bases 10.293/58.053/105.813/153.573 — verify against extraction) with shared row names (knobs1 46.35, cv1 58.7, knobs2 75.05, cv2 87.4, jacks 102.1); global bottom row elements at explicit x (from extraction) y 116.05; Grid snap knob ring as in Löp; stack-bar connectors per head knob→CV; labels via row shorthand per head.
This is the big one (~60 components) — the row/place shorthand keeps it manageable.

- [ ] Steps 1–4 as Task 11. Commit — `"Loooop regenerates with exact parity from new spec"`

---

### Task 14: Particules parity spec

**Files:**
- Create: `tests/fixtures/robotboy/particules.yaml` (+ glyph assets already copied in Task 10)
- Test: `tests/test_parity_particules.py`

The reference `Particules.svg` is the **hand-built Inkscape original** — panel-path parity is NOT expected. Assertions: (1) component centers exact vs the reference components layer (ids/centers listed in the design research: transport 11.9/20.4/38.1/59.845 @ 15.875; main grid cols 12.6/29.6/46.6/63.6 with knob/cv/atten rows 42.088/53.746/62.746 and 82.096/92.696/101.696; GRAIN_LIGHT at (29.6, 62.746); io 15.25/24.95/51.25/60.95 @ 114.3) — the hand-built components layer uses true radii; `components_of` reads cx/cy so radii don't matter; **normalize ids**: if the reference id lacks `#Widget` suffixes or uses different widget classes, compare by NAME part and center only, and take widget classes from `/Users/gabrielroth/Dev/RobotBoy/src/particules/Particules.cpp` `createParamCentered<...>` calls. (2) Panel furnishings present: pink zone `{x: 1.5, y: 28, w: 73.2, h: 79.6, rx: 2, fill: "#cf99a5", opacity: 0.5}`; all 12 glyph placements (positions in the design research §6 — atten-random ×4, ticks ×3, resize-arrow, shape icons ×4); title PARTICULES size 6.35 tracking 0.74; `theme: {screws: none}`; no connector bars. (3) The GRAIN_LIGHT / attenuverter-slot situation needs no `overlaps_ok` (slot is empty) — but FREEZE_INPUT/FREEZE_PARAM at 8.5 mm-ish spacing may warn; if so suppress with the pair + comment. Labels: match the worktree regen spec's text positions (`/Users/gabrielroth/Dev/RobotBoy/.claude/worktrees/panel-refactor/panel-specs/particules.yaml` is a v1-format map of every label/nudge — mine it for y values) — assert via bounding-box comparison against the WORKTREE regen SVG if present (`.claude/worktrees/panel-refactor/res/Particules.svg`), else skip path assertions and require preview review.

- [ ] Steps 1–4 as Task 11 (adjusted assertions). Commit — `"Particules regenerates from new spec with exact component parity"`

---

### Task 15: The skill

**Files:**
- Create: `skills/vcv-panel/SKILL.md`, symlink/install copy at `~/.claude/skills/vcv-panel/SKILL.md`

Content per design doc §9 (workflow, vertical-rhythm recipe, going-together math, jack-justification arithmetic, size table, overlap policy, the razor). Use superpowers:writing-skills for structure/frontmatter conventions. Frontmatter description: "Generate a VCV Rack panel SVG from a grid-based spec (vcv-panel-gen-redux). Supersedes vcv-panel-generate for new panels. Use when creating or editing a module panel." The going-together numbers to encode (from v1 constants, now guidance): label baseline 1.0 mm above control's drawn top edge; control↔jack stack 2.0 mm edge-to-edge; stereo pair 1.0 mm edge gap (9.7 mm centers for PJ301M); group gutters ≥4 mm; title band 10 mm; bottom label band ~3 mm margin. Include a worked Particules-style example (grid derivation from an element list) and the four RobotBoy fixture specs as canonical examples (link paths). Command crib: generate/check/preview invocations with the repo venv.

- [ ] **Step 1: Write SKILL.md; validate with writing-skills checklist.**
- [ ] **Step 2: Install to `~/.claude/skills/vcv-panel/` (copy, not symlink — plugins dir conventions).**
- [ ] **Step 3: Commit** — `"Add vcv-panel skill: layout judgment, spacing math, workflow"`

---

### Task 16: README + wrap-up

**Files:**
- Create: `README.md`
- Modify: none

- [ ] **Step 1: Write README**: what it is (v2 of vcv-panel-gen; scripts are mechanical, judgment in the skill), install, CLI usage, spec format reference (condensed from design doc §4 with a full small example), theme file docs, the SVG/VCV contract, preview, mm_sync, pointer to RobotBoy fixture specs as examples, relationship to v1 (v1 untouched; other modules still on it).
- [ ] **Step 2: Full test suite green** (`.venv/bin/python -m pytest -q`), run `panelgen.py` on one fixture with `--preview` and confirm files appear (manual smoke).
- [ ] **Step 3: Commit** — `"Add README"` — then merge `build-v1` into `main` (fast-forward or merge commit) and leave both branches.
