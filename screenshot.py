"""CLI: accurately cropped screenshots of a VCV Rack module.

Three ways to get a shot, all writing a tightly-cropped PNG to --out:

  screenshot.py default --plugin P --module M [--zoom Z] --out OUT.png
      The module in its default state. Rack renders each module to its own
      framebuffer and writes a natively-cropped PNG (its -t/--screenshot mode),
      so there is no crop arithmetic to get wrong. We isolate the target plugin
      in a throwaway user folder so only it (plus built-in Core) is rendered.

  screenshot.py patch --file P.vcv --plugin P --module M [--zoom Z] --out OUT.png
      The module as it appears in a saved patch, reflecting its live knob/screen
      state. We extract the patch into a throwaway autosave, pin the view so the
      module sits at the top-left corner (shotpatch), launch Rack, capture the
      window, and find + crop the module by template matching (shotmatch).

  screenshot.py live --plugin P --module M --out OUT.png
      The module in the Rack instance you already have open, without relaunching
      or touching its autosave. We capture its window and template-match the
      module wherever it currently sits.

Why template matching (see shotmatch): computing a module's on-screen rectangle
from Rack's scroll/zoom/Retina state is the arithmetic that drifted before. We
instead locate the module by its known default-state render and crop the matched
box, which needs none of those constants and is self-correcting. A match below a
confidence threshold is a loud error, never a silently-wrong crop.

macOS only (uses screencapture + osascript for window capture and geometry).
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time

import shotmatch
import shotpatch

__version__ = "1.0.0"


class ScreenshotError(Exception):
    """A screenshot could not be produced; the message explains why."""


# ---------------------------------------------------------------------------
# Environment discovery
# ---------------------------------------------------------------------------

RACK_APPS = [
    "/Applications/VCV Rack 2 Pro.app",
    "/Applications/VCV Rack 2 Free.app",
    "/Applications/VCV Rack 2.app",
]


def rack_binary(explicit=None):
    """Path to the Rack executable (--rack / $VCV_RACK_BIN override the search)."""
    cand = explicit or os.environ.get("VCV_RACK_BIN")
    if cand:
        if not os.path.isfile(cand):
            raise ScreenshotError(f"Rack binary not found at {cand!r}")
        return cand
    for app in RACK_APPS:
        binary = os.path.join(app, "Contents/MacOS/Rack")
        if os.path.isfile(binary):
            return binary
    raise ScreenshotError(
        "no VCV Rack app found in /Applications; pass --rack or set $VCV_RACK_BIN")


def plugins_dirname():
    """Rack's per-arch plugins folder name for this machine."""
    return "plugins-mac-arm64" if platform.machine() == "arm64" else "plugins-mac-x64"


def user_dir(explicit=None):
    """Rack's user folder ($RACK_USER_DIR / --user-dir override the default)."""
    return (explicit or os.environ.get("RACK_USER_DIR")
            or os.path.expanduser("~/Library/Application Support/Rack2"))


def installed_plugin_dir(plugin, udir):
    """Path to an installed plugin's folder, or raise listing what is present."""
    pdir = os.path.join(udir, plugins_dirname(), plugin)
    if not os.path.isdir(pdir):
        raise ScreenshotError(
            f"plugin {plugin!r} is not installed at {pdir!r}; install it in Rack "
            f"first, or pass --plugin-dir to point at a built plugin folder")
    return pdir


# ---------------------------------------------------------------------------
# (a) default-state render via Rack's own -t/--screenshot
# ---------------------------------------------------------------------------

def render_default(plugin, module, zoom, out_path, *, rack, udir, plugin_dir=None,
                   timeout=180):
    """Render one module in its default state to ``out_path`` (a PNG).

    Builds a throwaway user folder containing only the target plugin, runs
    ``Rack -u <tmp> --screenshot <zoom>`` (Rack writes a natively-cropped PNG per
    module), and copies out this module's PNG. Returns ``out_path``.

    Rack's --screenshot always renders the *light* panel (it ignores
    preferDarkPanels), so this output is always light. That is fine for the
    default-state screenshot and for use as a match template, because matching is
    on gradient magnitude (shotmatch), which holds across light/dark panels.
    """
    src_plugin = plugin_dir or installed_plugin_dir(plugin, udir)
    tmp = tempfile.mkdtemp(prefix="vcvshot-def-")
    try:
        pdir = os.path.join(tmp, plugins_dirname())
        os.makedirs(pdir)
        # copy (don't symlink) the one plugin in, so --screenshot only renders it
        # (+ Core). Copy, not symlink: a freshly built, ad-hoc *linker-signed*
        # dev plugin (e.g. one you're iterating on) is killed by AMFI when Rack
        # dlopens it through a symlink, but loads fine from a real copy.
        shutil.copytree(src_plugin, os.path.join(pdir, plugin))
        proc = subprocess.run(
            [rack, "-u", tmp, "--screenshot", str(zoom)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        shot = os.path.join(tmp, "screenshots", plugin, f"{module}.png")
        if not os.path.isfile(shot):
            out = (proc.stdout or b"").decode("utf-8", "replace")[-800:]
            if proc.returncode and proc.returncode < 0:
                raise ScreenshotError(
                    f"Rack crashed (signal {-proc.returncode}) while rendering "
                    f"{plugin}. If it's a plugin you just built, its dylib may be "
                    f"unsigned/misbuilt — check `codesign -v` on it. Rack said:\n{out}")
            raise ScreenshotError(
                f"Rack did not produce {plugin}/{module}.png (exit "
                f"{proc.returncode}). Check the plugin and module slugs. Rack "
                f"said:\n{out}")
        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
        shutil.copyfile(shot, out_path)
        return out_path
    except subprocess.TimeoutExpired:
        raise ScreenshotError(
            f"Rack --screenshot timed out after {timeout}s")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Window capture (macOS) + template-matched crop
# ---------------------------------------------------------------------------

def _osa(script):
    """Run an AppleScript, return stripped stdout (raises on osascript error)."""
    r = subprocess.run(["osascript", "-e", script],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        raise ScreenshotError(f"osascript failed: {r.stderr.strip()}")
    return r.stdout.strip()


def rack_running():
    """True if a Rack process currently exists."""
    out = _osa('tell application "System Events" to '
               '(name of processes) contains "Rack"')
    return out == "true"


def _proc_ref(pid):
    """An AppleScript process reference: a specific pid, or any process "Rack".

    Addressing by unix id matters when more than one Rack is open (e.g. `patch`
    launches its own instance while the user has Rack running) — "process Rack"
    would pick an arbitrary one.
    """
    if pid is not None:
        return f"(first process whose unix id is {int(pid)})"
    return 'process "Rack"'


def wait_for_window(pid=None, timeout=30.0, poll=0.5):
    """Wait until the Rack process has a front window; return (x, y, w, h) points."""
    ref = _proc_ref(pid)
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            out = _osa(f'tell application "System Events" to tell {ref} '
                       f'to get {{position, size}} of window 1')
        except ScreenshotError as e:
            last = str(e)
            time.sleep(poll)
            continue
        nums = [int(round(float(n))) for n in out.split(", ")]
        if len(nums) == 4 and nums[2] > 0 and nums[3] > 0:
            return tuple(nums)
        time.sleep(poll)
    raise ScreenshotError(
        f"Rack window did not appear within {timeout}s ({last})")


def activate_rack(pid=None):
    """Bring the Rack process to the front so nothing overlaps the capture."""
    _osa(f'tell application "System Events" to set frontmost of '
         f'{_proc_ref(pid)} to true')


def capture_window(bounds, out_png):
    """Capture the screen region ``bounds`` (x, y, w, h points) to ``out_png``."""
    x, y, w, h = bounds
    r = subprocess.run(
        ["screencapture", "-x", "-o", "-R", f"{x},{y},{w},{h}", out_png],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0 or not os.path.isfile(out_png):
        raise ScreenshotError(f"screencapture failed: {r.stderr.strip()}")


def _scale_candidates(hint):
    """A small set of template scales around ``hint`` (= viewZoom * backingScale)."""
    out = []
    for f in (1.0, 0.9, 1.1, 0.8, 1.25, 0.66, 1.5):
        out.append(hint * f)
    out += [1.0, 2.0]  # common backing scales, in case the hint is wrong
    return out


def matched_crop(window_png, template_png, out_path, *, scale_hint, min_score):
    """Locate the template in the window capture and crop it to ``out_path``.

    Returns the shotmatch.Match. Raises if the best match is below ``min_score``.
    """
    from PIL import Image

    window = shotmatch.to_gray(window_png)
    template = shotmatch.to_gray(template_png)
    match = shotmatch.locate(window, template, _scale_candidates(scale_hint))
    if match is None:
        raise ScreenshotError(
            "the module template does not fit in the window capture")
    if match.score < min_score:
        raise ScreenshotError(
            f"could not confidently locate the module (best match "
            f"{match.score:.2f} < {min_score:.2f}). Is it visible on screen and "
            f"not hidden behind a menu or another window?")
    img = Image.open(window_png)
    box = (match.x, match.y, match.x + match.w, match.y + match.h)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    img.crop(box).save(out_path)
    return match


def live_zoom_hint(udir):
    """Best-effort current view zoom from the running Rack's autosave (else 1.0)."""
    import json
    try:
        with open(os.path.join(udir, "autosave", "patch.json"),
                  encoding="utf-8") as f:
            return float(json.load(f).get("zoom", 1.0))
    except (OSError, ValueError):
        return 1.0


def _prepare_gui_user_dir(udir, plugin_slugs):
    """A throwaway user folder that loads ``plugin_slugs``, with a roomy window.

    Copies each referenced plugin from the real user folder (copy, not symlink,
    so freshly built ad-hoc linker-signed dev plugins load — see render_default),
    and copies the real settings.json with window geometry overridden, which also
    sidesteps first-run dialogs on a fresh folder. Plugins not found (e.g. Core,
    which is built in) are skipped; Rack marks any genuinely-missing module, but
    the target still renders.
    """
    import json
    tmp = tempfile.mkdtemp(prefix="vcvshot-gui-")
    real_plugins = os.path.join(udir, plugins_dirname())
    dst_plugins = os.path.join(tmp, plugins_dirname())
    os.makedirs(dst_plugins)
    for slug in sorted(set(plugin_slugs)):
        src = os.path.join(real_plugins, slug)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dst_plugins, slug))
    settings = {}
    real_settings = os.path.join(udir, "settings.json")
    if os.path.isfile(real_settings):
        try:
            with open(real_settings, encoding="utf-8") as f:
                settings = json.load(f)
        except (OSError, ValueError):
            settings = {}
    settings["windowMaximized"] = True
    settings["windowSize"] = [1680, 1050]
    settings["windowPos"] = [0, 0]
    settings["checkVersion"] = False
    with open(os.path.join(tmp, "settings.json"), "w", encoding="utf-8") as f:
        json.dump(settings, f)
    return tmp


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def cmd_default(args):
    rack = rack_binary(args.rack)
    udir = user_dir(args.user_dir)
    render_default(args.plugin, args.module, args.zoom, args.out,
                   rack=rack, udir=udir, plugin_dir=args.plugin_dir)
    print(f"Wrote {args.out}")
    return 0


def _capture_and_crop(bounds, template, args, *, scale_hint, pid=None):
    """Shared tail of patch/live: capture the window and matched-crop the module.

    ``template`` is a pre-rendered default-state PNG. It is rendered before this
    call (and before any window is captured) so the brief screenshot-mode Rack
    can never steal focus during the capture.
    """
    work = tempfile.mkdtemp(prefix="vcvshot-cap-")
    try:
        window = os.path.join(work, "window.png")
        activate_rack(pid)
        time.sleep(0.4)
        capture_window(bounds, window)
        match = matched_crop(window, template, args.out,
                             scale_hint=scale_hint, min_score=args.min_score)
        print(f"Wrote {args.out}  (match {match.score:.2f} at scale "
              f"{match.scale:.2f}, {match.w}x{match.h}px)")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def cmd_patch(args):
    rack = rack_binary(args.rack)
    udir = user_dir(args.user_dir)
    patch = shotpatch.load_vcv(args.file)
    # validate module is present before launching anything
    shotpatch.find_module(patch, args.plugin, args.module, args.index)

    plugin_slugs = {m.get("plugin") for m in patch.get("modules", [])}
    tmp = _prepare_gui_user_dir(udir, plugin_slugs)
    work = tempfile.mkdtemp(prefix="vcvshot-tpl-")
    proc = None
    try:
        # render the match template first, while nothing is being captured
        # (gradient matching handles the light-template vs dark-panel case)
        template = os.path.join(work, "template.png")
        render_default(args.plugin, args.module, 1, template, rack=rack,
                       udir=udir, plugin_dir=args.plugin_dir)

        autosave = os.path.join(tmp, "autosave")
        shotpatch.extract_vcv(args.file, autosave)
        derived, _pos = shotpatch.derive_patch(
            patch, args.plugin, args.module, args.index, zoom=args.zoom)
        shotpatch.write_patch_json(derived, autosave)

        proc = subprocess.Popen([rack, "-u", tmp],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        bounds = wait_for_window(pid=proc.pid, timeout=args.launch_timeout)
        time.sleep(args.settle)  # let panels finish drawing to their framebuffers
        # view zoom is pinned to args.zoom; backing scale unknown -> hint covers it
        return _capture_and_crop(bounds, template, args,
                                 scale_hint=args.zoom * 2.0, pid=proc.pid)
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


def cmd_live(args):
    rack = rack_binary(args.rack)
    udir = user_dir(args.user_dir)
    if not rack_running():
        raise ScreenshotError(
            "no running Rack found. Open your patch in Rack first, or use the "
            "'patch' command to screenshot from a .vcv file.")
    work = tempfile.mkdtemp(prefix="vcvshot-tpl-")
    try:
        template = os.path.join(work, "template.png")
        render_default(args.plugin, args.module, 1, template, rack=rack,
                       udir=udir, plugin_dir=args.plugin_dir)
        bounds = wait_for_window(timeout=10)
        hint = live_zoom_hint(udir) * 2.0  # * assumed Retina backing scale
        return _capture_and_crop(bounds, template, args, scale_hint=hint)
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _add_common(p, *, need_out=True):
    p.add_argument("--plugin", required=True, help="VCV plugin slug")
    p.add_argument("--module", required=True, help="VCV module (model) slug")
    p.add_argument("--out", required=need_out, help="output PNG path")
    p.add_argument("--plugin-dir", default=None,
                   help="a built plugin folder to use instead of the installed one")
    p.add_argument("--rack", default=None, help="path to the Rack binary")
    p.add_argument("--user-dir", default=None, help="Rack user folder")


def _build_parser():
    p = argparse.ArgumentParser(
        description="Accurately cropped screenshots of a VCV Rack module.")
    p.add_argument("--version", action="version",
                   version=f"vcv-screenshot {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("default", help="module in its default state")
    _add_common(d)
    d.add_argument("--zoom", type=float, default=1.0,
                   help="render zoom / output scale (default 1.0)")
    d.set_defaults(func=cmd_default)

    pa = sub.add_parser("patch", help="module as it appears in a .vcv patch")
    _add_common(pa)
    pa.add_argument("--file", required=True, help="the .vcv patch file")
    pa.add_argument("--index", type=int, default=0,
                    help="which instance, if the patch has duplicates (default 0)")
    pa.add_argument("--zoom", type=float, default=1.0,
                    help="pinned view zoom / output scale (default 1.0)")
    pa.add_argument("--min-score", type=float, default=0.5,
                    help="reject a crop below this match confidence (default 0.5)")
    pa.add_argument("--settle", type=float, default=2.5,
                    help="seconds to let panels draw before capture (default 2.5)")
    pa.add_argument("--launch-timeout", type=float, default=40.0,
                    help="seconds to wait for the Rack window (default 40)")
    pa.set_defaults(func=cmd_patch)

    li = sub.add_parser("live", help="module in the already-running Rack")
    _add_common(li)
    li.add_argument("--min-score", type=float, default=0.5,
                    help="reject a crop below this match confidence (default 0.5)")
    li.set_defaults(func=cmd_live)
    return p


def main(argv=None):
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    try:
        return args.func(args)
    except (ScreenshotError, shotpatch.PatchError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
