"""Bounds errors and suppressible overlap warnings for a resolved Layout.

Pure geometry: extents are the *true drawn* size of every checkable element
(circle components use components.yaml's diameter; rect components/screens
use their rect; texts use fontTools metrics sitting on the baseline; screws
use the fixed screw-head radius; the title is a text or logo rect). Zones,
glyphs, and connector bars are decorative and carry no extent.

See docs/superpowers/specs/2026-07-17-grid-panel-generator-design.md section 5
for the semantics this module implements.
"""
import math
from dataclasses import dataclass

from constants import SCREW_RADIUS_MM
from logo import load_logo
from resolve import PlacedLogo


@dataclass
class Report:
    errors: list
    warnings: list


# ---------------------------------------------------------------------------
# Extents, represented as tagged tuples:
#   ("circle", cx, cy, r)
#   ("rect", x, y, w, h)     -- x, y is the top-left corner
# ---------------------------------------------------------------------------

def _text_extent(t, renderer):
    w = renderer.text_width(t.text, t.size, t.tracking)
    h = renderer.cap_height(t.size)
    return ("rect", t.x - w / 2.0, t.y - h, w, h)


def _component_extent(comp, db):
    """Extent tuple for a placed component, or None if its widget class has
    no known size (rect: components always have a known extent -- their own
    rect -- regardless of any widget name given alongside it)."""
    if comp.rect is not None:
        return ("rect", comp.rect.x, comp.rect.y, comp.rect.w, comp.rect.h)
    if comp.widget is None:
        return None
    size = db.size_for(comp.widget)
    if size is None:
        return None
    if size.shape == "circle":
        return ("circle", comp.x, comp.y, size.d / 2.0)
    return ("rect", comp.x - size.w / 2.0, comp.y - size.h / 2.0, size.w, size.h)


def _screw_extent(s):
    return ("circle", s.x, s.y, SCREW_RADIUS_MM)


def _title_extent(title, renderer):
    if isinstance(title, PlacedLogo):
        logo = load_logo(title.src)
        w = title.height_mm * (logo.width / logo.height)
        return ("rect", title.x - w / 2.0, title.y, w, title.height_mm)
    return _text_extent(title, renderer)


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

def _bounds_overhang(extent, width, height):
    if extent[0] == "circle":
        _, cx, cy, r = extent
        xmin, xmax, ymin, ymax = cx - r, cx + r, cy - r, cy + r
    else:
        _, x, y, w, h = extent
        xmin, xmax, ymin, ymax = x, x + w, y, y + h
    over = max(0.0, -xmin, xmax - width, -ymin, ymax - height)
    return over if over > 1e-9 else 0.0


# ---------------------------------------------------------------------------
# Pairwise overlap depth
# ---------------------------------------------------------------------------

def _rect_corners(extent):
    _, x, y, w, h = extent
    return x, y, x + w, y + h


def _depth(e1, e2):
    """Overlap depth in mm between two extents, or None if they do not
    intersect. circle/circle: r1+r2-dist; rect/rect: min axis overlap;
    circle/rect: radius minus the distance to the nearest (clamped) point."""
    if e1[0] == "circle" and e2[0] == "circle":
        _, x1, y1, r1 = e1
        _, x2, y2, r2 = e2
        dist = math.hypot(x1 - x2, y1 - y2)
        depth = r1 + r2 - dist
        return depth if depth > 0 else None

    if e1[0] == "rect" and e2[0] == "rect":
        ax1, ay1, ax2, ay2 = _rect_corners(e1)
        bx1, by1, bx2, by2 = _rect_corners(e2)
        ox = min(ax2, bx2) - max(ax1, bx1)
        oy = min(ay2, by2) - max(ay1, by1)
        if ox > 0 and oy > 0:
            return min(ox, oy)
        return None

    circle, rect = (e1, e2) if e1[0] == "circle" else (e2, e1)
    _, cx, cy, r = circle
    rx1, ry1, rx2, ry2 = _rect_corners(rect)
    clamped_x = min(max(cx, rx1), rx2)
    clamped_y = min(max(cy, ry1), ry2)
    dist = math.hypot(cx - clamped_x, cy - clamped_y)
    depth = r - dist
    return depth if depth > 0 else None


# ---------------------------------------------------------------------------
# Labels (also the identifiers overlaps_ok suppression matches against)
# ---------------------------------------------------------------------------

def _screw_label(s):
    return f"screw@{s.x:.2f},{s.y:.2f}"


def _text_label(t):
    return f"text:{t.text}"


def _screw_coords(label):
    """Parse the "x,y" numbers out of a "screw@x,y" label (or overlaps_ok
    entry of the same form), rounded to 2 decimals -- exactly the precision
    _screw_label prints -- so entries written with different precision than
    the warning still match (e.g. "screw@7.5,3" matches "screw@7.50,3.00")."""
    x_str, y_str = label[len("screw@"):].split(",")
    return round(float(x_str), 2), round(float(y_str), 2)


def _label_matches(matcher, label):
    """Does an overlaps_ok entry name (`matcher`) refer to a given warning
    label? Declared component names, "title", and "text:<content>" entries
    match by exact string equality (labels are formatted identically to how
    a spec author would write them). "screw" matches any screw label;
    "screw@x,y" matches a screw label at the same coordinates after rounding
    both sides to 2 decimals."""
    if matcher == label:
        return True
    if matcher == "screw":
        return label.startswith("screw@")
    if matcher.startswith("screw@") and label.startswith("screw@"):
        return _screw_coords(matcher) == _screw_coords(label)
    return False


# ---------------------------------------------------------------------------
# run_checks
# ---------------------------------------------------------------------------

def run_checks(layout, spec, db, renderer):
    errors = []
    warnings = []

    overlaps_ok = spec.overlaps_ok or []

    def suppressed(a, b):
        for entry in overlaps_ok:
            if len(entry) == 1:
                m = entry[0]
                if _label_matches(m, a) or _label_matches(m, b):
                    return True
            else:
                m1, m2 = entry
                if ((_label_matches(m1, a) and _label_matches(m2, b)) or
                        (_label_matches(m1, b) and _label_matches(m2, a))):
                    return True
        return False

    # Duplicate placed-component name (defense in depth; spec.py already
    # rejects this at parse time).
    seen_names = set()
    for comp in layout.components:
        if comp.name in seen_names:
            errors.append(f"duplicate component name: {comp.name!r}")
        seen_names.add(comp.name)

    # Every checkable element with a known extent: (label, extent). Zones,
    # glyphs, and connector bars have no extent and are exempt.
    entries = []
    for comp in layout.components:
        extent = _component_extent(comp, db)
        if extent is None:
            errors.append(
                f"component {comp.name!r}: unknown widget class "
                f"{comp.widget!r} (no size data)")
            continue
        entries.append((comp.name, extent))

    for s in layout.screws:
        entries.append((_screw_label(s), _screw_extent(s)))

    for t in layout.texts:
        entries.append((_text_label(t), _text_extent(t, renderer)))

    entries.append(("title", _title_extent(layout.title, renderer)))

    # Bounds errors.
    for label, extent in entries:
        over = _bounds_overhang(extent, layout.width, layout.height)
        if over:
            errors.append(
                f"{label} extends {over:.2f}mm outside the panel bounds "
                f"(0..{layout.width:.1f} x 0..{layout.height:.1f})")

    # Overlap warnings: every intersecting pair, suppressible via overlaps_ok.
    for i in range(len(entries)):
        a_label, a_extent = entries[i]
        for j in range(i + 1, len(entries)):
            b_label, b_extent = entries[j]
            depth = _depth(a_extent, b_extent)
            if depth is None or suppressed(a_label, b_label):
                continue
            warnings.append(f"OVERLAP {a_label} ~ {b_label} depth {depth:.2f}mm")

    return Report(errors=errors, warnings=warnings)
