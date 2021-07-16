from ufo2ft.filters.transformations import TransformationsFilter
from ufo2ft.filters import BaseFilter
from fontTools.misc.transform import Identity, Transform
import logging

log = logging.getLogger(__name__)


class OptimizeAnchorsFilter(TransformationsFilter):
    def set_context(self, font, glyphSet):
        self.context = BaseFilter.set_context(self, font, glyphSet)

        self.context.component_use = {}
        for g in font.layers["public.default"]:
            for comp in g.components:
                self.context.component_use[comp.baseGlyph] = True

        return self.context


    def filter(self, glyph):
        if not any(a.name.startswith("_") for a in glyph.anchors):
            # We're a base!
            return False

        # Are we a spacing mark?
        if glyph.width != 0:
            return False

       # Are we anywhere used as a component?
        if glyph.name in self.context.component_use:
            return False

        # Also skip over marks which are deliberately positioned over the
        # previous glyphs
        if len(glyph.components) or glyph.getBounds().xMax < 0:
            return False

        # We are a mark glyph with (at least) one attachment point.
        theanchor = glyph.anchors[0]
        self.context.matrix = Identity.translate(-theanchor.x, -theanchor.y)
        log.info(
            "Transforming glyph %s to zero anchor %s: %s"
            % (glyph.name, theanchor.name, self.context.matrix)
        )
        return super().filter(glyph)
