"""Position-sync a hand-maintained MetaModule <Slug>_info.hh from a panel SVG.

The header is the source of truth for STRUCTURE — element names, order,
wrapper types, defaults, menu-only alt-params — because those are a contract
with the module's DSP code and tests. The generated SVG is the source of
truth for GEOMETRY. This tool rewrites only the x/y mm coordinates of header
elements whose enum name matches an SVG component (plus width/height for
display rects), and on any mismatch exits nonzero without writing.

Matching: each component id in the SVG's hidden layer (`NAME#WidgetClass`)
derives an enum name by the generator's naming convention (strip
_PARAM/_INPUT/_OUTPUT/_LIGHT, CamelCase, append Knob/Button/Switch/In/Out/
Light by kind). Hand-named enums that don't follow the convention are wired
up with a --map YAML file (`EnumName: SVG_ID`, or `EnumName: null` to mark a
menu-only element as deliberately position-less). A map value may also be a
dict, `{id: SVG_ID, mm_aspect: <ratio>}`, to apply a per-element geometry
override (e.g. reshaping a display's width/height) on top of the sync.
Header elements with no mapping are left untouched and reported (with
--strict, an element that is neither synced nor mapped to null is an error
instead); SVG components with no mapping are an error, so a panel control
can never silently stop syncing.

Usage: python3 mm_sync.py --header PATH --svg PATH [--map PATH] [--strict]
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import yaml


class MMSyncError(Exception):
    pass


KIND_BY_FILL = {"#ff0000": "param", "#00ff00": "input", "#0000ff": "output",
                "#ff00ff": "light", "#ffff00": "widget"}
PARAM_SUFFIX = {"RoundBlackKnob": "Knob", "RoundBigBlackKnob": "Knob",
                "RoundSmallBlackKnob": "Knob", "RoundBlackSnapKnob": "Knob",
                "Trimpot": "Knob", "VCVButton": "Button", "CKSS": "Switch"}
KIND_SUFFIX = {"input": "In", "output": "Out", "light": "Light", "widget": ""}
_STRIP_SUFFIXES = ("_PARAM", "_INPUT", "_OUTPUT", "_LIGHT")

OVERRIDE_KEYS = {"id", "mm_aspect"}


def _parse_aspect(value, en):
    """Parse an mm_aspect value ('16:9', '2:1', 1.78) into a positive float."""
    if isinstance(value, bool):
        raise MMSyncError(f"{en}: mm_aspect must be a number or 'W:H', "
                          f"got {value!r}")
    if isinstance(value, (int, float)):
        aspect = float(value)
    elif isinstance(value, str) and ":" in value:
        w, _, h = value.partition(":")
        try:
            aspect = float(w) / float(h)
        except (ValueError, ZeroDivisionError):
            raise MMSyncError(f"{en}: bad mm_aspect {value!r}")
    elif isinstance(value, str):
        try:
            aspect = float(value)
        except ValueError:
            raise MMSyncError(f"{en}: bad mm_aspect {value!r}")
    else:
        raise MMSyncError(f"{en}: mm_aspect must be a number or 'W:H', "
                          f"got {value!r}")
    if aspect <= 0:
        raise MMSyncError(f"{en}: mm_aspect must be positive, got {value!r}")
    return aspect


def _normalize_map(mapping):
    """Split the raw sync-map into (id_map, overrides, ignored).

    A value may be an SVG id string, None (menu-only), or a dict
    {id: SVG_ID, mm_aspect: <ratio>} carrying a geometry override.
    The reserved key `ignore` holds a list of SVG ids that deliberately
    have no header element (e.g. a VCV-only control that is a menu
    alt-param on MetaModule).
    """
    id_map, overrides = {}, {}
    mapping = dict(mapping or {})
    ignored = mapping.pop("ignore", None) or []
    if not isinstance(ignored, list) or any(not isinstance(s, str) for s in ignored):
        raise MMSyncError("'ignore' must be a list of SVG component ids")
    for en, val in mapping.items():
        if isinstance(val, dict):
            unknown = set(val) - OVERRIDE_KEYS
            if unknown:
                raise MMSyncError(
                    f"{en}: unknown map key(s) {sorted(unknown)}; "
                    f"allowed: {sorted(OVERRIDE_KEYS)}")
            if "id" not in val:
                raise MMSyncError(f"{en}: dict map entry needs an 'id'")
            if val["id"] is None and "mm_aspect" in val:
                raise MMSyncError(f"{en}: mm_aspect needs a non-null id")
            id_map[en] = val["id"]
            if "mm_aspect" in val:
                overrides[en] = {"aspect": _parse_aspect(val["mm_aspect"], en)}
        else:
            id_map[en] = val
    return id_map, overrides, ignored


# An element literal: `Knob{{{10.293f, 47.533f, <rest>`. Floats may be
# digits-dot ("9.") as well as digits-dot-digits ("10.293").
ELEM_RE = re.compile(r"^(\s*[A-Za-z_]\w*\{+)(-?\d+\.?\d*)f,\s*(-?\d+\.?\d*)f,(.*)$")
# Display width/height: the last two floats before the closing braces, after
# the long_name's empty string.
SIZE_RE = re.compile(r'^(.*"",\s*)(-?\d+\.?\d*)f,\s*(-?\d+\.?\d*)f(\}+,?\s*)$')


@dataclass
class Comp:
    shape: str                 # "circle" (x/y = center) or "rect" (top-left)
    x: float
    y: float
    w: float | None
    h: float | None
    fill: str
    widget: str


@dataclass
class Report:
    updated: int
    untouched: list


def derive_enum_name(name, fill, widget):
    kind = KIND_BY_FILL.get((fill or "").lower())
    if kind is None:
        raise MMSyncError(f"{name}: unknown component fill {fill!r}")
    if kind == "param":
        suffix = PARAM_SUFFIX.get(widget)
        if suffix is None:
            raise MMSyncError(
                f"{name}: no enum-name rule for param widget {widget!r}; "
                f"add a --map entry for it")
    else:
        suffix = KIND_SUFFIX[kind]
    base = name
    for s in _STRIP_SUFFIXES:
        if base.endswith(s):
            base = base[: -len(s)]
            break
    return "".join(w.capitalize() for w in base.split("_") if w) + suffix


def read_svg_components(path):
    """Component-id name -> Comp, from the SVG's hidden components layer."""
    comps = {}
    for node in ET.parse(path).getroot().iter():
        node_id = node.get("id", "")
        if "#" not in node_id:
            continue
        name, _, widget = node_id.partition("#")
        if name in comps:
            raise MMSyncError(f"duplicate SVG component id: {name}")
        tag = node.tag.split("}")[-1]
        fill = node.get("fill", "")
        if tag == "circle":
            comps[name] = Comp("circle", float(node.get("cx")),
                               float(node.get("cy")), None, None, fill, widget)
        elif tag == "rect":
            comps[name] = Comp("rect", float(node.get("x")), float(node.get("y")),
                               float(node.get("width")), float(node.get("height")),
                               fill, widget)
        else:
            raise MMSyncError(f"SVG id {name} is on an unsupported <{tag}>")
    if not comps:
        raise MMSyncError(f"{path}: no NAME#Widget component ids found")
    return comps


def _parse_header(lines):
    """Return (element line indices, enum names), validated 1:1 in order."""
    starts = [i for i, l in enumerate(lines) if "Elements{{" in l]
    if len(starts) != 1:
        raise MMSyncError(f"expected exactly one 'Elements{{{{' array, "
                          f"found {len(starts)}")
    end = next((i for i in range(starts[0] + 1, len(lines))
                if lines[i].strip().startswith("}};")), None)
    if end is None:
        raise MMSyncError("Elements array has no closing '}};'")
    elem_idx = []
    for i in range(starts[0] + 1, end):
        if not lines[i].strip() or lines[i].strip().startswith("//"):
            continue
        if not ELEM_RE.match(lines[i]):
            raise MMSyncError(
                f"line {i + 1} inside the Elements array is not a "
                f"one-per-line element literal: {lines[i].strip()!r}")
        elem_idx.append(i)

    estarts = [i for i, l in enumerate(lines) if "enum class Elem" in l]
    if len(estarts) != 1:
        raise MMSyncError("expected exactly one 'enum class Elem' block")
    eend = next((i for i in range(estarts[0] + 1, len(lines))
                 if lines[i].strip().startswith("};")), None)
    if eend is None:
        raise MMSyncError("Elem enum has no closing '};'")
    enum_names = [t.strip() for i in range(estarts[0] + 1, eend)
                  if not lines[i].strip().startswith("//")
                  for t in lines[i].split(",") if t.strip()]

    if len(elem_idx) != len(enum_names):
        raise MMSyncError(
            f"{len(elem_idx)} element lines but {len(enum_names)} enum "
            f"entries; the array and the enum must pair 1:1 in order")
    return elem_idx, enum_names


def _assign(comps, enum_names, mapping, ignored=()):
    """enum name -> svg id, from the explicit map plus auto-derivation.
    `ignored` svg ids are deliberately element-less and skipped."""
    enum_set = set(enum_names)
    mapping = dict(mapping or {})
    for sid in ignored:
        if sid not in comps:
            raise MMSyncError(
                f"--map ignore: unknown SVG component {sid!r} (typo, or the "
                f"control was removed from the panel — drop the entry)")
    for en, sid in mapping.items():
        if en not in enum_set:
            raise MMSyncError(f"--map names unknown enum {en!r}")
        if sid is not None and sid not in comps:
            raise MMSyncError(f"--map {en}: unknown SVG component {sid!r}")
    assigned = {en: sid for en, sid in mapping.items() if sid}
    claimed = set(assigned.values()) | set(ignored)

    unmatched = []
    for name in sorted(comps):
        if name in claimed:
            continue
        derived = derive_enum_name(name, comps[name].fill, comps[name].widget)
        if derived in mapping or derived not in enum_set:
            unmatched.append(name)
        elif derived in assigned:
            raise MMSyncError(
                f"both {assigned[derived]!r} and {name!r} resolve to enum "
                f"{derived!r}; disambiguate with --map")
        else:
            assigned[derived] = name
    if unmatched:
        raise MMSyncError(
            "SVG components with no matching header element: "
            + ", ".join(unmatched)
            + " — add --map entries (a panel control must never silently "
              "stop syncing)")
    return assigned


def sync_text(text, comps, mapping=None, strict=False):
    """Return (new header text, Report). Raises MMSyncError on any mismatch."""
    lines = text.splitlines()
    elem_idx, enum_names = _parse_header(lines)
    id_map, overrides, ignored = _normalize_map(mapping)
    assigned = _assign(comps, enum_names, id_map, ignored)

    updated, untouched = 0, []
    for idx, en in zip(elem_idx, enum_names):
        sid = assigned.get(en)
        if sid is None:
            untouched.append(en)
            continue
        comp = comps[sid]
        m = ELEM_RE.match(lines[idx])
        rest = m.group(4)
        coords_token = rest.lstrip().split(",")[0].strip()
        if comp.shape == "circle":
            if en in overrides:
                raise MMSyncError(
                    f"{en}: mm_aspect is only valid on a rectangular display, "
                    f"not circle component {sid}")
            if coords_token != "Center":
                raise MMSyncError(
                    f"{en}: circle component {sid} needs Center coords, "
                    f"header line says {coords_token!r}")
            x, y = comp.x, comp.y
        else:
            if coords_token == "TopLeft":
                x, y = comp.x, comp.y
            elif coords_token == "Center":
                x, y = comp.x + comp.w / 2.0, comp.y + comp.h / 2.0
            else:
                raise MMSyncError(
                    f"{en}: rect component {sid} needs TopLeft or Center "
                    f"coords, header line says {coords_token!r}")
            sm = SIZE_RE.match(rest)
            if not sm:
                raise MMSyncError(f"{en}: cannot find width/height to rewrite")
            w, h = comp.w, comp.h
            if en in overrides:
                w = overrides[en]["aspect"] * h
                if coords_token == "TopLeft":
                    x = comp.x + (comp.w - w) / 2.0
                # Center coords: stored center stays put; only width changes.
            rest = f"{sm.group(1)}{w:.3f}f, {h:.3f}f{sm.group(4)}"
        lines[idx] = f"{m.group(1)}{x:.3f}f, {y:.3f}f,{rest}"
        updated += 1
    if strict:
        declared_null = {en for en, sid in id_map.items() if sid is None}
        stale = [en for en in untouched if en not in declared_null]
        if stale:
            raise MMSyncError(
                "strict: header elements with no SVG match and no explicit "
                "null map entry: " + ", ".join(stale))
    return "\n".join(lines) + "\n", Report(updated, untouched)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Rewrite element coordinates in a hand-maintained "
                    "MetaModule info.hh from a generated panel SVG.")
    ap.add_argument("--header", required=True)
    ap.add_argument("--svg", required=True)
    ap.add_argument("--map", default=None,
                    help="YAML mapping EnumName: SVG_ID (or null) for enums "
                         "that don't follow the generator's naming convention; "
                         "a value may also be {id: SVG_ID, mm_aspect: <ratio>} "
                         "for a per-element geometry override")
    ap.add_argument("--strict", action="store_true",
                    help="every header element must be synced or explicitly "
                         "mapped to null; anything else is an error")
    args = ap.parse_args(argv)
    try:
        mapping = None
        if args.map:
            with open(args.map) as f:
                mapping = yaml.safe_load(f)
            if mapping is not None and not isinstance(mapping, dict):
                raise MMSyncError(f"{args.map}: map file must be a mapping")
        comps = read_svg_components(args.svg)
        with open(args.header) as f:
            text = f.read()
        new_text, report = sync_text(text, comps, mapping, strict=args.strict)
    except (MMSyncError, OSError, ET.ParseError) as e:
        print(f"mm_sync: {e}", file=sys.stderr)
        return 1
    with open(args.header, "w") as f:
        f.write(new_text)
    msg = f"Updated {report.updated} element(s)"
    if report.untouched:
        msg += (f"; {len(report.untouched)} untouched: "
                + ", ".join(report.untouched))
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
