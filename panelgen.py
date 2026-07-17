"""CLI: turn a spec YAML into a panel SVG.

Pipeline: load_spec -> resolve_theme (file layer + spec's inline layer) ->
build_font_index (once) -> resolve fonts/renderers (v1 panel_gen._render_svg's
recipe: one TextRenderer for the base font stack, a second only if the title
font stack resolves to a different face) -> resolve -> run_checks -> (bounds
errors abort before writing) -> build_svg -> validate_svg -> write.

Two module-level entry points sit under the CLI so tests can drive the
pipeline directly without subprocessing:

- generate(spec_path, out_path, theme_path=None) -> checks.Report
  Runs the full pipeline and writes out_path, but only when the resulting
  Report has no errors (a spec with an off-panel element is validated and
  reported, not written). Raises for anything that keeps the spec from even
  being built: SpecError, ThemeError, ResolveError, ValidationError,
  OutputLocationError, OSError.
- check(spec_path, theme_path=None) -> checks.Report
  The same pipeline (through build_svg + validate_svg) but never writes
  anything; used for --check. Raises the same set of errors generate() does.

Report.errors is a check failure (bounds overhang, duplicate name, ...), not
an exception — main() turns a non-empty errors list into exit code 1 and
prints each entry prefixed "ERROR: "; Report.warnings (suppressible overlaps)
are printed prefixed "WARNING: " but do not affect the exit code.
"""
import argparse
import os
import sys
import webbrowser

import yaml

import preview
from checks import run_checks
from components import load_component_db
from fontresolve import build_font_index, resolve_font_stack
from glyphs import TextRenderer
from resolve import resolve, ResolveError
from spec import load_spec, SpecError
from svgdoc import build_svg
from theme import resolve_theme, theme_from_mapping, load_theme_file, ThemeError
from validate import validate_svg, ValidationError

__version__ = "2.0.0"

# --theme absent + this file present -> read-only default theme layer for
# this run. Never touched unless both conditions hold, so tests never read
# the user's real config.
#
# PANELGEN_THEME_FILE, if set in the environment, replaces the conventional
# path below at import time. This exists so subprocess-based tests (which
# can't reach across the process boundary to monkeypatch this module's
# attribute the way in-process tests do) can still point the "conventional"
# theme lookup at a path that doesn't exist, instead of accidentally reading
# the real ~/.config/vcv-panel-gen/theme.yaml on the machine running the
# tests. When unset, behavior is unchanged.
CONVENTIONAL_THEME = os.environ.get("PANELGEN_THEME_FILE") or os.path.expanduser(
    "~/.config/vcv-panel-gen/theme.yaml")

TOOL_ROOT = os.path.dirname(os.path.abspath(__file__))

_EXPECTED_ERRORS = (SpecError, ThemeError, ResolveError, ValidationError,
                     OSError, yaml.YAMLError)


class OutputLocationError(Exception):
    pass


def _check_output_location(out_path):
    """Guard: refuse writes inside the tool checkout — a module's panel
    belongs in the module's own repo, not in vcv-panel-gen-redux itself.
    Anything outside the checkout (including a system temp directory, so
    pytest's tmp_path and quick demos still work) is allowed. The path is
    resolved to its real path before comparing so a symlink can't defeat the
    check."""
    resolved = os.path.realpath(os.path.abspath(out_path))

    try:
        inside_tool = os.path.commonpath([resolved, TOOL_ROOT]) == TOOL_ROOT
    except ValueError:
        # Different drive (Windows) or otherwise no common path: cannot be
        # inside the tool root.
        inside_tool = False
    if inside_tool:
        raise OutputLocationError(
            f"refusing to write {out_path} inside vcv-panel-gen-redux — a "
            f"module's panel belongs in the module's own repo; pass --out "
            f"under that repo (or a temp directory for a demo)")


def _load_theme_layer(theme_path):
    # --theme PATH replaces the conventional file for this run (read-only).
    if theme_path is not None:
        return load_theme_file(theme_path)
    if os.path.exists(CONVENTIONAL_THEME):
        return load_theme_file(CONVENTIONAL_THEME)
    return None


def _build_renderers(theme):
    """One font-index scan shared by both the base and title font stacks
    (the expensive part); a second TextRenderer only when the title stack
    resolves to a different face — matches v1 panel_gen._render_svg."""
    font_index = build_font_index()
    base_path, base_number = resolve_font_stack(theme.font, index=font_index)
    tr = TextRenderer(base_path, base_number)

    title_families = theme.title_font or theme.font
    title_path, title_number = resolve_font_stack(title_families, index=font_index)
    if (title_path, title_number) == (base_path, base_number):
        title_tr = tr
    else:
        title_tr = TextRenderer(title_path, title_number)
    return tr, title_tr


def _run_pipeline(spec, spec_path, theme_path):
    """Shared spine of generate()/check(): resolve theme + fonts, resolve the
    layout, run checks, and (only if the layout has no check errors) build
    and validate the SVG. Returns (report, svg_or_None) — svg is None when
    report.errors is non-empty, since v2 aborts before building/validating
    output for a layout that doesn't pass its own bounds checks."""
    file_partial = _load_theme_layer(theme_path)
    inline_partial = (theme_from_mapping(spec.theme_mapping, f"spec {spec_path}")
                       if spec.theme_mapping is not None else None)
    theme = resolve_theme(file_partial, inline_partial)

    tr, title_tr = _build_renderers(theme)
    db = load_component_db()

    lay = resolve(spec, theme, db, tr, title_tr)
    report = run_checks(lay, spec, db, tr, title_tr)
    if report.errors:
        return report, None

    svg = build_svg(lay, theme, tr, title_tr)
    validate_svg(svg)
    return report, svg


def generate(spec_path, out_path, theme_path=None):
    spec = load_spec(spec_path)
    _check_output_location(out_path)  # fail fast, before any rendering work

    report, svg = _run_pipeline(spec, spec_path, theme_path)
    if svg is not None:
        out_dir = os.path.dirname(os.path.abspath(out_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(out_path, "w") as f:
            f.write(svg)
    return report


def check(spec_path, theme_path=None):
    """Validate a spec end-to-end (spec -> theme -> layout -> checks ->
    SVG -> validation) without writing anything."""
    spec = load_spec(spec_path)
    report, _svg = _run_pipeline(spec, spec_path, theme_path)
    return report


def _build_parser():
    p = argparse.ArgumentParser(description="Generate a VCV Rack panel SVG from a spec.")
    p.add_argument("--version", action="version",
                   version=f"vcv-panel-gen-redux {__version__}")
    p.add_argument("spec")
    p.add_argument("--out", default=None,
                   help="output SVG path (required unless --check)")
    p.add_argument("--theme", default=None,
                   help="theme YAML file to use instead of the conventional "
                        "~/.config/vcv-panel-gen/theme.yaml for this run")
    p.add_argument("--check", action="store_true",
                   help="validate the spec and its layout without writing any "
                        "file; exits nonzero with a message if it won't build")
    p.add_argument("--library",
                   default=os.environ.get("VCV_COMPONENT_LIBRARY", preview.default_library()),
                   help="VCV ComponentLibrary dir, used by --preview/--open "
                        "(default: $VCV_COMPONENT_LIBRARY or a conventional "
                        "install location)")
    p.add_argument("--preview", action="store_true",
                   help="after a successful generate, composite ComponentLibrary "
                        "art onto the written SVG, producing <out-stem>.preview.svg "
                        "and <out-stem>.preview.html beside --out")
    p.add_argument("--open", action="store_true",
                   help="like --preview, and additionally open the preview html "
                        "in a browser")
    return p


def _emit_preview(out_path, library, open_browser):
    """After a successful (non---check) generate(), composite the real VCV
    ComponentLibrary art onto the written SVG (preview.build_preview),
    writing <out-stem>.preview.svg and <out-stem>.preview.html beside
    out_path. When open_browser, additionally open the html in a browser
    (webbrowser module, as v1's preview.py main() does). A missing
    ComponentLibrary is a note, not a failure — the panel SVG is already
    written. Returns 0 always."""
    if not library or not os.path.isdir(library):
        print(f"note: ComponentLibrary not found at {library!r}; skipping "
              f"preview (set VCV_COMPONENT_LIBRARY or pass --library)",
              file=sys.stderr)
        return 0

    root, _ext = os.path.splitext(out_path)
    preview_svg_path = f"{root}.preview.svg"
    html_path = f"{root}.preview.html"
    svg, missing = preview.build_preview(out_path, library)
    with open(preview_svg_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Wrote {preview_svg_path}")
    if missing:
        uniq = sorted(set(missing))
        print(f"WARNING: no ComponentLibrary asset for {len(uniq)} class(es), "
              f"drew markers: {', '.join(uniq)}", file=sys.stderr)

    title = os.path.basename(root)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(preview.wrap_html(svg, title))
    print(f"Wrote {html_path}")

    if open_browser:
        webbrowser.open("file://" + os.path.abspath(html_path))

    return 0


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.check and args.out is None:
        parser.error("--out is required unless --check is given")

    try:
        if args.check:
            report = check(args.spec, theme_path=args.theme)
        else:
            report = generate(args.spec, args.out, theme_path=args.theme)
    except (OutputLocationError,) + _EXPECTED_ERRORS as e:
        # Expected failures (a bad spec, a theme file that won't parse, a
        # write location we refuse) carry their own explanation — print it,
        # not a traceback.
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    for w in report.warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    if report.errors:
        for e in report.errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if args.check:
        print(f"OK: {args.spec} builds (nothing written).")
        return 0

    print(f"Wrote {args.out}")
    if args.preview or args.open:
        rc = _emit_preview(args.out, args.library, open_browser=args.open)
        if rc:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
