"""Component size database: true drawn dimensions (mm) for VCV Rack widget
classes, used by later overlap checking and for widget defaults (which
concrete widget class to draw for a param/input/output/light control that
doesn't name one explicitly).

Sizes live in components.yaml (repo root, beside this module) rather than in
code, since they come from measuring the installed Rack ComponentLibrary's
SVG assets (see tools/measure_components.py) and are data, not logic.
"""
import dataclasses
import os

import yaml

_DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "components.yaml")


@dataclasses.dataclass(frozen=True)
class WidgetSize:
    """The true drawn size of a widget class, in mm.

    shape is "circle" (use d, the diameter) or "rect" (use w and h).
    """
    shape: str
    d: float | None = None
    w: float | None = None
    h: float | None = None


def _strip_template(widget_class):
    """"MediumLight<RedLight>" -> "MediumLight". VCV widget classes are
    sometimes named with a C++-style template argument for the light/tint
    color; the size database only cares about the base widget shape."""
    i = widget_class.find("<")
    return widget_class if i == -1 else widget_class[:i]


class ComponentDB:
    """Looks up WidgetSize by widget class name, and default widget class by
    control kind (param/input/output/light)."""

    def __init__(self, sizes, aliases, defaults):
        self._sizes = sizes      # dict[str, WidgetSize], keyed by canonical class name
        self._aliases = aliases  # dict[str, str] needle -> canonical class name,
                                  # for substring containment fallback (subclasses)
        self._defaults = defaults  # dict[str, str] kind -> widget class name

    def size_for(self, widget_class):
        """WidgetSize for widget_class, or None if unknown.

        Match order: exact name; then with any <Template> argument stripped;
        then longest-substring containment match against known aliases (so
        e.g. "RoundSmallBlackSnapKnob" resolves via the "RoundSmallBlack"
        alias to RoundSmallBlackKnob's size) -- same technique v1 preview.py's
        CLASS_ASSETS lookup uses for widget subclasses.
        """
        if widget_class in self._sizes:
            return self._sizes[widget_class]

        stripped = _strip_template(widget_class)
        if stripped in self._sizes:
            return self._sizes[stripped]

        best_needle, best_canonical = None, None
        for needle, canonical in self._aliases.items():
            if needle in stripped and (best_needle is None or len(needle) > len(best_needle)):
                best_needle, best_canonical = needle, canonical
        if best_canonical is not None:
            return self._sizes.get(best_canonical)
        return None

    def default_widget(self, kind):
        """Default widget class name for a control kind ("param", "input",
        "output", "light"), or None if there's no default for that kind."""
        return self._defaults.get(kind)


def load_component_db(path=None):
    """Load a ComponentDB from a components.yaml file. Defaults to
    components.yaml beside this module."""
    path = path or _DEFAULT_PATH
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    sizes = {}
    for name, spec in (data.get("components") or {}).items():
        sizes[name] = WidgetSize(
            shape=spec["shape"],
            d=spec.get("d"),
            w=spec.get("w"),
            h=spec.get("h"),
        )

    aliases = {}
    for canonical, needles in (data.get("aliases") or {}).items():
        for needle in needles:
            aliases[needle] = canonical

    defaults = data.get("defaults") or {}

    return ComponentDB(sizes, aliases, defaults)
