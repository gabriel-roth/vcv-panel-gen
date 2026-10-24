"""Assemble the final panel SVG from a resolved Layout.

Adapted from v1's svgdoc.py: same Inkscape layer attributes, same
background/zone/screw/bar/title/components emission style. What changed for
v2: the input is the new flat `resolve.Layout` (no row/group/tint model —
zones now carry their own fill/opacity, texts carry their own layer and
color); every text is emitted via `renderer.text_to_path_d(..., anchor=
"middle", tracking_mm=...)` with its own per-text color rather than a
handful of theme-wide colors; `values`-layer texts land in their own visible
Inkscape layer (excluded from the MetaModule faceplate export); glyph assets
are baked via images.py; the components layer emits `id="{name}#{widget}"`
(or `"{name}#Widget"` when no widget class is known, matching v1's screen
convention) with real bounds for rect components.

See AGENTS.md §6 ("The SVG contract") for the contract this module
implements.
"""
from xml.sax.saxutils import quoteattr

from constants import COLORS
from images import load_image, place_image
from logo import load_logo, place_logo
from resolve import PlacedLogo
from theme import resolve_screw_color, resolve_title_color

NS = ('xmlns="http://www.w3.org/2000/svg" '
      'xmlns:xlink="http://www.w3.org/1999/xlink" '
      'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
      'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd"')


def _path(d, fill="#000000"):
    return f'    <path fill="{fill}" d="{d}"/>'


def _zone_path_d(z):
    """Outline of a rounded-rect zone with its arrows (pointing out) and
    notches (cut in) folded into the edges, traced clockwise from the top-left
    corner. One path, so the triangles share the zone's fill without a seam or
    a doubled-opacity overlap."""
    x1, y1, x2, y2, r = z.x, z.y, z.x + z.w, z.y + z.h, z.rx
    # Per side: tracing direction along the edge, and the outward normal.
    pointers = {side: [] for side in ("top", "right", "bottom", "left")}
    for p in z.arrows:
        pointers[p.side].append((p, 1))
    for p in z.notches:
        pointers[p.side].append((p, -1))

    def f(v):
        return f"{v:.3f}".rstrip("0").rstrip(".")

    def edge(side, fixed, sign, out_sign, horizontal):
        # sign: +1 when tracing toward larger coordinates along the edge.
        cmds = []
        for p, kind in sorted(pointers[side], key=lambda t: sign * t[0].at):
            a, b = p.at - sign * p.w / 2, p.at + sign * p.w / 2
            tip = fixed + out_sign * kind * p.depth
            if horizontal:
                cmds += [f"H{f(a)}", f"L{f(p.at)},{f(tip)}", f"L{f(b)},{f(fixed)}"]
            else:
                cmds += [f"V{f(a)}", f"L{f(tip)},{f(p.at)}", f"L{f(fixed)},{f(b)}"]
        return cmds

    def arc(x, y):
        return [f"A{f(r)},{f(r)} 0 0 1 {f(x)},{f(y)}"] if r else []

    d = [f"M{f(x1 + r)},{f(y1)}"]
    d += edge("top", y1, 1, -1, True) + [f"H{f(x2 - r)}"] + arc(x2, y1 + r)
    d += edge("right", x2, 1, 1, False) + [f"V{f(y2 - r)}"] + arc(x2 - r, y2)
    d += edge("bottom", y2, -1, 1, True) + [f"H{f(x1 + r)}"] + arc(x1, y2 - r)
    d += edge("left", x1, -1, -1, False) + [f"V{f(y1 + r)}"] + arc(x1 + r, y1)
    return " ".join(d + ["Z"])


def _component_id(comp):
    return f"{comp.name}#{comp.widget if comp.widget is not None else 'Widget'}"


def _emit_texts(out, texts, renderer):
    for t in texts:
        d = renderer.text_to_path_d(t.text, t.x, t.y, t.size, anchor="middle",
                                     tracking_mm=t.tracking)
        if d:
            out.append(_path(d, fill=t.color))


def build_svg(layout, theme, renderer, title_renderer):
    screw_color = resolve_screw_color(theme)
    w, h = layout.width, layout.height

    panel_texts = [t for t in layout.texts if t.layer == "panel"]
    value_texts = [t for t in layout.texts if t.layer == "values"]

    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append(f'<svg {NS} version="1.1" width="{w}mm" height="{h}mm" '
               f'viewBox="0 0 {w} {h}">')

    # panel layer
    out.append('  <g inkscape:label="panel" inkscape:groupmode="layer" id="panel">')
    out.append(f'    <rect x="0" y="0" width="{w}" height="{h}" fill="{theme.background}"/>')
    for z in layout.zones:
        # An #rrggbbaa fill carries its own opacity, split off here and used
        # in place of z.opacity — matching v1 layout.py:604-611 tint
        # semantics (hues need different alphas to read equally).
        fill, opacity = z.fill, z.opacity
        if len(fill) == 9:
            opacity = round(int(fill[7:9], 16) / 255.0, 4)
            fill = fill[:7]
        if z.arrows or z.notches:
            out.append(f'    <path class="zone" d="{_zone_path_d(z)}" '
                       f'fill="{fill}" fill-opacity="{opacity}"/>')
        else:
            out.append(f'    <rect class="zone" x="{z.x:.2f}" y="{z.y:.2f}" '
                       f'width="{z.w:.2f}" height="{z.h:.2f}" rx="{z.rx:.2f}" '
                       f'fill="{fill}" fill-opacity="{opacity}"/>')
    for s in layout.screws:
        out.append(f'    <circle cx="{s.x}" cy="{s.y}" r="1.6" fill="{screw_color}"/>')
    for b in layout.bars:
        out.append(f'    <rect x="{b.x - b.width / 2.0}" y="{b.y1}" '
                   f'width="{b.width}" height="{b.y2 - b.y1}" fill="{b.color}"/>')
    if isinstance(layout.title, PlacedLogo):
        title_color = resolve_title_color(theme)
        logo = load_logo(layout.title.src)
        out.append(place_logo(logo, cx=layout.title.x, top=layout.title.y,
                              target_h=layout.title.height_mm, fill=title_color))
    elif layout.title is not None and layout.title.text.strip():
        d = title_renderer.text_to_path_d(layout.title.text, layout.title.x, layout.title.y,
                                          layout.title.size, anchor="middle",
                                          tracking_mm=layout.title.tracking,
                                          kern_mm=layout.title.kern)
        if d:
            out.append(_path(d, fill=layout.title.color))
    _emit_texts(out, panel_texts, renderer)
    out.append('  </g>')

    # values layer: ring/position labels, kept out of the panel layer so the
    # MetaModule faceplate export (SvgToPng --layer panel) omits them.
    if value_texts:
        out.append('  <g inkscape:label="values" inkscape:groupmode="layer" '
                   'id="values">')
        _emit_texts(out, value_texts, renderer)
        out.append('  </g>')

    # glyphs layer: baked decorative assets, above the panel art.
    if layout.glyphs:
        out.append('  <g inkscape:label="glyphs" inkscape:groupmode="layer" '
                   'id="glyphs">')
        for g in layout.glyphs:
            img = load_image(g.src)
            out.append(place_image(img, g.x, g.y, g.scale, g.scale))
        out.append('  </g>')

    # components layer (hidden): one marker per placed component, matched
    # back to real VCV widgets by preview.py / mm_sync.py via its id.
    out.append('  <g inkscape:label="components" inkscape:groupmode="layer" '
               'id="components" style="display:none">')
    for comp in layout.components:
        cid = _component_id(comp)
        fill = COLORS[comp.kind]
        if comp.rect is not None:
            out.append(f'    <rect id={quoteattr(cid)} x="{comp.rect.x}" y="{comp.rect.y}" '
                       f'width="{comp.rect.w}" height="{comp.rect.h}" fill="{fill}"/>')
        else:
            out.append(f'    <circle id={quoteattr(cid)} cx="{comp.x}" cy="{comp.y}" '
                       f'r="2" fill="{fill}"/>')
    out.append('  </g>')

    out.append('</svg>')
    return "\n".join(out) + "\n"
