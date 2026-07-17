"""Place external SVG glyph assets at arbitrary panel positions.

A spec's `glyphs:` list names small vector assets — the marks that ring a knob:
waveform icons, arrows, tick scales, staircases — and says where to drop each
one. Every drawable element in the asset (`path`, `line`, `polyline`, `polygon`)
is copied onto the panel with its coordinates **baked** into absolute mm — no
`transform=` attribute survives, because NanoSVG (VCV's renderer) can't render
transforms. Each element keeps its own `fill`/`stroke`/`stroke-width` (unlike a
title logo, which is recolored and sized to the cap height), so the mark looks
exactly as authored.

Placement is by the asset's viewBox: `at: [x, y]` puts the viewBox *center* at
(x, y) mm; `scale` (a number, or `[sx, sy]`) maps viewBox units to mm and may be
negative to mirror. Stroke widths scale with the placement so a mark stays in
proportion.

Only `path` (M/L/H/V/C/Q/Z), `line`, `polyline` and `polygon` are baked;
`rect`/`circle`/`ellipse`/`text`/`image` are rejected — convert shapes to paths
(Inkscape: Path > Object to Path). Nested `<g transform=...>` and per-element
`transform=` are honored and folded into the baked coordinates.
"""
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from logo import IDENTITY, _compose, _parse_transform, _bake_path, _num, LogoError

SVG_NS = "http://www.w3.org/2000/svg"

# Presentation attributes carried through onto the baked element (child wins
# over ancestor). stroke-width is the only one rescaled by the placement.
_STYLE_ATTRS = ("fill", "stroke", "stroke-width", "stroke-linecap",
                "stroke-linejoin", "stroke-miterlimit", "fill-opacity",
                "stroke-opacity", "opacity", "fill-rule")

_BAKEABLE = ("path", "line", "polyline", "polygon")
_REJECT = ("rect", "circle", "ellipse", "text", "image")
_SKIP = ("defs", "metadata", "title", "desc", "namedview", "sodipodi:namedview")


class ImageError(Exception):
    pass


@dataclass
class Element:
    tag: str                       # local name: path/line/polyline/polygon
    geom: dict                     # geometry attrs (d, or points, or x1..y2)
    style: dict                    # presentation attrs (fill, stroke, ...)
    transform: tuple               # affine from the asset's <g>/element transforms


@dataclass
class Image:
    minx: float
    miny: float
    width: float
    height: float
    elements: list = field(default_factory=list)


def _local(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _parse_style_attr(text):
    out = {}
    for chunk in (text or "").split(";"):
        if ":" in chunk:
            k, v = chunk.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _effective_style(elem, inherited):
    style = dict(inherited)
    css = _parse_style_attr(elem.get("style"))
    for k in _STYLE_ATTRS:
        if elem.get(k) is not None:
            style[k] = elem.get(k)
        if k in css:
            style[k] = css[k]
    return style


def _walk(elem, parent_tr, parent_style, out):
    tr = _compose(parent_tr, _parse_transform(elem.get("transform")))
    style = _effective_style(elem, parent_style)
    name = _local(elem.tag)
    if name in _BAKEABLE:
        geom = {k: v for k, v in elem.attrib.items()
                if k in ("d", "points", "x1", "y1", "x2", "y2")}
        out.append(Element(tag=name, geom=geom, style=style, transform=tr))
    elif name in _REJECT:
        raise ImageError(
            f"glyph asset contains a <{name}> — only path/line/polyline/polygon "
            f"are baked; convert shapes to paths (Inkscape: Path > Object to Path)")
    elif name in ("g", "svg") or name in _SKIP:
        if name in _SKIP:
            return
        for child in elem:
            _walk(child, tr, style, out)


def load_image(path):
    """Parse a glyph asset SVG into its viewBox and its list of drawable
    elements (with transforms and styles resolved). Requires a viewBox and at
    least one bakeable element."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        raise ImageError(f"glyph asset {path!r} is not well-formed XML: {e}")
    vb = root.get("viewBox")
    if not vb:
        raise ImageError(f"glyph asset {path!r} has no viewBox; cannot place it")
    parts = vb.replace(",", " ").split()
    if len(parts) != 4:
        raise ImageError(f"glyph asset {path!r} viewBox must have 4 numbers, got {vb!r}")
    try:
        minx, miny, width, height = (float(p) for p in parts)
    except ValueError:
        raise ImageError(f"glyph asset {path!r} viewBox is not numeric: {vb!r}")
    if width <= 0 or height <= 0:
        raise ImageError(f"glyph asset {path!r} viewBox has non-positive size: {vb!r}")

    elements = []
    for child in root:
        _walk(child, IDENTITY, {}, elements)
    if not elements:
        raise ImageError(f"glyph asset {path!r} has no drawable content "
                         f"(path/line/polyline/polygon)")
    return Image(minx=minx, miny=miny, width=width, height=height, elements=elements)


def _pt(aff, x, y):
    a, b, c, d, e, f = aff
    return a * x + c * y + e, b * x + d * y + f


def _bake_points(points, aff):
    coords = [float(n) for n in points.replace(",", " ").split()]
    out = []
    for i in range(0, len(coords) - 1, 2):
        x, y = _pt(aff, coords[i], coords[i + 1])
        out.append(f"{_num(x)},{_num(y)}")
    return " ".join(out)


def _style_str(style, sw_scale):
    parts = []
    for k in _STYLE_ATTRS:
        if k not in style:
            continue
        v = style[k]
        if k == "stroke-width":
            try:
                v = _num(float(v) * sw_scale)
            except ValueError:
                pass
        parts.append(f'{k}="{v}"')
    return " ".join(parts)


def place_image(img, cx, cy, sx=1.0, sy=1.0, indent="    "):
    """Return baked SVG element strings placing `img` with its viewBox center at
    (cx, cy) mm, scaled by (sx, sy). No transform attribute is emitted; each
    element keeps its own presentation style, with stroke-width rescaled by the
    placement magnitude."""
    center_x = img.minx + img.width / 2.0
    center_y = img.miny + img.height / 2.0
    placement = (sx, 0.0, 0.0, sy, cx - sx * center_x, cy - sy * center_y)
    lines = []
    for el in img.elements:
        aff = _compose(placement, el.transform)
        sw_scale = math.sqrt(abs(aff[0] * aff[3] - aff[1] * aff[2])) or 1.0
        style = _style_str(el.style, sw_scale)
        style = (" " + style) if style else ""
        if el.tag == "path":
            baked = _bake_path(el.geom.get("d", ""), aff)
            if baked:
                lines.append(f'{indent}<path{style} d="{baked}"/>')
        elif el.tag == "line":
            x1, y1 = _pt(aff, float(el.geom.get("x1", 0)), float(el.geom.get("y1", 0)))
            x2, y2 = _pt(aff, float(el.geom.get("x2", 0)), float(el.geom.get("y2", 0)))
            lines.append(f'{indent}<line x1="{_num(x1)}" y1="{_num(y1)}" '
                         f'x2="{_num(x2)}" y2="{_num(y2)}"{style}/>')
        elif el.tag in ("polyline", "polygon"):
            pts = _bake_points(el.geom.get("points", ""), aff)
            lines.append(f'{indent}<{el.tag} points="{pts}"{style}/>')
    return "\n".join(lines)
