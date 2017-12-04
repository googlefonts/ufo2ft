from __future__ import (
    print_function, division, absolute_import, unicode_literals)

import math
from collections import namedtuple
import logging

from ufo2ft.filters import BaseFilter

from fontTools.misc.py23 import round
from fontTools.misc.transform import Identity
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen as _TransformPen


# make do without the real Enum type, python3 only... :(
def IntEnum(typename, field_names):
    return namedtuple(typename, field_names)._make(
        range(len(field_names)))


log = logging.getLogger(__name__)


class TransformPen(_TransformPen):

    def __init__(self, outPen, transformation, exclude=None):
        super(TransformPen, self).__init__(outPen, transformation)
        self.exclude = exclude if exclude is not None else set()

    def addComponent(self, baseGlyph, transformation):
        if baseGlyph in self.exclude:
            self._outPen.addComponent(baseGlyph, transformation)
        else:
            super(TransformPen, self).addComponent(baseGlyph, transformation)


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

    def get_origin_height(self, font, origin):
        if origin is self.Origin.BASELINE:
            return 0
        elif origin is self.Origin.CAP_HEIGHT:
            return font.info.capHeight
        elif origin is self.Origin.HALF_CAP_HEIGHT:
            return round(font.info.capHeight/2)
        elif origin is self.Origin.X_HEIGHT:
            return font.info.xHeight
        elif origin is self.Origin.HALF_X_HEIGHT:
            return round(font.info.xHeight/2)
        else:
            raise AssertionError(origin)

    def set_context(self, font, glyphSet):
        ctx = super(TransformationsFilter, self).set_context(font, glyphSet)

        origin_height = self.get_origin_height(font, self.options.Origin)

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
            if origin_height != 0:
                m = m.translate(0, origin_height)
            if sx != 100 or sy != 100:
                m = m.scale(sx/100, sy/100)
            if angle != 0:
                m = m.skew(math.radians(angle))
            if origin_height != 0:
                m = m.translate(0, -origin_height)

        ctx.matrix = m

        return ctx

    def filter(self, glyph):
        matrix = self.context.matrix
        if (matrix == Identity or
                not (glyph or glyph.components or glyph.anchors)):
            return False  # nothing to do

        if self.options.DEBUG:
            log.debug("transforming %r with %r", glyph.name, matrix)

        modified = self.context.modified
        glyphSet = self.context.glyphSet
        for component in glyph.components:
            base_name = component.baseGlyph
            if base_name in modified:
                if self.options.DEBUG:  # pragma: no cover
                    log.debug("base glyph %r already transformed; "
                              "skip component", base_name)
                continue
            base_glyph = glyphSet[base_name]
            if self.include(base_glyph) and self.filter(base_glyph):
                # base glyph is included but was not transformed yet; we
                # call filter recursively until all the included bases are
                # transformed, or there are no more components
                modified.add(base_name)

        rec = RecordingPen()
        glyph.draw(rec)
        glyph.clearContours()
        glyph.clearComponents()

        outpen = glyph.getPen()
        filterpen = TransformPen(outpen,
                                 matrix,
                                 exclude=modified)
        rec.replay(filterpen)

        # anchors are not drawn through the pen API,
        # must be transformed separately
        for a in glyph.anchors:
            a.x, a.y = matrix.transformPoint((a.x, a.y))

        return True
