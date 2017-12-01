from __future__ import (
    print_function, division, absolute_import, unicode_literals)

from ufo2ft.filters import BaseFilter
from cu2qu.ufo import DEFAULT_MAX_ERR
from cu2qu.pens import Cu2QuPointPen

import logging


logger = logging.getLogger(__name__)


class CubicToQuadraticFilter(BaseFilter):

    _kwargs = {
        'conversionError': None,
        'reverseDirection': True,
    }

    def set_context(self, font, glyphSet):
        ctx = super(CubicToQuadraticFilter, self).set_context(font, glyphSet)

        relativeError = self.options.conversionError or DEFAULT_MAX_ERR
        ctx.absoluteError = relativeError * font.info.unitsPerEm

        ctx.stats = {}

        return ctx

    def __call__(self, font, glyphSet=None):
        if super(CubicToQuadraticFilter, self).__call__(font, glyphSet):
            stats = self.context.stats
            logger.info('New spline lengths: %s' % (', '.join(
                '%s: %d' % (l, stats[l]) for l in sorted(stats.keys()))))

    def filter(self, glyph):
        if not len(glyph):
            return False

        pen = Cu2QuPointPen(
            glyph.getPointPen(),
            self.context.absoluteError,
            reverse_direction=self.options.reverseDirection,
            stats=self.context.stats)
        contours = list(glyph)
        glyph.clearContours()
        for contour in contours:
            contour.drawPoints(pen)
        return True
