"""CLI: build several variants of one panel spec and lay them out side by side
on a single comparison page, with real ComponentLibrary art.

    variants.py VARIANTS.yaml [--out PAGE.html] [--open] [--library DIR] [--theme FILE]

A variants file names a base spec and lists variants as small edits to it,
so a design round is one short file instead of a one-off script:

    base: ../panel-specs/lyrebird.yaml   # relative to this file
    title: Lyrebird INPUT plate, round 1  # page heading (optional)
    about: One line under the heading.    # (optional)
    rough: true          # default for every variant (optional, default false)
    crop: [0, 100, 66, 28.5]   # card viewBox in mm (optional; the lightbox shows the full panel)
    overlay: overlay_lyrebird.py   # module defining overlay(spec) -> SVG fragment (optional)
    include_base: true   # first card is the unedited base (default true)
    later:               # parked details, listed on the page (optional)
      - title tracking once the plate is settled
    variants:
      - name: Knob centered
        note: One line saying what this variant tries.
        rough: false     # per-variant override
        crop: null       # per-variant override; null shows the whole panel (e.g. after an hp change)
        set: {hp: 22, title: {tracking: 3.0}}   # deep-merged into the top level
        edit:            # targets: element name, text:CONTENT[#n], zone:N, glyph:N or glyph:FILE
          GESTURE_PARAM: {x: 30}
          text:INPUT: {y: 118, size: null}      # null deletes a key
          zone:3: {arrows: [{side: top, at: 32.9}]}
        remove: [CV_INPUT, glyph:texture.svg]
        add:             # appended to the spec's lists
          elements: [{name: CV_INPUT, x: 50, y: 112}]
          connectors: [[GESTURE_PARAM, CV_INPUT]]

Operations apply in the order set, edit, remove, add, against the base's own
indices. Removing a component also drops its connectors, rings and
overlaps_ok entries. Editing x/y/grid of an element placed by a row/place
block pulls it out of the row as a standalone element (its column slot is
left empty), so one control can move without rewriting the row.

Rough mode leaves out glyphs, zone arrows/notches and the overlay: for
deciding what goes where before any polish.

Each card shows its variant's warnings or errors; a variant that won't build
shows its error instead of stopping the page. Nothing is written but the page.
"""
import argparse
import base64
import copy
import html
import importlib.util
import os
import re
import sys
import tempfile
import webbrowser

import yaml

import panelgen
import preview
from spec import parse_spec

_FILE_KEYS = {"base", "title", "about", "rough", "crop", "overlay", "include_base",
              "later", "variants"}
_VARIANT_KEYS = {"name", "note", "rough", "crop", "set", "edit", "remove", "add"}
_LIST_KEYS = ("elements", "zones", "glyphs", "connectors", "overlaps_ok")


class VariantError(Exception):
    pass


def _reject_unknown(mapping, allowed, ctx):
    bad = sorted(set(mapping) - allowed)
    if bad:
        raise VariantError(f"{ctx}: unknown key(s) {', '.join(bad)}")


# ---------------------------------------------------------------------------
# Edits
# ---------------------------------------------------------------------------

def _merge(dst, src):
    """Deep-merge src into dst: mappings merge, anything else replaces; a
    None value deletes the key."""
    for k, v in src.items():
        if v is None:
            dst.pop(k, None)
        elif isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = copy.deepcopy(v)


def _slots(spec):
    """Every element the spec places, as (index in elements, index in place
    or None, the element's dict-or-string). Row/place items are listed
    individually."""
    out = []
    for i, el in enumerate(spec.get("elements") or []):
        if isinstance(el, dict) and "row" in el and "place" in el:
            for j, item in enumerate(el["place"]):
                if item is not None:
                    out.append((i, j, item))
        else:
            out.append((i, None, el))
    return out


def _item_text(item):
    if isinstance(item, str):
        return item
    if isinstance(item, dict) and "text" in item and "name" not in item:
        return item["text"]
    return None


def _find(spec, target):
    """Resolve a target string to ("element", i, j) / ("zone", i) / ("glyph", i)."""
    if target.startswith("zone:"):
        zones = spec.get("zones") or []
        try:
            i = int(target[5:])
        except ValueError:
            raise VariantError(f"{target!r}: zone index must be an integer")
        if not 0 <= i < len(zones):
            raise VariantError(f"{target!r}: the base has {len(zones)} zones (0-based)")
        return ("zone", i)
    if target.startswith("glyph:"):
        glyphs = spec.get("glyphs") or []
        key = target[6:]
        if key.isdigit():
            i = int(key)
            if not 0 <= i < len(glyphs):
                raise VariantError(f"{target!r}: the base has {len(glyphs)} glyphs (0-based)")
            return ("glyph", i)
        hits = [i for i, g in enumerate(glyphs)
                if os.path.basename(str(g.get("src", ""))) == key]
        if len(hits) != 1:
            raise VariantError(f"{target!r}: matches {len(hits)} glyphs; use glyph:N")
        return ("glyph", hits[0])
    if target.startswith("text:"):
        content, _, nth = target[5:].partition("#")
        hits = [(i, j) for i, j, item in _slots(spec) if _item_text(item) == content]
        n = int(nth) if nth else None
        if n is None and len(hits) != 1:
            raise VariantError(f"{target!r}: matches {len(hits)} text elements; "
                               f"add #n (1-based) to pick one")
        if n is not None and not 1 <= n <= len(hits):
            raise VariantError(f"{target!r}: only {len(hits)} text elements match")
        i, j = hits[(n or 1) - 1]
        return ("element", i, j)
    for i, j, item in _slots(spec):
        if isinstance(item, dict) and item.get("name") == target:
            return ("element", i, j)
    raise VariantError(f"{target!r}: no such element (component name, text:CONTENT, "
                       f"zone:N or glyph:N)")


def _standalone(row_el, j):
    """Row/place item j as a standalone element dict: the row's shared keys,
    then the item's own, then its grid position."""
    block = row_el["row"]
    item = row_el["place"][j]
    out = {k: v for k, v in block.items() if k not in ("grid", "at")}
    if isinstance(item, str) or "name" not in item:
        out.pop("widget", None)
        out.pop("kind", None)
    out.update({"text": item} if isinstance(item, str) else item)
    out["grid"] = block["grid"]
    out["col"] = j + 1
    out["row"] = block["at"]
    return out


def _edit(spec, target, changes, pulled):
    if not isinstance(changes, dict):
        raise VariantError(f"edit {target!r}: must be a mapping of keys to new values")
    hit = _find(spec, target)
    if hit[0] in ("zone", "glyph"):
        _merge(spec[hit[0] + "s"][hit[1]], changes)
        return
    _, i, j = hit
    if j is None:
        el = spec["elements"][i]
        if "x" in changes:
            el.pop("col", None)
        if "y" in changes:
            el.pop("row", None)
        _merge(el, changes)
        return
    row_el = spec["elements"][i]
    item = row_el["place"][j]
    if {"x", "y", "grid"} & set(changes):
        el = _standalone(row_el, j)
        if "x" in changes:
            el.pop("col", None)
        if "y" in changes:
            el.pop("row", None)
        if "x" in changes and "y" in changes:
            el.pop("grid", None)
        _merge(el, changes)
        row_el["place"][j] = None
        pulled.append((i, el))
    else:
        if isinstance(item, str):
            item = row_el["place"][j] = {"text": item}
        _merge(item, changes)


def _drop_refs(spec, name):
    for key in ("connectors", "overlaps_ok"):
        if spec.get(key):
            spec[key] = [e for e in spec[key] if name not in e]
    spec["elements"] = [e for e in spec["elements"]
                        if not (isinstance(e, dict) and e.get("around") == name)]


def _remove(spec, targets):
    hits = [(t, _find(spec, t)) for t in targets]
    drop = {"elements": set(), "zones": set(), "glyphs": set()}
    names = []
    for t, hit in hits:
        if hit[0] == "element":
            _, i, j = hit
            if j is None:
                el = spec["elements"][i]
                drop["elements"].add(i)
            else:
                el = spec["elements"][i]["place"][j]
                spec["elements"][i]["place"][j] = None
            if isinstance(el, dict) and "name" in el:
                names.append(el["name"])
            if _item_text(el) is not None:
                names.append("text:" + _item_text(el))
        else:
            drop[hit[0] + "s"].add(hit[1])
    for key, idx in drop.items():
        if idx:
            spec[key] = [e for k, e in enumerate(spec[key]) if k not in idx]
    for name in names:
        _drop_refs(spec, name)


def apply_variant(base, variant):
    """The base spec dict with one variant's set/edit/remove/add applied."""
    spec = copy.deepcopy(base)
    if variant.get("set"):
        if not isinstance(variant["set"], dict):
            raise VariantError("set: must be a mapping of top-level spec keys")
        _merge(spec, variant["set"])
    pulled = []
    for target, changes in (variant.get("edit") or {}).items():
        _edit(spec, str(target), changes, pulled)
    # Pulled-out row items go right after their row, last index first so
    # earlier insertions don't shift later ones.
    for i, el in sorted(pulled, key=lambda p: p[0], reverse=True):
        spec["elements"].insert(i + 1, el)
    if variant.get("remove"):
        _remove(spec, [str(t) for t in variant["remove"]])
    for key, items in (variant.get("add") or {}).items():
        if key not in _LIST_KEYS:
            raise VariantError(f"add: {key!r} is not one of {', '.join(_LIST_KEYS)}")
        spec[key] = list(spec.get(key) or []) + copy.deepcopy(items)
    # Empty optional lists are spec errors; an emptied list means "none".
    for key in _LIST_KEYS[1:]:
        if key in spec and not spec[key]:
            del spec[key]
    spec["elements"] = [el for el in spec.get("elements") or []
                        if not (isinstance(el, dict) and "place" in el
                                and all(p is None for p in el["place"]))]
    return spec


def roughen(spec):
    """Drop the polish: glyphs and zone arrows/notches."""
    spec.pop("glyphs", None)
    for z in spec.get("zones") or []:
        z.pop("arrows", None)
        z.pop("notches", None)
    return spec


# ---------------------------------------------------------------------------
# Overlay helpers (for overlay modules)
# ---------------------------------------------------------------------------

def find(spec, name):
    """The element dict named `name` in a spec dict (row/place items
    included), or None. For overlay modules: find(spec, "SCREEN")["rect"]."""
    for _i, _j, item in _slots(spec):
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return None


def _load_overlay(path):
    spec = importlib.util.spec_from_file_location("panel_overlay", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["variants"] = sys.modules[__name__]   # so the overlay can `import variants`
    spec.loader.exec_module(mod)
    if not callable(getattr(mod, "overlay", None)):
        raise VariantError(f"overlay {path}: must define overlay(spec) -> SVG fragment")
    return mod.overlay


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render(spec_dict, base_dir, theme_path, library, overlay, tmpdir, k):
    """(svg_text_or_None, warnings, errors) for one variant."""
    try:
        spec = parse_spec(copy.deepcopy(spec_dict), base_dir)
        report, svg = panelgen._run_pipeline(spec, f"variant {k}", theme_path)
    except panelgen._EXPECTED_ERRORS as e:
        return None, [], [str(e)]
    if svg is None:
        return None, list(report.warnings), list(report.errors)
    path = os.path.join(tmpdir, f"{k:02d}.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    if library and os.path.isdir(library):
        svg, missing = preview.build_preview(path, library)
        if missing:
            report.warnings.append("no ComponentLibrary art for: "
                                   + ", ".join(sorted(set(missing))))
    if overlay is not None:
        try:
            frag = overlay(copy.deepcopy(spec_dict))
        except Exception as e:   # an overlay bug shouldn't sink the page
            report.warnings.append(f"overlay failed: {type(e).__name__}: {e}")
        else:
            i = svg.rindex("</svg>")
            svg = svg[:i] + frag + "\n" + svg[i:]
    return svg, list(report.warnings), []


def _crop(svg, crop):
    x, y, w, h = crop
    head_end = svg.index(">", svg.index("<svg")) + 1
    head = svg[:head_end]
    head = re.sub(r'viewBox="[^"]*"', f'viewBox="{x} {y} {w} {h}"', head, count=1)
    head = re.sub(r'width="[^"]*"', f'width="{w}mm"', head, count=1)
    head = re.sub(r'height="[^"]*"', f'height="{h}mm"', head, count=1)
    return head + svg[head_end:]


def _uri(svg):
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


_CSS = """
:root { color-scheme: dark; --bg: #2b2b2b; --card: #353535; --ink: #e8e8e8; --muted: #a8a8a8;
        --warn: #e0b04a; --err: #ff6b6b; }
body { margin: 0; background: var(--bg); color: var(--ink);
       font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif; }
main { padding: 20px 24px 40px; }
h1 { font-size: 20px; margin: 0 0 4px; }
.sub { color: var(--muted); margin: 0 0 18px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--cardw), 1fr)); gap: 16px; }
.card { background: var(--card); border-radius: 8px; padding: 12px; }
.card header { display: flex; gap: 8px; align-items: baseline; margin-bottom: 8px; }
.card .n { color: var(--muted); font-variant-numeric: tabular-nums; }
.card h2 { font-size: 15px; margin: 0; }
.card .tag { margin-left: auto; color: var(--muted); font-size: 12px; }
.card img { display: block; width: 100%; height: auto; cursor: zoom-in; background: #3d3d3d; }
.card p { margin: 8px 0 0; }
.card .warn { color: var(--warn); font-size: 12px; white-space: pre-wrap; }
.card .err { color: var(--err); white-space: pre-wrap; }
details { margin-top: 8px; color: var(--muted); font-size: 12px; }
details pre { white-space: pre-wrap; margin: 4px 0 0; }
.later { margin-top: 28px; color: var(--muted); }
.later h2 { font-size: 15px; color: var(--ink); }
#box { position: fixed; inset: 0; background: rgba(0,0,0,.85); display: none;
       align-items: center; justify-content: center; cursor: zoom-out; }
#box.on { display: flex; }
#box img { height: 96vh; width: auto; max-width: 96vw; object-fit: contain; background: #3d3d3d; }
"""

_JS = """
const box = document.getElementById('box'), big = box.querySelector('img');
document.querySelectorAll('.card img').forEach(img => img.addEventListener('click', () => {
  big.src = img.dataset.full; box.classList.add('on'); }));
box.addEventListener('click', () => box.classList.remove('on'));
document.addEventListener('keydown', e => { if (e.key === 'Escape') box.classList.remove('on'); });
"""


def _card(k, v, svg, warnings, errors, crop, rough):
    e = html.escape
    parts = [f'<section class="card"><header><span class="n">{k:02d}</span>'
             f'<h2>{e(v["name"])}</h2>' + ('<span class="tag">rough</span>' if rough else '')
             + '</header>']
    if svg is not None:
        shown = _crop(svg, crop) if crop else svg
        parts.append(f'<img src="{_uri(shown)}" data-full="{_uri(svg)}" alt="{e(v["name"])}">')
    if v.get("note"):
        parts.append(f'<p>{e(v["note"])}</p>')
    if errors:
        parts.append('<p class="err">' + e("\n".join(errors)) + '</p>')
    if warnings:
        parts.append('<p class="warn">' + e("\n".join(warnings)) + '</p>')
    ops = {key: v[key] for key in ("set", "edit", "remove", "add") if v.get(key)}
    if ops:
        parts.append('<details><summary>Changes</summary><pre>'
                     + e(yaml.safe_dump(ops, sort_keys=False, allow_unicode=True))
                     + '</pre></details>')
    parts.append('</section>')
    return "".join(parts)


def _check_crop(crop, ctx):
    if crop is not None and (not isinstance(crop, list) or len(crop) != 4
                             or not all(isinstance(n, (int, float)) for n in crop)):
        raise VariantError(f"{ctx}: must be [x, y, w, h] in mm, or null")
    return crop


def build_page(variants_path, theme_path=None, library=None):
    """The comparison page's HTML, and a list of (name, errors) for variants
    that didn't build."""
    with open(variants_path) as f:
        doc = yaml.safe_load(f)
    if not isinstance(doc, dict):
        raise VariantError(f"{variants_path}: must be a YAML mapping")
    _reject_unknown(doc, _FILE_KEYS, variants_path)
    here = os.path.dirname(os.path.abspath(variants_path))
    if "base" not in doc:
        raise VariantError(f"{variants_path}: 'base' (the spec to vary) is required")
    base_path = os.path.normpath(os.path.join(here, doc["base"]))
    with open(base_path) as f:
        base = yaml.safe_load(f)
    base_dir = os.path.dirname(base_path)

    variants = list(doc.get("variants") or [])
    for n, v in enumerate(variants, 1):
        if not isinstance(v, dict) or not v.get("name"):
            raise VariantError(f"variant {n}: must be a mapping with a 'name'")
        _reject_unknown(v, _VARIANT_KEYS, f"variant {n} ({v['name']})")
    if doc.get("include_base", True):
        variants.insert(0, {"name": "Current", "note": f"The base spec, {doc['base']}, unedited."})
    if not variants:
        raise VariantError(f"{variants_path}: no variants")

    crop = _check_crop(doc.get("crop"), "crop")
    overlay = _load_overlay(os.path.join(here, doc["overlay"])) if doc.get("overlay") else None
    page_rough = bool(doc.get("rough", False))

    cards, failed = [], []
    with tempfile.TemporaryDirectory() as tmpdir:
        for k, v in enumerate(variants, 0 if doc.get("include_base", True) else 1):
            rough = bool(v.get("rough", page_rough))
            v_crop = _check_crop(v["crop"], f"{v['name']}: crop") if "crop" in v else crop
            try:
                spec = apply_variant(base, v)
                if rough:
                    roughen(spec)
            except VariantError as e:
                svg, warnings, errors = None, [], [str(e)]
            else:
                svg, warnings, errors = _render(spec, base_dir, theme_path, library,
                                                None if rough else overlay, tmpdir, k)
            if errors:
                failed.append((v["name"], errors))
            cards.append(_card(k, v, svg, warnings, errors, v_crop, rough))

    # Card width: wide enough to read a cropped region or a whole panel.
    aspect = (crop[2] / crop[3]) if crop else (base.get("hp", 10) * 5.08 / 128.5)
    cardw = max(220, min(520, round(380 * aspect)))
    e = html.escape
    title = doc.get("title") or os.path.splitext(os.path.basename(variants_path))[0]
    later = doc.get("later") or []
    page = [
        '<!doctype html><html lang="en"><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>{e(title)}</title><style>{_CSS}</style>',
        f'<body style="--cardw:{cardw}px"><main><h1>{e(title)}</h1>',
        f'<p class="sub">{e(doc["about"])}</p>' if doc.get("about") else '<p class="sub"></p>',
        '<div class="grid">', *cards, '</div>',
    ]
    if later:
        page.append('<section class="later"><h2>Later</h2><ul>'
                    + "".join(f"<li>{e(str(x))}</li>" for x in later) + '</ul></section>')
    page.append(f'</main><div id="box"><img alt=""></div><script>{_JS}</script></body></html>')
    return "\n".join(page), failed


def _build_parser():
    p = argparse.ArgumentParser(description="Build variants of a panel spec onto one comparison page.")
    p.add_argument("variants", help="variants YAML file (see this script's docstring)")
    p.add_argument("--out", default=None,
                   help="output HTML path (default: the variants file with .html)")
    p.add_argument("--open", action="store_true", help="open the page in a browser")
    p.add_argument("--theme", default=None, help="theme YAML file, as panelgen.py --theme")
    p.add_argument("--library",
                   default=os.environ.get("VCV_COMPONENT_LIBRARY", preview.default_library()),
                   help="VCV ComponentLibrary dir (default: $VCV_COMPONENT_LIBRARY or "
                        "a conventional install location)")
    return p


def main(argv=None):
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    out = args.out or os.path.splitext(args.variants)[0] + ".html"
    try:
        panelgen._check_output_location(out)
        page, failed = build_page(args.variants, args.theme, args.library)
    except (VariantError, panelgen.OutputLocationError) + panelgen._EXPECTED_ERRORS as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if not args.library or not os.path.isdir(args.library):
        print(f"note: ComponentLibrary not found at {args.library!r}; cards show the bare panel",
              file=sys.stderr)
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Wrote {out}")
    for name, errors in failed:
        print(f"WARNING: variant {name!r} did not build: {errors[0]}", file=sys.stderr)
    if args.open:
        webbrowser.open("file://" + os.path.abspath(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
