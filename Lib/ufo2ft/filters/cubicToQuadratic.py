from __future__ import (
    print_function, division, absolute_import, unicode_literals)

from ufo2ft.filters import BaseFilter
from cu2qu.ufo import DEFAULT_MAX_ERR
from cu2qu.pens import Cu2QuPointPen


class CubicToQuadraticFilter(BaseFilter):

    _kwargs = {
        'conversionError': None,
        'unitsPerEm': 1000,
        'reverseDirection': True,
    }

    def start(self):
        relativeError = self.conversionError or DEFAULT_MAX_ERR
        self.absoluteError = relativeError * self.unitsPerEm

    def filter(self, glyph, glyphSet=None):
        if not len(glyph):
            return False

        pen = Cu2QuPointPen(
            glyph.getPointPen(),
            self.absoluteError,
            reverse_direction=self.reverseDirection)
        contours = list(glyph)
        glyph.clearContours()
        for contour in contours:
            contour.drawPoints(pen)
        return True
