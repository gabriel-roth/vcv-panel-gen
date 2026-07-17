import os
import sys
from fontTools.ttLib import TTFont, TTCollection

BUNDLED_FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "fonts", "DejaVuSans.ttf")

_EXTS = (".ttf", ".otf", ".ttc")


def _font_dirs():
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return ["/System/Library/Fonts",
                "/System/Library/Fonts/Supplemental",
                "/Library/Fonts",
                os.path.join(home, "Library", "Fonts")]
    if sys.platform.startswith("win"):
        dirs = [r"C:\Windows\Fonts"]
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
        return dirs
    return ["/usr/share/fonts", "/usr/local/share/fonts",
            os.path.join(home, ".fonts"),
            os.path.join(home, ".local", "share", "fonts")]


def _iter_font_files(dirs):
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for fn in files:
                if fn.lower().endswith(_EXTS):
                    yield os.path.join(root, fn)


def _family_names(ttfont):
    names = set()
    try:
        name_table = ttfont["name"]
    except KeyError:
        return names
    for rec in name_table.names:
        if rec.nameID in (1, 16):  # family, typographic family
            try:
                names.add(str(rec).strip().lower())
            except Exception:
                pass
    return names


def build_font_index(dirs=None):
    """Map lowercased family name -> (path, font_number). First seen wins."""
    dirs = dirs if dirs is not None else _font_dirs()
    index = {}
    for path in _iter_font_files(dirs):
        try:
            if path.lower().endswith(".ttc"):
                coll = TTCollection(path, lazy=True)
                faces = list(enumerate(coll.fonts))
            else:
                faces = [(0, TTFont(path, fontNumber=0, lazy=True))]
        except Exception:
            continue
        for num, font in faces:
            for fam in _family_names(font):
                index.setdefault(fam, (path, num))
    return index


def resolve_font_stack(families, dirs=None, index=None):
    """First installed family in the stack, else bundled DejaVu Sans.

    Pass a prebuilt `index` (from build_font_index) when resolving several
    stacks in one run — the system-font scan is the expensive part."""
    if index is None:
        index = build_font_index(dirs)
    for fam in list(families) + ["DejaVu Sans"]:
        hit = index.get(fam.strip().lower())
        if hit is not None:
            return hit
    return BUNDLED_FONT, 0
