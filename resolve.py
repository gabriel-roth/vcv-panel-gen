"""Resolver: turns a parsed PanelSpec into absolutely-positioned elements.

Pure arithmetic — no layout judgment. Grid columns/rows and element dx/dy are
resolved to mm; four small pieces of geometry are ported from v1 layout.py
because they are mechanical, not opinionated: value-ring label placement
(minus the dodge logic), explicit connector bars, mounting-screw marker
positions, and title placement.

See docs/superpowers/specs/2026-07-17-grid-panel-generator-design.md
section 5 for the semantics this module implements.
"""
import math
from dataclasses import dataclass

from constants import (HP_MM, PANEL_H_MM, SIDE_MARGIN_MM, TITLE_BAND_MM,
                       TITLE_FONT_MM, LABEL_FONT_MM, MOUNT_INSET_X,
                       MOUNT_Y_TOP, MOUNT_Y_BOTTOM, KNOB_SWEEP_RAD,
                       VALUE_FONT_MM, CONNECT_LINE_WIDTH, CONNECT_LINE_COLOR)
from spec import ComponentEl, TextEl, RingEl
from theme import (apply_casing, resolve_text_color, resolve_title_color,
                   resolve_value_color)


class ResolveError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Placed element dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PlacedComponent:
    name: str
    kind: str
    widget: str | None
    x: float
    y: float
    rect: object | None = None  # spec.Rect, for kind: widget positioned by rect:


@dataclass
class PlacedText:
    text: str
    x: float          # anchor-middle center
    y: float           # baseline
    size: float
    color: str
    tracking: float
    layer: str          # "panel" | "values"


@dataclass
class PlacedBar:
    x: float
    y1: float
    y2: float
    width: float
    color: str


@dataclass
class PlacedScrew:
    x: float
    y: float


@dataclass
class PlacedLogo:
    src: str
    x: float           # center
    y: float            # top edge of the logo's box
    height_mm: float


@dataclass
class Layout:
    width: float
    height: float
    components: list
    texts: list
    bars: list
    screws: list
    zones: list
    glyphs: list
    title: object       # PlacedText | PlacedLogo


# ---------------------------------------------------------------------------
# Grid column math
# ---------------------------------------------------------------------------

def _resolve_cols(cols_spec, width, side_margin):
    """List of x centers for a ColsSpec: explicit list verbatim, else evenly
    spaced from x_from to x_to (defaulting to side_margin / width -
    side_margin when omitted); count == 1 uses the midpoint."""
    if cols_spec.explicit is not None:
        return list(cols_spec.explicit)
    x_from = cols_spec.x_from if cols_spec.x_from is not None else side_margin
    x_to = cols_spec.x_to if cols_spec.x_to is not None else (width - side_margin)
    if cols_spec.count == 1:
        return [(x_from + x_to) / 2.0]
    step = (x_to - x_from) / (cols_spec.count - 1)
    return [x_from + i * step for i in range(cols_spec.count)]


def _resolve_position(pos, grids, grid_cols):
    """(x, y) mm for a spec.Position, dx/dy already folded in."""
    if pos.col is not None:
        x = grid_cols[pos.grid][pos.col - 1]
    else:
        x = pos.x
    if pos.row is not None:
        y = grids[pos.grid].rows[pos.row]
    else:
        y = pos.y
    return x + pos.dx, y + pos.dy


# ---------------------------------------------------------------------------
# Text / label helpers
# ---------------------------------------------------------------------------

def _resolve_label(label, cx, cy, theme):
    casing = label.casing if label.casing is not None else theme.casing
    text = apply_casing(label.text, casing)
    size = label.size if label.size is not None else LABEL_FONT_MM
    color = label.color if label.color is not None else resolve_text_color(theme)
    return PlacedText(text=text, x=cx + label.dx, y=cy + label.dy, size=size,
                      color=color, tracking=0.0, layer="panel")


def _resolve_text_el(el, x, y, theme):
    casing = el.casing if el.casing is not None else theme.casing
    text = apply_casing(el.text, casing)
    size = el.size if el.size is not None else LABEL_FONT_MM
    color = el.color if el.color is not None else resolve_text_color(theme)
    tracking = el.tracking if el.tracking is not None else 0.0
    return PlacedText(text=text, x=x, y=y, size=size, color=color,
                      tracking=tracking, layer="panel")


# ---------------------------------------------------------------------------
# Value rings — ported from v1 layout.py:222 (_value_ring_labels), minus the
# `avoid`/dodge logic (v2 relies on overlap warnings instead of auto-dodge).
# ---------------------------------------------------------------------------

def _ring_labels(renderer, values, cx, cy, true_radius, gap, color, casing):
    n = len(values)
    ring = true_radius + gap
    half_h = renderer.cap_height(VALUE_FONT_MM) / 2.0
    labels = []
    for i, raw in enumerate(values):
        text = apply_casing(raw, casing)
        # n == 1 has no v1 precedent (division by n - 1); straight up is the
        # only reasonable single-label angle.
        theta = 0.0 if n == 1 else (
            -KNOB_SWEEP_RAD + i * (2.0 * KNOB_SWEEP_RAD) / (n - 1))
        half_w = renderer.text_width(text, VALUE_FONT_MM) / 2.0
        r_eff = ring + abs(math.sin(theta)) * half_w + abs(math.cos(theta)) * half_h
        ax = cx + r_eff * math.sin(theta)
        ay = cy - r_eff * math.cos(theta)
        labels.append(PlacedText(text=text, x=ax, y=ay + half_h, size=VALUE_FONT_MM,
                                 color=color, tracking=0.0, layer="values"))
    return labels


# ---------------------------------------------------------------------------
# Connectors — center-to-center, matching v1 layout.py _add_explicit_connectors;
# v1's value-ring clamp deliberately dropped. Same-x tolerance tightened to
# 0.01mm per the task 4 brief.
# ---------------------------------------------------------------------------

def _resolve_connectors(connectors, comp_by_name):
    bars = []
    for a_name, b_name in connectors or []:
        a, b = comp_by_name[a_name], comp_by_name[b_name]
        if abs(a.x - b.x) >= 0.01:
            raise ResolveError(
                f"connector {a_name}->{b_name}: endpoints must share an x "
                f"position (a vertical bar), got {a.x:.3f} vs {b.x:.3f}")
        top, bot = (a, b) if a.y <= b.y else (b, a)
        y0, y1 = top.y, bot.y
        if y1 > y0:
            bars.append(PlacedBar(x=a.x, y1=y0, y2=y1, width=CONNECT_LINE_WIDTH,
                                  color=CONNECT_LINE_COLOR))
    return bars


# ---------------------------------------------------------------------------
# Screws — ported from v1 layout.py:372-376 (mounting-hole marker positions).
# No narrow-panel special case exists in v1 to port; the four corners are
# always the same offsets regardless of panel width.
# ---------------------------------------------------------------------------

def _resolve_screws(theme, width):
    if theme.screws == "none":
        return []
    return [
        PlacedScrew(MOUNT_INSET_X, MOUNT_Y_TOP),
        PlacedScrew(width - MOUNT_INSET_X, MOUNT_Y_TOP),
        PlacedScrew(MOUNT_INSET_X, MOUNT_Y_BOTTOM),
        PlacedScrew(width - MOUNT_INSET_X, MOUNT_Y_BOTTOM),
    ]


# ---------------------------------------------------------------------------
# Title — ported from v1 layout.py:377-392, minus the "+ first grouped row's
# gap_above" term (v2 has no row/band model to consult), plus spec x/y/dx/dy
# overrides.
# ---------------------------------------------------------------------------

def _resolve_title(spec, theme, width, title_renderer):
    title = spec.title
    size = title.size if title.size is not None else TITLE_FONT_MM
    valign = title.valign if title.valign is not None else "baseline"
    cap = title_renderer.cap_height(size)
    if valign == "baseline":
        baseline = size + 1.0
    else:
        baseline = (TITLE_BAND_MM + cap) / 2.0
    cx = width / 2.0

    if title.x is not None:
        cx = title.x
    if title.y is not None:
        baseline = title.y
    cx += title.dx if title.dx is not None else 0.0
    baseline += title.dy if title.dy is not None else 0.0

    if title.logo is not None:
        top = baseline - cap
        return PlacedLogo(src=title.logo, x=cx, y=top, height_mm=cap)

    text = title.text if title.text is not None else spec.name
    tracking = title.tracking if title.tracking is not None else 0.0
    cased = apply_casing(text, theme.casing)
    color = resolve_title_color(theme)
    return PlacedText(text=cased, x=cx, y=baseline, size=size, color=color,
                      tracking=tracking, layer="panel")


# ---------------------------------------------------------------------------
# Top-level resolve
# ---------------------------------------------------------------------------

def resolve(spec, theme, db, renderer, title_renderer=None):
    title_renderer = title_renderer or renderer
    width = spec.hp * HP_MM
    height = PANEL_H_MM
    side_margin = spec.side_margin if spec.side_margin is not None else SIDE_MARGIN_MM

    grid_cols = {name: _resolve_cols(g.cols, width, side_margin)
                for name, g in spec.grids.items()}

    components = []
    comp_by_name = {}
    texts = []
    rings = []

    for el in spec.elements:
        if isinstance(el, ComponentEl):
            if el.rect is not None:
                cx = el.rect.x + el.rect.w / 2.0
                cy = el.rect.y + el.rect.h / 2.0
                comp = PlacedComponent(name=el.name, kind=el.kind, widget=el.widget,
                                       x=cx, y=cy, rect=el.rect)
            else:
                x, y = _resolve_position(el.pos, spec.grids, grid_cols)
                comp = PlacedComponent(name=el.name, kind=el.kind, widget=el.widget,
                                       x=x, y=y, rect=None)
            components.append(comp)
            comp_by_name[el.name] = comp
            if el.label is not None:
                texts.append(_resolve_label(el.label, comp.x, comp.y, theme))
        elif isinstance(el, TextEl):
            x, y = _resolve_position(el.pos, spec.grids, grid_cols)
            texts.append(_resolve_text_el(el, x, y, theme))
        elif isinstance(el, RingEl):
            rings.append(el)

    for ring in rings:
        comp = comp_by_name[ring.around]
        size = db.size_for(comp.widget) if comp.widget else None
        if size is None or size.shape != "circle" or size.d is None:
            raise ResolveError(
                f"ring around {ring.around!r}: widget {comp.widget!r} has no "
                f"known circular size (rings need a true knob radius)")
        texts.extend(_ring_labels(renderer, ring.labels, comp.x, comp.y,
                                  size.d / 2.0, ring.gap, resolve_value_color(theme),
                                  theme.casing))

    bars = _resolve_connectors(spec.connectors, comp_by_name)
    screws = _resolve_screws(theme, width)
    title = _resolve_title(spec, theme, width, title_renderer)

    return Layout(width=width, height=height, components=components, texts=texts,
                 bars=bars, screws=screws, zones=list(spec.zones or []),
                 glyphs=list(spec.glyphs or []), title=title)
