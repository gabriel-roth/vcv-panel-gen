"""Embed a vector wordmark in place of the drawn module title.

Used when the title font can't render the name (a missing glyph, a licensed
face that isn't installed). The logo is authored once — e.g. traced from a
reference PNG with `potrace --tight -a 0` — and committed alongside the spec;
`title_logo:` in the spec points at it.

The generator scales/centers/recolors the logo and **bakes** the result into
plain absolute path coordinates — no `transform=` attribute survives, because
NanoSVG (VCV's renderer) can't render transforms. The path shapes are copied
faithfully; only their coordinates move. The logo is drawn in the panel's text
color; per-element fill/stroke in the asset are ignored.

Supported path commands: M/L/H/V/C/Q/Z (absolute or relative). Smooth (S/T)
and arc (A) commands are rejected — retrace or convert them to lines/beziers
(potrace emits only lines and cubics, so its output already qualifies).
"""
import re
from dataclasses import dataclass, field

_VIEWBOX_RE = re.compile(r'viewBox\s*=\s*"([^"]+)"')
_SVG_OPEN_RE = re.compile(r'<svg\b[^>]*>', re.IGNORECASE)
_METADATA_RE = re.compile(r'<metadata\b.*?</metadata>', re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
_G_TRANSFORM_RE = re.compile(r'<g\b[^>]*?\btransform\s*=\s*"([^"]*)"', re.IGNORECASE)
_PATH_D_RE = re.compile(r'<path\b[^>]*?\bd\s*=\s*"([^"]*)"', re.IGNORECASE | re.DOTALL)
_OTHER_SHAPE_RE = re.compile(r'<(rect|circle|ellipse|line|polyline|polygon)\b', re.IGNORECASE)
_TRANSFORM_FUNC_RE = re.compile(r'(\w+)\s*\(([^)]*)\)')
_NUM_RE = r'[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?'
_TOKEN_RE = re.compile(r'[MmLlHhVvCcQqSsTtAaZz]|' + _NUM_RE)


class LogoError(Exception):
    pass


# --- affine transforms as (a, b, c, d, e, f): x' = a·x + c·y + e, y' = b·x + d·y + f

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _compose(p, q):
    """Return p∘q — the affine that applies q first, then p."""
    a1, b1, c1, d1, e1, f1 = p
    a2, b2, c2, d2, e2, f2 = q
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def _parse_transform(text):
    """Parse an SVG transform attribute (translate/scale/matrix/rotate) into an
    affine. Functions compose left-to-right, matching SVG semantics."""
    t = IDENTITY
    for name, raw in _TRANSFORM_FUNC_RE.findall(text or ""):
        nums = [float(n) for n in re.findall(_NUM_RE, raw)]
        name = name.lower()
        if name == "translate":
            tx = nums[0] if nums else 0.0
            ty = nums[1] if len(nums) > 1 else 0.0
            m = (1.0, 0.0, 0.0, 1.0, tx, ty)
        elif name == "scale":
            sx = nums[0] if nums else 1.0
            sy = nums[1] if len(nums) > 1 else sx
            m = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        elif name == "matrix" and len(nums) == 6:
            m = tuple(nums)
        elif name == "rotate":
            import math
            ang = math.radians(nums[0]) if nums else 0.0
            cos, sin = math.cos(ang), math.sin(ang)
            r = (cos, sin, -sin, cos, 0.0, 0.0)
            if len(nums) >= 3:
                cx, cy = nums[1], nums[2]
                m = _compose((1.0, 0.0, 0.0, 1.0, cx, cy),
                             _compose(r, (1.0, 0.0, 0.0, 1.0, -cx, -cy)))
            else:
                m = r
        else:
            raise LogoError(f"unsupported transform function {name!r}")
        t = _compose(t, m)
    return t


@dataclass
class Logo:
    minx: float
    miny: float
    width: float
    height: float
    transform: tuple            # affine mapping raw path coords -> viewBox coords
    paths: list = field(default_factory=list)   # raw path 'd' strings


def load_logo(path):
    """Parse a logo SVG into its viewBox box, its group transform, and the raw
    path 'd' strings. Requires a viewBox and at least one <path>."""
    with open(path) as f:
        text = f.read()

    m = _VIEWBOX_RE.search(text)
    if not m:
        raise LogoError(f"logo {path!r} has no viewBox; cannot place it")
    parts = m.group(1).replace(",", " ").split()
    if len(parts) != 4:
        raise LogoError(f"logo {path!r} viewBox must have 4 numbers, got {m.group(1)!r}")
    try:
        minx, miny, width, height = (float(p) for p in parts)
    except ValueError:
        raise LogoError(f"logo {path!r} viewBox is not numeric: {m.group(1)!r}")
    if width <= 0 or height <= 0:
        raise LogoError(f"logo {path!r} viewBox has non-positive size: {m.group(1)!r}")

    open_m = _SVG_OPEN_RE.search(text)
    close = text.rfind("</svg>")
    if not open_m or close < 0:
        raise LogoError(f"logo {path!r} is not a well-formed <svg> document")
    inner = text[open_m.end():close]
    inner = _METADATA_RE.sub("", inner)
    inner = _COMMENT_RE.sub("", inner)

    other = _OTHER_SHAPE_RE.search(inner)
    if other:
        raise LogoError(
            f"logo {path!r} contains a <{other.group(1)}>; only <path> elements "
            f"are supported — convert shapes to paths (Inkscape: Path > Object to Path)")

    transforms = _G_TRANSFORM_RE.findall(inner)
    transform = IDENTITY
    for tr in transforms:
        transform = _compose(transform, _parse_transform(tr))

    paths = _PATH_D_RE.findall(inner)
    if not paths:
        raise LogoError(f"logo {path!r} has no <path> drawable content")

    return Logo(minx=minx, miny=miny, width=width, height=height,
                transform=transform, paths=paths)


def _num(x):
    """Trim trailing zeros so baked coordinates read cleanly."""
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def _bake_path(d, aff):
    """Rewrite path data `d` into absolute coordinates with the affine `aff`
    baked in. Current point is tracked in the original (pre-affine) space;
    emitted coordinates are transformed."""
    a, b, c, dd, e, f = aff

    def pt(x, y):
        return f"{_num(a * x + c * y + e)} {_num(b * x + dd * y + f)}"

    tokens = _TOKEN_RE.findall(d)
    out = []
    i, n = 0, len(tokens)
    cx = cy = sx = sy = 0.0   # current point, subpath start — original space

    def num():
        nonlocal i
        v = float(tokens[i]); i += 1
        return v

    while i < n:
        cmd = tokens[i]; i += 1
        rel = cmd.islower()
        u = cmd.upper()
        if u == "Z":
            out.append("Z"); cx, cy = sx, sy
        elif u == "M":
            x, y = num(), num()
            if rel: x, y = cx + x, cy + y
            cx, cy = x, y; sx, sy = x, y
            out.append("M " + pt(x, y))
            while i < n and not tokens[i].isalpha():   # implicit linetos
                x, y = num(), num()
                if rel: x, y = cx + x, cy + y
                cx, cy = x, y
                out.append("L " + pt(x, y))
        elif u == "L":
            while i < n and not tokens[i].isalpha():
                x, y = num(), num()
                if rel: x, y = cx + x, cy + y
                cx, cy = x, y
                out.append("L " + pt(x, y))
        elif u == "H":
            while i < n and not tokens[i].isalpha():
                x = num()
                x = cx + x if rel else x
                cx = x
                out.append("L " + pt(cx, cy))
        elif u == "V":
            while i < n and not tokens[i].isalpha():
                y = num()
                y = cy + y if rel else y
                cy = y
                out.append("L " + pt(cx, cy))
        elif u == "C":
            while i < n and not tokens[i].isalpha():
                x1, y1, x2, y2, x, y = (num() for _ in range(6))
                if rel:
                    x1, y1, x2, y2, x, y = (cx + x1, cy + y1, cx + x2, cy + y2, cx + x, cy + y)
                cx, cy = x, y
                out.append("C " + pt(x1, y1) + " " + pt(x2, y2) + " " + pt(x, y))
        elif u == "Q":
            while i < n and not tokens[i].isalpha():
                x1, y1, x, y = (num() for _ in range(4))
                if rel:
                    x1, y1, x, y = (cx + x1, cy + y1, cx + x, cy + y)
                cx, cy = x, y
                out.append("Q " + pt(x1, y1) + " " + pt(x, y))
        else:
            raise LogoError(
                f"unsupported path command {cmd!r} in logo — only M/L/H/V/C/Q/Z "
                f"are baked (smooth S/T and arc A must be converted to beziers)")
    return " ".join(out)


def place_logo(logo, cx, top, target_h, fill, indent="    "):
    """Return one or more <path> elements placing `logo` so its box is
    `target_h` mm tall, centered horizontally on `cx`, top edge at `top` (mm),
    filled with `fill`. Coordinates are fully baked (no transform attribute)."""
    s = target_h / logo.height
    # viewBox coords -> panel mm: scale by s, center width on cx, top at `top`.
    placement = (s, 0.0, 0.0, s,
                 cx - logo.width * s / 2.0 - logo.minx * s,
                 top - logo.miny * s)
    aff = _compose(placement, logo.transform)
    lines = []
    for d in logo.paths:
        baked = _bake_path(d, aff)
        if baked:
            lines.append(f'{indent}<path fill="{fill}" d="{baked}"/>')
    return "\n".join(lines)
