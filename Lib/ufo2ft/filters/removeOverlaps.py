from __future__ import (
    print_function, division, absolute_import, unicode_literals)

from ufo2ft.filters import BaseFilter
from booleanOperations import union, BooleanOperationsError

import logging


logger = logging.getLogger(__name__)


class RemoveOverlapsFilter(BaseFilter):

    def filter(self, glyph):
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
