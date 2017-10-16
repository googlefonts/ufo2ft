from __future__ import (
    print_function, division, absolute_import, unicode_literals)

from ufo2ft.filters import BaseFilter, logger
from booleanOperations import union, BooleanOperationsError


class RemoveOverlapsFilter(BaseFilter):

    def filter(self, glyph, glyphSet=None):
        if not len(glyph):
            return False

        contours = list(glyph)
        glyph.clearContours()
        try:
            union(contours, glyph.getPointPen())
        except BooleanOperationsError:
            logger.error("Failed to remove overlaps for %s",
                         glyph.name)
            raise
        return True
