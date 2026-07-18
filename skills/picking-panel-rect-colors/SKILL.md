---
name: picking-panel-rect-colors
description: Use when choosing or tuning the fill color and opacity of a rectangle, tint zone, or background region on a VCV Rack / MetaModule panel SVG, and you want to preview candidate colors composited over the panel's own background before committing a value.
---

# Picking panel rect/tint colors

## Overview

Colors on a panel are almost always **translucent fills over the dark panel background**, so a hex value in isolation lies — a "light pink" at 0.5 opacity over `#3d3d3d` is a muted rose, not pink. This skill previews a candidate `fill` + `fill-opacity` composited over the actual background, with white sample labels on top so you can judge label contrast, and hands you the exact SVG string to paste.

The tool is `color-tuner.html` (next to this file): a self-contained page with Hue/Saturation/Brightness/Opacity sliders, published as an Artifact.

## When to use

- Adding or recoloring a `<rect>` zone/tint/panel region in a panel SVG.
- The user asks to "pick a color", "try a different shade", "make it dustier/lighter/more opaque", or tune a background block.
- Any time opacity is in play — that's exactly when eyeballing a hex fails.

Not for: opaque text/glyph colors you already know, or non-visual choices.

## Workflow

1. **Find the background.** Read the target panel SVG's background rect fill (the `<rect id="background" ... fill:#RRGGBB>` in the panel layer). That is the color you composite over.
2. **Copy the template** `color-tuner.html` to your scratchpad (don't edit it in place in the repo).
3. **Set `CONFIG`** at the bottom of the `<script>`:
   - `bg` — the background hex from step 1.
   - `initialHex` / `initialOpacity` — the rect's **current** values when editing an existing rect, or a reasonable starting guess for a new one.
   - `zoneLabels` — the white caps labels that will sit **over** the zone (so contrast is realistic); `aboveLabels` / `title` are cosmetic context.
4. **Publish it** with the Artifact tool and give the user the link. Let them drive the sliders.
5. **Apply the result.** When they settle (they'll copy the "SVG fill string", e.g. `fill:#cf99a5;fill-opacity:0.5`, or just tell you the numbers), write it into the target rect's `style` in the panel SVG, then regenerate/rebuild as usual (SvgToPng for MetaModule, build-install for VCV).

## Notes

- The tool reports both the **pure hex** and the **effective hex** (what the translucent fill actually resolves to over the background) — the effective hex is what you'd use if you ever want the same look as a fully opaque fill.
- Reference for margins/opacity conventions: vcv-panel-gen's own group-tint rects sit ~1.5 mm from the panel edge at ~0.14 opacity (`layout.py` / generated panels) — a good starting point for a new zone.
- Keep the SVG clean: a `<rect>` with a `style="fill:...;fill-opacity:...;stroke:none"` and no `transform` passes the panel build's cleanup checks.
