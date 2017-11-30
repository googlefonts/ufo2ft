from __future__ import (
    print_function, division, absolute_import, unicode_literals)

import math
from collections import namedtuple
import logging

from ufo2ft.filters import BaseFilter

from fontTools.misc.py23 import round
from fontTools.misc.transform import Identity
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen


# make do without the real Enum type, python3 only... :(
def IntEnum(typename, field_names):
    return namedtuple(typename, field_names)._make(
        range(len(field_names)))


log = logging.getLogger(__name__)


class TransformationsFilter(BaseFilter):

    Origin = IntEnum(
        'Origin',
        (
            'CAP_HEIGHT',
            'HALF_CAP_HEIGHT',
            'X_HEIGHT',
            'HALF_X_HEIGHT',
            'BASELINE',
        )
    )

    _kwargs = {
        'OffsetX': 0,
        'OffsetY': 0,
        'ScaleX': 100,
        'ScaleY': 100,
        'Slant': 0,
        'Origin': 4,  # BASELINE
        'DEBUG': False,  # enables logging
    }

    def start(self):
        if self.options.Origin not in self.Origin:
            raise ValueError("%r is not a valid Origin value"
                             % self.options.Origin)

    def set_context(self, font, glyphSet):
        origin = self.options.Origin
        if origin is self.Origin.BASELINE:
            value = 0
        elif origin is self.Origin.CAP_HEIGHT:
            value = font.info.capHeight
        elif origin is self.Origin.HALF_CAP_HEIGHT:
            value = round(font.info.capHeight/2)
        elif origin is self.Origin.X_HEIGHT:
            value = font.info.xHeight
        elif origin is self.Origin.HALF_X_HEIGHT:
            value = round(font.info.xHeight/2)
        else:
            raise AssertionError(origin)
        return dict(origin_height=value)

    @staticmethod
    def transform(glyph, matrix):
        if matrix == Identity:
            return False

        rec = RecordingPen()
        glyph.draw(rec)
        glyph.clearContours()
        glyph.clearComponents()
        rec.replay(TransformPen(glyph.getPen(), matrix))
        # anchors are not drawn through the pen API,
        # must be transformed separately
        for a in glyph.anchors:
            a.x, a.y = matrix.transformPoint((a.x, a.y))
        return True

    def filter(self, glyph):
        if not (glyph or glyph.components or glyph.anchors):
            return False  # skip empty

        m = Identity
        dx, dy = self.options.OffsetX, self.options.OffsetY
        if dx != 0 or dy != 0:
            m = m.translate(dx, dy)

        sx, sy = self.options.ScaleX, self.options.ScaleY
        angle = self.options.Slant
        # TODO Add support for "Cursify" option
        # cursify = self.options.SlantCorrection
        if sx != 100 or sy != 100 or angle != 0:
            # vertically shift glyph to the specified 'Origin' before
            # scaling and/or slanting, then move it back
            oy = self.context.origin_height
            if oy != 0:
                m = m.translate(0, oy)
            if sx != 100 or sy != 100:
                m = m.scale(sx/100, sy/100)
            if angle != 0:
                m = m.skew(math.radians(angle))
            if oy != 0:
                m = m.translate(0, -oy)

        if self.options.DEBUG:
            log.debug("transforming %r with %r", glyph.name, m)
        return self.transform(glyph, m)
