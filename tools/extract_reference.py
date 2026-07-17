#!/usr/bin/env python3
"""Print a human-readable parity report for a RobotBoy reference panel SVG:
every component's id and center (or rect bounds), every panel-layer path's
normalized `d` and approximate bounding box, and every other panel-layer
rect/circle (screws, tint zones, tick marks, screen placeholders drawn
directly rather than via the components layer).

This is the spec-writing aid for Tasks 11-14: read its output for a reference
fixture (tests/fixtures/robotboy/reference/*.svg) to write the declarative
spec that should regenerate the same panel via the v2 pipeline.

    .venv/bin/python tools/extract_reference.py tests/fixtures/robotboy/reference/MF20Filter.svg

Path bounding boxes are an APPROXIMATION: they are computed as the min/max
over every raw coordinate the path data touches, including Bezier control
points, not the tight box of the rendered curve. This is deliberate rather
than lazy -- a cubic/quadratic Bezier curve is mathematically guaranteed to
lie within the convex hull of its control points, so a box drawn around all
control points is guaranteed to *contain* the true rendered path, even
though it may be looser than the curve's real extent (which would require
solving for the curve's parametric extrema). Good enough to eyeball where a
path sits on the panel; not a substitute for the parity tests' exact
normalized-`d` string comparison. Supported commands are M/L/H/V/C/Q/Z
(absolute or relative, matching v1 logo.py's supported subset) -- the same
set every reference fixture actually uses (verified: no S/T/A appear in any
of the four RobotBoy panels this tool was built against).
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))
import parity  # noqa: E402  (path must be set up first)

_NUM_RE = r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?'
_TOKEN_RE = re.compile(r'[MmLlHhVvCcQqZz]|' + _NUM_RE)


def _path_bbox(d):
    """(min_x, min_y, max_x, max_y) over every raw coordinate the path data
    touches (endpoints + control points). See module docstring: this
    contains but does not tightly bound curved segments."""
    tokens = _TOKEN_RE.findall(d)
    i, n = 0, len(tokens)
    cx = cy = sx = sy = 0.0
    xs, ys = [], []

    def num():
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    while i < n:
        cmd = tokens[i]
        i += 1
        if not (len(cmd) == 1 and cmd.isalpha()):
            # malformed/unsupported data; stop rather than misparse.
            break
        rel = cmd.islower()
        u = cmd.upper()
        if u == "Z":
            cx, cy = sx, sy
            continue
        if u == "M":
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            cx, cy = x, y
            sx, sy = x, y
            xs.append(x); ys.append(y)
            while i < n and not (len(tokens[i]) == 1 and tokens[i].isalpha()):
                x, y = num(), num()
                if rel:
                    x, y = cx + x, cy + y
                cx, cy = x, y
                xs.append(x); ys.append(y)
        elif u == "L":
            while i < n and not (len(tokens[i]) == 1 and tokens[i].isalpha()):
                x, y = num(), num()
                if rel:
                    x, y = cx + x, cy + y
                cx, cy = x, y
                xs.append(x); ys.append(y)
        elif u == "H":
            while i < n and not (len(tokens[i]) == 1 and tokens[i].isalpha()):
                x = num()
                x = cx + x if rel else x
                cx = x
                xs.append(x); ys.append(cy)
        elif u == "V":
            while i < n and not (len(tokens[i]) == 1 and tokens[i].isalpha()):
                y = num()
                y = cy + y if rel else y
                cy = y
                xs.append(cx); ys.append(y)
        elif u == "C":
            while i < n and not (len(tokens[i]) == 1 and tokens[i].isalpha()):
                x1, y1, x2, y2, x, y = (num() for _ in range(6))
                if rel:
                    x1, y1, x2, y2, x, y = (cx + x1, cy + y1, cx + x2, cy + y2, cx + x, cy + y)
                cx, cy = x, y
                xs.extend([x1, x2, x]); ys.extend([y1, y2, y])
        elif u == "Q":
            while i < n and not (len(tokens[i]) == 1 and tokens[i].isalpha()):
                x1, y1, x, y = (num() for _ in range(4))
                if rel:
                    x1, y1, x, y = (cx + x1, cy + y1, cx + x, cy + y)
                cx, cy = x, y
                xs.extend([x1, x]); ys.extend([y1, y])
        else:
            # S/T/A or anything else unsupported: skip the command letter and
            # keep going from the next token rather than aborting the whole
            # report over one unhandled path.
            continue
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _panel_shapes(svg_path):
    """[(tag, attrs-dict), ...] for every <rect>/<circle> directly in the
    panel layer, in document order (screws, tint zones, tick marks, etc --
    everything that ISN'T a <path> and isn't in the components layer)."""
    body = parity._layer_body(parity._read(svg_path), "panel")
    shapes = []
    if body is None:
        return shapes
    for m in re.finditer(r'<(circle|rect)\b([^>]*?)/>', body, re.DOTALL):
        shapes.append((m.group(1), parity._attrs(m.group(2))))
    return shapes


def _fmt_num(x):
    return f"{x:.3f}".rstrip("0").rstrip(".") or "0"


def print_report(svg_path):
    print(f"=== {svg_path} ===\n")

    print("--- components layer (id -> shape) ---")
    components = parity.components_of(svg_path)
    if not components:
        print("  (none found)")
    for eid in sorted(components):
        shape = components[eid]
        if shape[0] == "circle":
            _, cx, cy = shape
            print(f"  {eid:40s} circle  cx={cx:<10} cy={cy}")
        else:
            _, x, y, w, h = shape
            print(f"  {eid:40s} rect    x={x:<10} y={y:<10} w={w:<10} h={h}")
    print(f"  ({len(components)} total)\n")

    print("--- panel layer: <path> elements (normalized d + approx bbox) ---")
    paths = parity.panel_paths_of(svg_path)
    if not paths:
        print("  (none found)")
    for idx, d in enumerate(paths):
        bbox = _path_bbox(d)
        if bbox is None:
            bbox_str = "(unparsed)"
        else:
            min_x, min_y, max_x, max_y = bbox
            bbox_str = (
                f"x=[{_fmt_num(min_x)}, {_fmt_num(max_x)}] "
                f"y=[{_fmt_num(min_y)}, {_fmt_num(max_y)}]"
            )
        preview = d if len(d) <= 70 else d[:67] + "..."
        print(f"  [{idx:3d}] bbox {bbox_str:40s} d={preview}")
    print(f"  ({len(paths)} total)\n")

    print("--- panel layer: other <rect>/<circle> shapes (not paths) ---")
    shapes = _panel_shapes(svg_path)
    if not shapes:
        print("  (none found)")
    def _n(attrs, key):
        v = attrs.get(key)
        return _fmt_num(float(v)) if v is not None else "?"

    for tag, attrs in shapes:
        label = attrs.get("id") or attrs.get("class") or "(no id)"
        if tag == "circle":
            print(f"  circle  {label:24s} cx={_n(attrs, 'cx'):<10} cy={_n(attrs, 'cy'):<10} r={_n(attrs, 'r')}")
        else:
            print(
                f"  rect    {label:24s} x={_n(attrs, 'x'):<10} y={_n(attrs, 'y'):<10} "
                f"w={_n(attrs, 'width'):<10} h={_n(attrs, 'height')}"
            )
    print(f"  ({len(shapes)} total)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("svg", help="reference (or generated) panel SVG to report on")
    args = ap.parse_args()

    if not os.path.exists(args.svg):
        print(f"BLOCKED: no such file: {args.svg}", file=sys.stderr)
        sys.exit(1)

    print_report(args.svg)


if __name__ == "__main__":
    main()
