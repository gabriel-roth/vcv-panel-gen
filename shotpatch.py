"""Read a Rack `.vcv` patch and pin its viewport onto one module.

A Rack 2 `.vcv` file is a Zstandard-compressed tar of an autosave directory:
`patch.json` plus a `modules/` tree of per-module state. To screenshot one
module from a patch we extract that tar into a throwaway autosave folder, then
rewrite `patch.json` so the target module is guaranteed on-screen: set the view
`zoom` to 1.0 and `gridOffset` (the grid coords at the viewport's top-left) to
just above-left of the module's own `pos`, parking it near the top-left corner
but inset enough that the toolbar's drop shadow clears its top edge. The tight
crop is still found by template matching (shotmatch), so this only has to make
the module *visible* — it does not have to be pixel-exact.

`derive_patch` is a pure dict->dict transform and is unit-tested without Rack;
the tar/zstd IO around it is thin.
"""
import copy
import io
import json
import os
import tarfile

import zstandard


class PatchError(Exception):
    """A patch could not be read, or the requested module isn't in it."""


def load_vcv(path):
    """Decompress a `.vcv` file and return its patch.json as a dict."""
    with open(path, "rb") as f:
        raw = zstandard.ZstdDecompressor().stream_reader(f).read()
    with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
        member = tf.extractfile("./patch.json")
        if member is None:
            raise PatchError(f"{path}: no patch.json inside the .vcv")
        return json.load(member)


def extract_vcv(path, dest_dir):
    """Extract a `.vcv`'s tar into ``dest_dir`` (an autosave folder).

    Leaves ``dest_dir/patch.json`` and ``dest_dir/modules/`` in place, ready for
    Rack to restore. Returns the patch dict (unmodified) for convenience.
    """
    os.makedirs(dest_dir, exist_ok=True)
    with open(path, "rb") as f:
        raw = zstandard.ZstdDecompressor().stream_reader(f).read()
    with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
        tf.extractall(dest_dir, filter="data")
    with open(os.path.join(dest_dir, "patch.json"), encoding="utf-8") as f:
        return json.load(f)


def find_module(patch, plugin, model, index=0):
    """Return the ``index``-th module in ``patch`` matching plugin+model.

    Raises PatchError with a helpful message when there is no such module (and
    lists what the patch does contain), or when ``index`` is out of range.
    """
    matches = [m for m in patch.get("modules", [])
               if m.get("plugin") == plugin and m.get("model") == model]
    if not matches:
        have = sorted({f"{m.get('plugin')}:{m.get('model')}"
                       for m in patch.get("modules", [])})
        raise PatchError(
            f"no module {plugin}:{model} in patch; it contains: "
            + (", ".join(have) if have else "(no modules)"))
    if index >= len(matches):
        raise PatchError(
            f"patch has {len(matches)} instance(s) of {plugin}:{model}; "
            f"--index {index} is out of range")
    return matches[index]


# Grid-unit gap left between the viewport corner and the module, so the
# toolbar's drop shadow (a dark band just under the toolbar) falls on empty rack
# above the module rather than on its top edge. The crop is template-matched, so
# the module only has to be fully visible, not exactly at the corner.
CORNER_MARGIN = (2.0, 0.5)  # (hp right, rows down)


def derive_patch(patch, plugin, model, index=0, zoom=1.0, margin=CORNER_MARGIN):
    """Return (new_patch, pos): a copy pinned so the target module is visible.

    Sets the view ``zoom`` and moves ``gridOffset`` so the module sits just
    inside the viewport's top-left — inset by ``margin`` (hp, rows) so the
    toolbar's drop shadow doesn't darken its top edge. ``pos`` is returned (grid
    units) for the caller's records. Does not mutate ``patch``.
    """
    module = find_module(patch, plugin, model, index)
    pos = list(module["pos"])
    mx, my = margin
    out = copy.deepcopy(patch)
    out["zoom"] = float(zoom)
    out["gridOffset"] = [float(pos[0]) - mx, float(pos[1]) - my]
    return out, pos


def write_patch_json(patch, autosave_dir):
    """Overwrite ``autosave_dir/patch.json`` with ``patch``."""
    with open(os.path.join(autosave_dir, "patch.json"), "w",
              encoding="utf-8") as f:
        json.dump(patch, f)
