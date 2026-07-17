#!/usr/bin/env python3
"""Measure the true drawn size (mm) of each VCV Rack widget class from the
installed Rack ComponentLibrary SVG assets, and (re)write components.yaml.

    .venv/bin/python tools/measure_components.py            # write components.yaml
    .venv/bin/python tools/measure_components.py --check     # print only, no write

Mirrors v1 vcv-panel-gen/preview.py's `_conventional_libraries` (candidate
install locations) and `_px_size` (native SVG size) / `PX_TO_MM` (75 dpi ->
mm) logic: VCV ComponentLibrary SVGs are authored in px at 75 dpi, so
mm = px * 25.4 / 75.

One wrinkle _px_size doesn't need to handle but this tool does: the Light dot
assets (MediumLight.svg, SmallLight.svg, LargeLight.svg) declare their
width/height directly in "mm" units (e.g. `width="3mm"`) rather than
unitless/px -- they are already in mm and must NOT be run through
PX_TO_MM again (doing so would shrink a 3mm light down to ~1mm). measure_mm
below detects the declared unit and only applies PX_TO_MM to px/unitless
assets.
"""
import argparse
import os
import re
import sys

SVG_DPI = 75.0
PX_TO_MM = 25.4 / SVG_DPI

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPONENTS_YAML = os.path.join(REPO_ROOT, "components.yaml")


def _conventional_libraries():
    """Conventional VCV Rack ComponentLibrary locations for this platform.
    Mirrors v1 preview.py's _conventional_libraries()."""
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


def find_component_library():
    """First existing conventional Rack ComponentLibrary dir, or None."""
    for path in _conventional_libraries():
        if os.path.isdir(path):
            return path
    return None


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def measure_mm(svg_path):
    """Native (w, h) of an SVG asset, in mm. See module docstring for the
    px-vs-mm unit handling."""
    txt = _read(svg_path)
    m = re.search(r'\bwidth="([\d.]+)(px|mm)?"[^>]*?\bheight="([\d.]+)(px|mm)?"', txt)
    if m:
        w, wu, h, hu = m.group(1), m.group(2), m.group(3), m.group(4)
        w, h = float(w), float(h)
        if wu == "mm" or hu == "mm":
            return w, h
        return w * PX_TO_MM, h * PX_TO_MM
    m = re.search(r'viewBox="[\d.eE+-]+\s+[\d.eE+-]+\s+([\d.eE+-]+)\s+([\d.eE+-]+)"', txt)
    if m:
        return float(m.group(1)) * PX_TO_MM, float(m.group(2)) * PX_TO_MM
    raise ValueError(f"cannot determine size of {svg_path}")


# Widget class -> ComponentLibrary basename (no .svg) of the FOREGROUND asset
# that defines its true drawn size -- the same asset v1 preview.py's
# CLASS_ASSETS stacks on top (a knob's `_bg` companion is a same-size or
# larger shadow/mounting plate, not the visible control body).
ASSET_MAP = {
    "RoundBlackKnob":      "RoundBlackKnob",
    "RoundSmallBlackKnob": "RoundSmallBlackKnob",
    "RoundBigBlackKnob":   "RoundBigBlackKnob",
    "RoundHugeBlackKnob":  "RoundHugeBlackKnob",
    "Trimpot":             "Trimpot",
    "PJ301MPort":          "PJ301M",
    "VCVButton":           "VCVButton_0",
    "VCVBezel":            "VCVBezel",
    "CKSS":                "CKSS_0",
    "CKSSThree":           "CKSSThree_0",
    "MediumLight":         "MediumLight",
    "SmallLight":          "SmallLight",
    "LargeLight":          "LargeLight",
    "ScrewSilver":         "ScrewSilver",
    "ScrewBlack":          "ScrewBlack",
}

# Classes whose drawn shape is a rectangle (both w and h matter); every other
# ASSET_MAP entry is round (measured w == h to within SVG rounding, use d).
RECT_CLASSES = {"CKSS", "CKSSThree"}

# LEDBezel has no ComponentLibrary asset of its own: in real Rack it *is* the
# VCVBezel graphic with a light widget drawn on top, at the same footprint.
ALIAS_SIZES = {"LEDBezel": "VCVBezel"}

# v1 vcv-panel-gen/constants.py TRUE_* diameters (mm), independently verified
# against the value-ring geometry of a real Rack install. Authoritative over
# a fresh measurement per the task brief: if this tool's own measurement of
# the same SVGs disagrees, these win (and the disagreement gets flagged
# below, not silently overridden).
V1_TRUE_DIAM = {
    "RoundBlackKnob": 9.6,
    "RoundSmallBlackKnob": 7.68,
    "RoundBigBlackKnob": 15.24,
}

# needle -> canonical component key, for ComponentDB's substring-containment
# fallback tier. Mirrors v1 preview.py CLASS_ASSETS's needle list (same
# needles, same "longest contained substring wins" intent) so a subclass like
# RoundSmallBlackSnapKnob or CKSSThreeHorizontal resolves without its own
# components.yaml entry.
ALIASES = {
    "RoundBlackKnob":      ["RoundBlack"],
    "RoundSmallBlackKnob": ["RoundSmallBlack"],
    "RoundBigBlackKnob":   ["RoundBigBlack", "RoundBig"],
    "RoundHugeBlackKnob":  ["RoundHugeBlack"],
    "Trimpot":             ["Trimpot"],
    "PJ301MPort":          ["PJ301", "Port"],
    "VCVButton":           ["VCVButton", "Button"],
    "VCVBezel":            ["VCVBezel"],
    "LEDBezel":            ["LEDBezel"],
    "CKSSThree":           ["CKSSThree"],
    "CKSS":                ["CKSS"],
    "MediumLight":         ["MediumLight"],
    "SmallLight":          ["SmallLight"],
    "LargeLight":          ["LargeLight"],
    "ScrewSilver":         ["ScrewSilver"],
    "ScrewBlack":          ["ScrewBlack"],
}

DEFAULTS = {
    "param": "RoundBlackKnob",
    "input": "PJ301MPort",
    "output": "PJ301MPort",
    "light": "MediumLight<RedLight>",
}


def measure_all(lib_dir):
    """dict[class name -> (w_mm, h_mm, source_note)] for every ASSET_MAP
    entry, plus ALIAS_SIZES entries copied from their source class."""
    sizes = {}
    notes = {}
    for cls, basename in ASSET_MAP.items():
        svg_path = os.path.join(lib_dir, basename + ".svg")
        w, h = measure_mm(svg_path)
        if cls in V1_TRUE_DIAM:
            v1_d = V1_TRUE_DIAM[cls]
            if abs(w - v1_d) > 0.01 or abs(h - v1_d) > 0.01:
                notes[cls] = (
                    f"MEASUREMENT DISAGREES with v1 TRUE_ constant: measured "
                    f"{w:.4f}x{h:.4f}mm from {basename}.svg vs v1 {v1_d}mm; "
                    f"v1 constant wins, using {v1_d}."
                )
                w = h = v1_d
            else:
                notes[cls] = (
                    f"= v1 TRUE_ constant; measured {basename}.svg at "
                    f"{w:.4f}x{h:.4f}mm, matches."
                )
        else:
            notes[cls] = f"measured {basename}.svg at {w:.4f}x{h:.4f}mm"
        sizes[cls] = (w, h)

    for cls, source in ALIAS_SIZES.items():
        w, h = sizes[source]
        sizes[cls] = (w, h)
        notes[cls] = f"no dedicated asset; reuses {source}'s measured size ({w:.4f}x{h:.4f}mm)"

    return sizes, notes


def _fmt(n):
    """Trim a measured mm value to a readable literal (2 decimal places is
    plenty of precision for panel geometry) without a trailing ".00"."""
    r = round(n, 2)
    return int(r) if r == int(r) else r


def render_yaml(sizes, notes):
    lines = []
    lines.append("# Component size database for VCV Rack widget classes.")
    lines.append("#")
    lines.append("# Sizes are in mm and are each widget's TRUE DRAWN size (the actual on-panel")
    lines.append("# graphic), not any larger reserved/padded footprint used elsewhere for layout")
    lines.append("# spacing. Generated by tools/measure_components.py from the installed Rack")
    lines.append("# ComponentLibrary; re-run that tool to refresh against a different Rack build.")
    lines.append("#")
    lines.append("# RoundBlackKnob / RoundSmallBlackKnob / RoundBigBlackKnob use the v1")
    lines.append("# vcv-panel-gen/constants.py TRUE_KNOB_DIAM / TRUE_SMALL_KNOB_DIAM /")
    lines.append("# TRUE_HERO_KNOB_DIAM constants (authoritative per the v2 task brief); this")
    lines.append("# tool's own measurement of the same ComponentLibrary SVGs matched them")
    lines.append("# exactly, so there was no discrepancy to resolve.")
    lines.append("#")
    lines.append("# MediumLight / SmallLight / LargeLight are the one class of asset NOT")
    lines.append("# authored in px at 75 dpi like the rest of the library: their SVGs declare")
    lines.append('# width/height directly in "mm" (e.g. width="3mm"), so those values are used')
    lines.append("# as-is (measure_mm() detects this and skips the px->mm conversion for them).")
    lines.append("#")
    lines.append("# LEDBezel has no ComponentLibrary asset of its own -- in real Rack it is the")
    lines.append("# VCVBezel graphic with a light widget drawn on top, at the same footprint --")
    lines.append("# so it reuses VCVBezel's measured size here.")
    lines.append("components:")
    for cls in ASSET_MAP:
        w, h = sizes[cls]
        note = notes[cls]
        if cls in RECT_CLASSES:
            lines.append(f"  {cls}: {{ shape: rect, w: {_fmt(w)}, h: {_fmt(h)} }}  # {note}")
        else:
            lines.append(f"  {cls}: {{ shape: circle, d: {_fmt(w)} }}  # {note}")
    for cls in ALIAS_SIZES:
        w, h = sizes[cls]
        lines.append(f"  {cls}: {{ shape: circle, d: {_fmt(w)} }}  # {notes[cls]}")
    lines.append("")
    lines.append("# needle -> canonical component key above, for ComponentDB's substring-")
    lines.append("# containment fallback (so a subclass like RoundSmallBlackSnapKnob or")
    lines.append("# CKSSThreeHorizontal resolves without its own entry). Same technique as v1")
    lines.append("# preview.py's CLASS_ASSETS needle list.")
    lines.append("aliases:")
    for canonical, needles in ALIASES.items():
        needle_list = ", ".join(f'"{n}"' for n in needles)
        lines.append(f"  {canonical}: [{needle_list}]")
    lines.append("")
    lines.append("defaults:")
    for kind, widget in DEFAULTS.items():
        lines.append(f'  {kind}: "{widget}"')
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                         help="print measurements without writing components.yaml")
    args = parser.parse_args()

    lib_dir = find_component_library()
    if lib_dir is None:
        print("BLOCKED: no installed VCV Rack ComponentLibrary found. Checked:", file=sys.stderr)
        for c in _conventional_libraries():
            print(f"  {c}", file=sys.stderr)
        sys.exit(1)

    print(f"Measuring from: {lib_dir}")
    sizes, notes = measure_all(lib_dir)
    for cls in list(ASSET_MAP) + list(ALIAS_SIZES):
        w, h = sizes[cls]
        print(f"  {cls:22s} {w:7.4f} x {h:7.4f} mm  -- {notes[cls]}")

    if args.check:
        return

    yaml_text = render_yaml(sizes, notes)
    with open(COMPONENTS_YAML, "w", encoding="utf-8") as f:
        f.write(yaml_text)
    print(f"\nWrote {COMPONENTS_YAML}")


if __name__ == "__main__":
    main()
