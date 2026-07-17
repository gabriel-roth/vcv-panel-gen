#!/usr/bin/env python3
"""Composite the real VCV ComponentLibrary art onto a generated faceplate.

The generator writes a hidden `components` layer where every control is a shape
tagged with its widget class in the id (e.g. `SIZE_PARAM#RoundBlackKnob`). Opening
the bare SVG shows only background + labels, which looks nothing like VCV. This
reads that layer, drops the actual knob/port/button/switch graphics onto the
faceplate at each control's position, and writes a preview SVG that renders in
a browser looking like the module will in Rack.

    python preview.py res/Slug.svg               # -> res/Slug.preview.svg
    python preview.py res/Slug.svg --out /tmp/p.svg
    python preview.py res/Slug.svg --open        # also open in a browser

Knob pointers render at their default (centered) rotation; placement, size, and
hardware appearance match VCV. Lights render as their tint circle; the screen
region is left to the faceplate. Unknown classes fall back to a labeled marker
so nothing is silently dropped.
"""
import argparse
import base64
import functools
import os
import re
import sys
import webbrowser
import xml.etree.ElementTree as ET

# VCV ComponentLibrary SVGs are authored in px at 75 dpi.
SVG_DPI = 75.0
PX_TO_MM = 25.4 / SVG_DPI

def _conventional_libraries():
    """Conventional VCV Rack ComponentLibrary locations for this platform."""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return [
            "/Applications/VCV Rack 2 Free.app/Contents/Resources/res/ComponentLibrary",
            "/Applications/VCV Rack 2 Pro.app/Contents/Resources/res/ComponentLibrary",
        ]
    if sys.platform.startswith("win"):
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        return [
            os.path.join(pf, "VCV", "Rack2Free", "res", "ComponentLibrary"),
            os.path.join(pf, "VCV", "Rack2Pro", "res", "ComponentLibrary"),
        ]
    return [
        os.path.join(home, ".local", "share", "Rack2", "res", "ComponentLibrary"),
        "/opt/Rack2/res/ComponentLibrary",
        "/usr/share/Rack2/res/ComponentLibrary",
    ]


CONVENTIONAL_LIBRARIES = _conventional_libraries()


def default_library(candidates=None):
    """First existing conventional library dir, else the first candidate
    (used only to name a path in the not-found error)."""
    candidates = candidates if candidates is not None else CONVENTIONAL_LIBRARIES
    for path in candidates:
        if os.path.isdir(path):
            return path
    return candidates[0]

# Widget class -> ordered list of ComponentLibrary basenames to stack (bottom
# first). Knobs are a static shadow/body (`_bg`) under the rotating body. The
# lookup is by longest-matching substring so subclasses (RoundSmallBlackSnapKnob,
# PJ301MPort, custom *Button) resolve without an exact entry.
CLASS_ASSETS = [
    ("RoundBigBlack",   ["RoundBigBlackKnob_bg", "RoundBigBlackKnob"]),
    ("RoundSmallBlack", ["RoundSmallBlackKnob_bg", "RoundSmallBlackKnob"]),
    ("RoundBlack",      ["RoundBlackKnob_bg", "RoundBlackKnob"]),
    ("RoundBig",        ["RoundBigBlackKnob_bg", "RoundBigBlackKnob"]),
    ("Trimpot",         ["Trimpot_bg", "Trimpot"]),
    ("PJ301",           ["PJ301M"]),
    ("Port",            ["PJ301M"]),
    ("CKSSThree",       ["CKSSThree_0"]),
    ("CKSS",            ["CKSS_0"]),
    ("VCVButton",       ["VCVButton_0"]),
    ("VCVBezel",        ["VCVBezel"]),
    ("Button",          ["VCVButton_0"]),
    ("TL1105",          ["TL1105_0"]),
]

# Classes handled specially rather than by a ComponentLibrary asset: the screen
# widget renders as a placeholder rect marking the display area (VCV draws the
# live content at runtime); lights render as a small colored dot.
SCREEN_SUBSTR = ("Widget",)
LIGHT_SUBSTR = ("Light",)


def _class_of(elem_id):
    return elem_id.split("#", 1)[1] if "#" in elem_id else elem_id


def _assets_for(cls):
    for needle, assets in CLASS_ASSETS:
        if needle in cls:
            return assets
    return None


@functools.lru_cache(maxsize=None)
def _px_size(svg_path):
    """Native (w, h) in px from width/height, falling back to the viewBox.
    Memoized: a panel reuses the same handful of assets many times."""
    txt = _read(svg_path)
    m = re.search(r'\bwidth="([\d.]+)(?:px)?"[^>]*?\bheight="([\d.]+)(?:px)?"', txt)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'\bviewBox="[\d.eE+-]+\s+[\d.eE+-]+\s+([\d.eE+-]+)\s+([\d.eE+-]+)"', txt)
    if m:
        return float(m.group(1)), float(m.group(2))
    raise ValueError(f"cannot determine size of {svg_path}")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@functools.lru_cache(maxsize=None)
def _data_uri(svg_path):
    """base64 data: URI for an asset. Memoized so an asset used N times is
    read and encoded once, not N times."""
    with open(svg_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


class _AssetDefs:
    """Collects the unique ComponentLibrary assets a preview draws into a
    <defs> block, so each asset's (large) base64 payload is embedded once and
    every placement is a lightweight <use> reference rather than a fresh copy."""

    def __init__(self):
        self._ids = {}          # svg_path -> def id
        self.defs = []          # <image> template lines, in first-seen order

    def use(self, svg_path, cx, cy):
        """A <use> line placing `svg_path` centered on (cx, cy) mm, registering
        the asset's <image> template in the defs block on first sight."""
        def_id = self._ids.get(svg_path)
        w, h = (d * PX_TO_MM for d in _px_size(svg_path))
        if def_id is None:
            def_id = f"asset{len(self._ids)}"
            self._ids[svg_path] = def_id
            self.defs.append(
                f'    <image id="{def_id}" width="{w:.4f}" height="{h:.4f}" '
                f'xlink:href="{_data_uri(svg_path)}"/>'
            )
        x, y = cx - w / 2.0, cy - h / 2.0
        return f'    <use xlink:href="#{def_id}" x="{x:.4f}" y="{y:.4f}"/>'


def _controls(svg_text):
    """Yield (tag, cls, attrs) for each shape in the components layer.

    The widget class comes from the id suffix `NAME#Class` (panel_gen output).
    Hand-authored panels leave the id plain and name the class
    in an HTML comment before a run of shapes (`<!-- RoundBlackKnob: ... -->`),
    so we carry the last-seen comment class forward as a fallback.
    """
    m = re.search(
        r'<g\b[^>]*?(?:inkscape:label="components"|id="components")[^>]*?>(.*?)</g>',
        svg_text, re.DOTALL,
    )
    if not m:
        return
    body = m.group(1)
    comment_cls = None
    for tok in re.finditer(r'<!--(.*?)-->|<(circle|rect)\b([^>]*?)/>', body, re.DOTALL):
        if tok.group(1) is not None:
            cm = re.match(r'\s*([A-Za-z0-9_]+)', tok.group(1))
            comment_cls = cm.group(1) if cm else comment_cls
            continue
        attrs = dict(re.findall(r'(\w[\w:-]*)="([^"]*)"', tok.group(3)))
        eid = attrs.get("id", "")
        cls = eid.split("#", 1)[1] if "#" in eid else (comment_cls or eid)
        yield tok.group(2), cls, attrs


def _center(tag, a):
    if tag == "circle":
        return float(a["cx"]), float(a["cy"])
    return (float(a["x"]) + float(a["width"]) / 2.0,
            float(a["y"]) + float(a["height"]) / 2.0)


def build_preview(src_svg, library):
    txt = _read(src_svg)
    defs = _AssetDefs()
    body = []
    missing = []
    for tag, cls, attrs in _controls(txt):
        if any(s in cls for s in SCREEN_SUBSTR):
            # Placeholder for the display: a dark screen rect at its bounds so
            # the layout shows where the display sits. VCV draws live content on
            # top at runtime. Only rects carry usable bounds; skip a stray shape.
            if tag != "rect":
                continue
            body.append(
                f'    <rect x="{float(attrs["x"]):.2f}" y="{float(attrs["y"]):.2f}" '
                f'width="{float(attrs["width"]):.2f}" height="{float(attrs["height"]):.2f}" '
                f'rx="1" fill="#0a0a0a" stroke="#5a5a5a" stroke-width="0.3"/>'
            )
            continue
        cx, cy = _center(tag, attrs)
        if any(s in cls for s in LIGHT_SUBSTR):
            body.append(
                f'    <circle cx="{cx:.4f}" cy="{cy:.4f}" r="1.5" '
                f'fill="#ff3b30" fill-opacity="0.9"/>'
            )
            continue
        assets = _assets_for(cls)
        drew = False
        if assets:
            for name in assets:
                path = os.path.join(library, name + ".svg")
                if os.path.exists(path):
                    body.append(defs.use(path, cx, cy))
                    drew = True
        if not drew:
            # Try an exact-name asset before giving up.
            path = os.path.join(library, cls + ".svg")
            if os.path.exists(path):
                body.append(defs.use(path, cx, cy))
                drew = True
        if not drew:
            missing.append(cls)
            body.append(
                f'    <circle cx="{cx:.4f}" cy="{cy:.4f}" r="4" '
                f'fill="none" stroke="#ff00ff" stroke-width="0.3"/>'
            )
    lines = ['  <g inkscape:label="preview" id="preview">']
    if defs.defs:
        # Each asset embedded once here; every placement above is a <use>.
        lines.append("    <defs>")
        lines.extend(defs.defs)
        lines.append("    </defs>")
    lines.extend(body)
    lines.append("  </g>")
    group = "\n".join(lines)
    out = txt.replace("</svg>", group + "\n</svg>", 1)
    return out, missing


def wrap_html(svg_text, title):
    """A minimal page that centers the inline SVG so the browser doesn't jam it
    into the top-left/right corner and it scales to the window."""
    inline = re.sub(r'<\?xml[^>]*\?>\s*', '', svg_text, count=1)
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  html, body {{ height: 100%; margin: 0; }}
  body {{ display: flex; align-items: center; justify-content: center;
         background: #555; padding: 24px; box-sizing: border-box; }}
  svg {{ height: auto; width: auto; max-height: 95vh; max-width: 95vw;
        box-shadow: 0 6px 30px rgba(0,0,0,0.5); }}
</style>
{inline}
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("svg", help="generated faceplate SVG (with components layer)")
    ap.add_argument("--out", help="output path (default: <svg>.preview.svg)")
    ap.add_argument("--library", default=os.environ.get("VCV_COMPONENT_LIBRARY", default_library()),
                    help="VCV ComponentLibrary dir")
    ap.add_argument("--open", action="store_true", help="open the preview in a browser")
    args = ap.parse_args()

    if not os.path.isdir(args.library):
        sys.exit(f"ComponentLibrary not found: {args.library}\n"
                 f"Set VCV_COMPONENT_LIBRARY or pass --library.")

    root, ext = os.path.splitext(args.svg)
    out_path = args.out or f"{root}.preview.svg"
    svg, missing = build_preview(args.svg, args.library)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {out_path}")
    if missing:
        uniq = sorted(set(missing))
        print(f"note: no asset for {len(uniq)} class(es), drew markers: {', '.join(uniq)}")
    if args.open:
        html_path = os.path.splitext(out_path)[0] + ".html"
        title = os.path.basename(root)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(wrap_html(svg, title))
        webbrowser.open("file://" + os.path.abspath(html_path))


if __name__ == "__main__":
    main()
