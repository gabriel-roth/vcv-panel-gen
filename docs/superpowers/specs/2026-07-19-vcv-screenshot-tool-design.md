# VCV module screenshot tool — design

**Date:** 2026-07-19
**Status:** approved

## Goal

A CLI tool, part of this repo, that produces **accurately cropped** PNG
screenshots of a VCV Rack module. Two situations:

- **(a) default state** — a module rendered on its own, in its default state.
- **(b) live in a patch** — a module reflecting its live knob/screen state from
  a running patch. Crop is tight to the single module (no neighbours/cables
  required). The patch may be a `.vcv` file on disk *or* the currently running
  Rack instance.

Past attempts cropped a whole-window screenshot by pixel arithmetic and drifted
with scroll / zoom / Retina. This design removes the guesswork.

## Environment (verified)

- `/Applications/VCV Rack 2 Free.app/Contents/MacOS/Rack`, arch `arm64`,
  plugins in `~/Library/Application Support/Rack2/plugins-mac-arm64/`.
- Rack CLI (from vcvrack.com/manual/Installing): `-u/--user <dir>`,
  `-s/--system <dir>`, `-t/--screenshot <zoom>` ("screenshots of all installed
  modules → `<user>/screenshots/<plugin>/<module>.png`"), `-h/--headless`,
  positional `<patch>` loads a patch, `-v/--version`.
- Patch/autosave `patch.json` fields: `zoom` (linear multiplier; 1.0 = 100%),
  `gridOffset` (viewport top-left, in grid units), `modules[].pos` (grid units;
  1 HP = 15 px wide, 1 row = 380 px tall), `plugin`, `model`.
- Repo convention: standalone scripts run as `.venv/bin/python <tool>.py …`
  (panelgen.py, preview.py, mm_sync.py). Python 3.14, lean deps (fonttools,
  PyYAML).

## CLI

Standalone `screenshot.py`, three subcommands. Shared options:
`--plugin <slug> --module <slug>` (VCV plugin + model slug), `--out PATH.png`
(required), `--zoom Z` (default 1).

- `screenshot.py default --plugin P --module M [--zoom Z] --out OUT.png`
  Also: `--plugin-dir DIR` to screenshot a freshly built plugin folder instead
  of the installed one.
- `screenshot.py patch --file P.vcv --plugin P --module M [--zoom Z] --out OUT.png`
- `screenshot.py live --plugin P --module M [--zoom Z] --out OUT.png [--min-score S]`

## Approach

### `default` — native render (case a)

Rack renders each module to its own framebuffer and writes a natively-cropped
PNG. No crop math.

1. Make a throwaway temp user folder.
2. Put the target plugin into `<temp>/plugins-mac-arm64/<Plugin>` — symlink the
   installed plugin dir, or copy `--plugin-dir`.
3. Run `Rack -u <temp> --screenshot <zoom>` as a subprocess; wait for exit.
   (Built-in Core/Fundamental come from the system folder and are also shot;
   we ignore them.)
4. Copy `<temp>/screenshots/<plugin-slug>/<module-slug>.png` → `--out`.

This render is cached (keyed by plugin/module/zoom + plugin dir mtime) and reused
as the **match template** for `patch`/`live`.

### Crop core — template matching (cases b)

Never guess pixels. Capture the Rack window, locate the module by matching its
known default render inside the capture, crop the matched box.

- `render_template(plugin, module, zoom)` → the `default` PNG (native pixels:
  `HP*15*zoom` × `380*zoom`).
- `locate(template, window, scale_hint) -> (x, y, w, h, score)`: grayscale float
  arrays (Pillow). For each scale `s` in a small set around
  `scale_hint = viewZoom * backingScale` (plus `s∈{1,2}` fallbacks), resize the
  template and compute a normalized cross-correlation over the window via
  `numpy.fft` (O(N log N)); keep the best `(score, x, y, s)`. Return the box
  `(x, y, w=tpl_w*s, h=tpl_h*s)`. If best `score < min-score` (default ~0.5),
  raise — a low score is a loud error, never a silently-wrong crop.
- Crop the window PNG to that box → `--out` (device pixels).

### `patch` — deterministic viewport (case b, file)

We control the view, so the match is trivial and unambiguous.

1. Temp user folder; symlink the real `plugins-mac-arm64` in (so every plugin
   the patch uses loads); copy real `settings.json` minus window geometry.
2. Load `--file`, find the target module by `plugin`+`model`, rewrite the patch:
   `zoom = 1.0`, `gridOffset = module.pos` → module sits at the viewport
   top-left corner. Write it as the temp folder's autosave.
3. Launch `Rack -u <temp>` (GUI); poll for its window; short settle for GL
   render; activate frontmost; `screencapture` the window.
4. `locate` (scale_hint = 1.0 * backingScale) → crop → `--out`. Kill Rack.

### `live` — running Rack (case b, live)

1. Rack already running — never relaunch, never touch its autosave.
2. Ensure the template exists (render via `default` into cache).
3. Read the live view `zoom` from the current autosave as a scale hint (best
   effort; matching absorbs error).
4. Activate Rack frontmost; `screencapture` its window.
5. `locate` → crop → `--out`. Report the score.

### Window capture / geometry (macOS)

- Launch Rack as a subprocess of the binary directly (so we can wait on / kill
  it): `<Rack> -u <temp> [patch]`.
- Window readiness + geometry via `osascript` (System Events, process "Rack",
  `window 1` position/size in points).
- Capture with `screencapture -o -R <x,y,w,h>` after `osascript … activate`
  (Rack frontmost). Output is device pixels — matching handles the scale.
- `backingScale` auto-detected: capture width in px ÷ window width in points.

## Dependencies

Add `numpy` and `Pillow` to `.venv` and to a dev-only requirements section.
Not used by panel generation and not shipped in panel output.

## Safety / isolation

- Every Rack launch uses a throwaway temp user folder (under a temp dir),
  removed after. The real user folder is never written.
- `live` never writes any Rack state.

## Testing

Pure, Rack-free (the reliability-critical logic):

- **patch derivation** — from a fixture `patch.json` + a target plugin/model,
  assert the rewritten patch has `zoom==1.0` and `gridOffset==pos`, and errors
  when the module isn't in the patch.
- **`locate()`** — paste a template into a larger canvas at a known scale and
  offset (with mild noise); assert the recovered box is within a few px and
  score is high. Assert a below-threshold match raises.
- **crop math / backingScale detection** — pure arithmetic.

Rack-dependent (gated; skipped when Rack absent or `RUN_RACK_TESTS` unset):

- `default` against an installed plugin → a PNG of the expected dimensions.

## Out of scope

- Neighbours/cables in the crop (tight single-module only).
- Non-macOS window capture.
- Screenshotting the whole patch.
