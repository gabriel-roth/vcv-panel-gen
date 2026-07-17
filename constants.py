import math

import fontresolve

HP_MM = 5.08
PANEL_H_MM = 128.5
MOUNT_INSET_X = 7.5
MOUNT_Y_TOP = 3.0
MOUNT_Y_BOTTOM = 125.5
# Footprint radius (mm) of the round mounting-screw head, centered on each
# mounting hole — larger than the 1.6mm drilled-hole marker but inside the
# ~5.08mm (1 HP) screw-widget box. Used to check that the title clears the two
# top screws (which would otherwise hide it on narrow panels).
SCREW_RADIUS_MM = 2.0
SIDE_MARGIN_MM = 8.0
TITLE_BAND_MM = 10.0
LABEL_FONT_MM = 3.0
TITLE_FONT_MM = 5.0

# Value ring: labels around a stepped knob, one per snap position. Rack's
# round knobs sweep -0.83π..+0.83π (Rack componentlibrary.hpp), so the ring
# spans that arc; nothing lands at the bottom for even position counts.
KNOB_SWEEP_RAD = 0.83 * math.pi
VALUE_RING_GAP_MM = 0.65  # gap between the drawn knob edge and label boxes
VALUE_FONT_MM = 1.8       # value-label size (control labels are LABEL_FONT_MM)
VALUE_TEXT_MIX = 0.55  # value-ring label color: this share of the text color, rest background

CONNECT_LINE_WIDTH = 0.3     # width of the vertical connecting bar (mm)
CONNECT_LINE_COLOR = "#808080"

COLORS = {
    "param": "#ff0000",
    "input": "#00ff00",
    "output": "#0000ff",
    "light": "#ff00ff",
    "widget": "#ffff00",
}

# Theme defaults. The default font is the bundled DejaVu Sans so output is
# reproducible on any machine out of the box; users who want a different face
# (e.g. Futura) set it in a theme file. Background and casing reproduce the
# tool's original behavior.
DEFAULT_BACKGROUND = "#e8e8e8"
DEFAULT_FONT_STACK = ["DejaVu Sans"]
DEFAULT_CASING = "preserve"
DEFAULT_SCREWS = "light"

# Mounting-screw head fill by theme.screws mode. "light" is VCV's silver
# ScrewSilver look (the tool's original, default); "dark" reads as a charcoal
# screw head for panels on dark backgrounds.
SCREW_COLORS = {"light": "#c0c0c0", "dark": "#333333", "none": None}

# Convenience handle for a guaranteed-present font, used by tests and any caller
# that just wants "a font" without resolving a theme. Points at the bundled
# DejaVu deliberately: the real pipeline resolves fonts from theme.font via
# fontresolve, so this must NOT trigger a full system-font scan at import time
# (constants is imported by nearly every module and test).
FONT_PATH, FONT_INDEX = fontresolve.BUNDLED_FONT, 0
