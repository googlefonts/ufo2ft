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
        'unitsPerEm': 1000,
        'reverseDirection': True,
    }

    def start(self):
        relativeError = self.conversionError or DEFAULT_MAX_ERR
        self.absoluteError = relativeError * self.unitsPerEm
        self.stats = None

    def __call__(self, glyphSet):
        self.stats = {}
        if super(CubicToQuadraticFilter, self).__call__(glyphSet):
            self.dump_stats()

    def dump_stats(self):
        stats = self.stats
        logger.info('New spline lengths: %s' % (', '.join(
                    '%s: %d' % (l, stats[l]) for l in sorted(stats.keys()))))
        self.stats = None

    def filter(self, glyph, glyphSet=None):
        if not len(glyph):
            return False

        pen = Cu2QuPointPen(
            glyph.getPointPen(),
            self.absoluteError,
            reverse_direction=self.reverseDirection,
            stats=self.stats)
        contours = list(glyph)
        glyph.clearContours()
        for contour in contours:
            contour.drawPoints(pen)
        return True
