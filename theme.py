import re
from dataclasses import dataclass

import yaml

from constants import (DEFAULT_BACKGROUND, DEFAULT_FONT_STACK, DEFAULT_CASING,
                       DEFAULT_SCREWS, SCREW_COLORS, VALUE_TEXT_MIX)


@dataclass
class Theme:
    background: str | None = None
    font: list | None = None
    title_font: list | None = None
    casing: str | None = None
    text_color: str | None = None
    title_color: str | None = None
    screws: str | None = None
    value_color: str | None = None


DEFAULT_THEME = Theme(
    background=DEFAULT_BACKGROUND,
    font=list(DEFAULT_FONT_STACK),
    casing=DEFAULT_CASING,
    text_color=None,
    screws=DEFAULT_SCREWS,
)


def merge(base, override):
    def pick(attr):
        v = getattr(override, attr)
        return v if v is not None else getattr(base, attr)
    return Theme(background=pick("background"), font=pick("font"),
                 title_font=pick("title_font"), casing=pick("casing"),
                 text_color=pick("text_color"), title_color=pick("title_color"),
                 screws=pick("screws"), value_color=pick("value_color"))


def resolve_theme(file_partial=None, inline_partial=None):
    t = DEFAULT_THEME
    if file_partial is not None:
        t = merge(t, file_partial)
    if inline_partial is not None:
        t = merge(t, inline_partial)
    return t


class ThemeError(Exception):
    pass


CASING_MODES = ("upper", "lower", "title", "preserve")
SCREW_MODES = tuple(SCREW_COLORS)
_ALLOWED_FIELDS = {"background", "font", "title_font", "casing", "text_color",
                   "title_color", "screws", "value_color"}
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _validate_hex(value, fieldname, source):
    if not isinstance(value, str) or not _HEX_RE.match(value):
        raise ThemeError(
            f"{source}: '{fieldname}' must be a hex color like #rrggbb or #rgb "
            f"(got {value!r})")
    return value


def _validate_font_list(value, fieldname, source):
    if (not isinstance(value, list) or not value
            or not all(isinstance(x, str) and x.strip() for x in value)):
        raise ThemeError(
            f"{source}: '{fieldname}' must be a non-empty list of font family names "
            f"(got {value!r})")
    return value


def theme_from_mapping(data, source):
    if data is None:
        return Theme()
    if not isinstance(data, dict):
        raise ThemeError(f"{source}: theme must be a mapping (got {type(data).__name__})")
    unknown = set(data) - _ALLOWED_FIELDS
    if unknown:
        raise ThemeError(
            f"{source}: unknown theme field(s): {sorted(unknown)}; "
            f"valid: {sorted(_ALLOWED_FIELDS)}")

    bg = _validate_hex(data["background"], "background", source) if "background" in data else None
    tc = _validate_hex(data["text_color"], "text_color", source) if "text_color" in data else None
    tic = _validate_hex(data["title_color"], "title_color", source) if "title_color" in data else None
    vc = _validate_hex(data["value_color"], "value_color", source) if "value_color" in data else None

    casing = None
    if "casing" in data:
        casing = data["casing"]
        if casing not in CASING_MODES:
            raise ThemeError(
                f"{source}: 'casing' must be one of {', '.join(CASING_MODES)} "
                f"(got {casing!r})")

    screws = None
    if "screws" in data:
        screws = data["screws"]
        if screws not in SCREW_MODES:
            raise ThemeError(
                f"{source}: 'screws' must be one of {', '.join(SCREW_MODES)} "
                f"(got {screws!r})")

    font = _validate_font_list(data["font"], "font", source) if "font" in data else None
    title_font = (_validate_font_list(data["title_font"], "title_font", source)
                  if "title_font" in data else None)

    return Theme(background=bg, font=font, title_font=title_font,
                 casing=casing, text_color=tc, title_color=tic,
                 screws=screws, value_color=vc)


def load_theme_file(path):
    with open(path) as f:
        data = yaml.safe_load(f)
    return theme_from_mapping(data, f"theme file {path}")


def apply_casing(text, mode):
    if mode == "upper":
        return text.upper()
    if mode == "lower":
        return text.lower()
    if mode == "title":
        return text.title()
    return text  # preserve / unknown


def _hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def resolve_screw_color(theme):
    return SCREW_COLORS[theme.screws or DEFAULT_SCREWS]


def resolve_text_color(theme):
    if theme.text_color is not None:
        return theme.text_color
    r, g, b = _hex_to_rgb(theme.background)
    luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
    return "#000000" if luminance > 0.5 else "#ffffff"


def resolve_title_color(theme):
    """The module title's color: an explicit theme.title_color wins; otherwise
    it falls back to the resolved control-label color."""
    if theme.title_color is not None:
        return theme.title_color
    return resolve_text_color(theme)


def resolve_value_color(theme):
    """Value-ring labels draw quieter than control labels: an explicit
    theme.value_color wins; otherwise the resolved text color blended
    toward the background (VALUE_TEXT_MIX of the text color remains)."""
    if theme.value_color is not None:
        return theme.value_color
    t = _hex_to_rgb(resolve_text_color(theme))
    b = _hex_to_rgb(theme.background)
    return "#" + "".join(
        f"{round(tc * VALUE_TEXT_MIX + bc * (1.0 - VALUE_TEXT_MIX)):02x}"
        for tc, bc in zip(t, b))
