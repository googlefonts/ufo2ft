from ufo2ft.filters.transformations import TransformationsFilter
from fontTools.misc.transform import Identity, Transform
import logging

log = logging.getLogger(__name__)


class OptimizeAnchorsFilter(TransformationsFilter):
    def set_context(self, font, glyphSet):
        # Skip over transformations filter to base filter
        return super(TransformationsFilter, self).set_context(font, glyphSet)

    def filter(self, glyph):
        if len(glyph.anchors) == 0 or any(
            not (a.name.startswith("_")) for a in glyph.anchors
        ):
            # We're a base!
            return False

        # We are a mark glyph with (at least) one attachment point.
        theanchor = glyph.anchors[0]
        self.context.matrix = Identity.translate(-theanchor.x, -theanchor.y)
        log.warn(
            "Transforming glyph %s to zero anchor %s: %s"
            % (glyph.name, theanchor.name, self.context.matrix)
        )
        return super().filter(glyph)
