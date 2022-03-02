from statistics import mean
import logging
import math

from ufoLib2.objects import Glyph

from ufo2ft.featureCompiler import parseLayoutFeatures
from ufo2ft.featureWriters import ast
from ufo2ft.filters import BaseFilter
from ufo2ft.util import _GlyphSet, _LazyFontName

logger = logging.getLogger(__name__)
CIRCULAR_SUPERNESS = 0.551784777779014


def circle(pen, origin, radius):
    w = (origin[0] - radius, origin[1])
    n = (origin[0], origin[1] + radius)
    e = (origin[0] + radius, origin[1])
    s = (origin[0], origin[1] - radius)

    pen.moveTo(w)
    pen.curveTo(
        (w[0], w[1] + radius * CIRCULAR_SUPERNESS),
        (n[0] - radius * CIRCULAR_SUPERNESS, n[1]),
        n,
    )
    pen.curveTo(
        (n[0] + radius * CIRCULAR_SUPERNESS, n[1]),
        (e[0], e[1] + radius * CIRCULAR_SUPERNESS),
        e,
    )
    pen.curveTo(
        (e[0], e[1] - radius * CIRCULAR_SUPERNESS),
        (s[0] + radius * CIRCULAR_SUPERNESS, s[1]),
        s,
    )
    pen.curveTo(
        (s[0] - radius * CIRCULAR_SUPERNESS, s[1]),
        (w[0], w[1] - radius * CIRCULAR_SUPERNESS),
        w,
    )
    pen.closePath()


class DottedCircleFilter(BaseFilter):

    _kwargs = {"margin": 80, "sidebearing": 160, "dots": 12}

    def __call__(self, font, glyphSet=None):
        fontName = _LazyFontName(font)
        if glyphSet is not None and getattr(glyphSet, "name", None):
            logger.info("Running %s on %s-%s", self.name, fontName, glyphSet.name)
        else:
            logger.info("Running %s on %s", self.name, fontName)

        if glyphSet is None:
            glyphSet = _GlyphSet.from_layer(font)

        self.set_context(font, glyphSet)
        dotted_circle = self.check_dotted_circle(glyphSet)
        return self.check_dotted_circle_anchors(dotted_circle)

    def check_dotted_circle(self, glyphSet):
        font = self.context.font
        dotted_circle = [g for g in font.keys() if font[g].unicode == 0x25CC]
        if dotted_circle:
            logger.info("Found dotted circle glyph %s", dotted_circle)
            return dotted_circle[0]
        glyph = Glyph(name="uni25CC", unicodes=[0x25CC])
        pen = glyph.getPen()

        bigradius = (font.info.xHeight - 2 * self.options.margin) / 2
        littleradius = bigradius / 6
        left = self.options.sidebearing + littleradius
        right = self.options.sidebearing + bigradius * 2 - littleradius
        middleY = font.info.xHeight / 2
        middleX = (left + right) / 2
        subangle = 2 * math.pi / self.options.dots
        for t in range(self.options.dots):
            angle = t * subangle
            cx = middleX + bigradius * math.cos(angle)
            cy = middleY + bigradius * math.sin(angle)
            circle(pen, (cx, cy), littleradius)

        glyph.setRightMargin(self.options.sidebearing)
        font.addGlyph(glyph)
        glyphSet["uni25CC"] = glyph
        return "uni25CC"

    def check_dotted_circle_anchors(self, dotted_circle):
        font = self.context.font
        all_anchors = {}
        any_added = False
        for glyph in font:
            bounds = glyph.getBounds(font)
            if bounds:
                width = bounds.xMax
            else:
                width = glyph.width
            for anchor in glyph.anchors:
                if anchor.name.startswith("_"):
                    # We don't want their coordinates, just their names
                    # so we can match them with base anchors later.
                    all_anchors[anchor.name] = []
                    continue
                if not width:
                    continue
                x_percentage = anchor.x / width
                all_anchors.setdefault(anchor.name, []).append(
                    (glyph.name, x_percentage, anchor.y)
                )
        dsglyph = font[dotted_circle]
        dsanchors = set([a.name for a in dsglyph.anchors])
        for anchor, vals in all_anchors.items():
            # Skip existing anchors on the dotted-circle, and any anchors
            # which don't have a matching mark glyph.
            if anchor in dsanchors or f"_{anchor}" not in all_anchors:
                continue
            average_x = mean([v[1] for v in vals])
            average_y = mean([v[2] for v in vals])
            logger.debug(
                "Adding anchor %s to dotted circle glyph at %i,%i",
                anchor,
                dsglyph.width * average_x,
                average_y,
            )
            dsglyph.appendAnchor(
                {
                    "name": anchor,
                    "x": int(dsglyph.width * average_x),
                    "y": int(average_y),
                }
            )
            any_added = True
        if any_added:
            self.ensure_base(dotted_circle)
            return dotted_circle
        else:
            return []

    # We need to ensure the glyph is a base or else it won't feature
    # in the mark features writer. And if it previously had no anchors,
    # glyphsLib does not consider it a base.
    def ensure_base(self, dotted_circle):
        font = self.context.font
        feaFile = parseLayoutFeatures(font)
        if ast.findTable(feaFile, "GDEF") is None:
            return
        for st in feaFile.statements:
            if isinstance(st, ast.TableBlock) and st.name == "GDEF":
                for st in st.statements:
                    if isinstance(st, ast.GlyphClassDefStatement):
                        if (
                            st.baseGlyphs
                            and dotted_circle not in st.baseGlyphs.glyphSet()
                        ):
                            st.baseGlyphs.glyphs.append(dotted_circle)
        font.features.text = feaFile.asFea()
