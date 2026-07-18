from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen


class TextRenderer:
    def __init__(self, font_path, font_number=0):
        # font_number selects a face inside a .ttc collection (e.g. Futura.ttc);
        # 0 is also valid for a plain single-font .ttf.
        self.font = TTFont(font_path, fontNumber=font_number)
        self.glyphset = self.font.getGlyphSet()
        self.upm = self.font["head"].unitsPerEm
        self.cmap = self.font.getBestCmap()
        self.hmtx = self.font["hmtx"]
        self.fallback_glyph = self.cmap.get(ord(" "))
        if self.fallback_glyph is None:
            self.fallback_glyph = self.font.getGlyphOrder()[0]  # .notdef, always present

    def _glyph_name(self, ch):
        return self.cmap.get(ord(ch), self.fallback_glyph)

    def cap_height(self, size_mm):
        """Cap height in mm at the given size; falls back to 0.7 em when the
        font carries no OS/2 sCapHeight."""
        os2 = self.font.get("OS/2")
        cap = getattr(os2, "sCapHeight", 0) if os2 else 0
        if not cap:
            cap = 0.7 * self.upm
        return cap / self.upm * size_mm

    def text_width(self, text, size_mm, tracking_mm=0.0, kern_mm=None):
        """Advance width of `text` at `size_mm`. `tracking_mm` adds that many mm
        of extra letter-spacing after every glyph (matching the way SVG
        `letter-spacing` widens a run), so the width stays consistent with what
        text_to_path_d lays down. `kern_mm`, if given, is a per-glyph list of
        leading offsets in mm (kern_mm[i] inserted before glyph i, kern_mm[0]
        normally 0) — per-pair kerning; its sum widens/narrows the run."""
        scale = size_mm / self.upm
        total = 0.0
        for ch in text:
            gn = self._glyph_name(ch)
            total += self.hmtx[gn][0]
        width = total * scale + tracking_mm * len(text)
        if kern_mm:
            width += sum(kern_mm)
        return width

    def text_to_path_d(self, text, x, y, size_mm, anchor="middle", tracking_mm=0.0,
                       kern_mm=None):
        if not text or not text.strip():
            return ""
        scale = size_mm / self.upm
        if anchor == "middle":
            x = x - self.text_width(text, size_mm, tracking_mm, kern_mm) / 2.0
        # Glyph space is y-up; SVG is y-down. Flip y, place baseline at y.
        pen_x_mm = 0.0
        commands = []
        for i, ch in enumerate(text):
            if kern_mm:
                pen_x_mm += kern_mm[i]  # per-pair leading offset before this glyph
            gn = self._glyph_name(ch)
            adv = self.hmtx[gn][0]
            spen = SVGPathPen(self.glyphset)
            # transform: (scale, 0, 0, -scale, x + pen_x_mm, y)
            tpen = TransformPen(spen, (scale, 0, 0, -scale, x + pen_x_mm, y))
            self.glyphset[gn].draw(tpen)
            cmds = spen.getCommands()
            if cmds:
                commands.append(cmds)
            pen_x_mm += adv * scale + tracking_mm
        return " ".join(commands)
