import math
from collections import namedtuple
import logging

from ufo2ft.fontInfoData import getAttrWithFallback
from ufo2ft.filters import BaseFilter

from fontTools.misc.fixedTools import otRound
from fontTools.misc.transform import Transform, Identity
from fontTools.pens.recordingPen import RecordingPointPen
from fontTools.pens.transformPen import TransformPointPen as _TransformPointPen
from enum import IntEnum


log = logging.getLogger(__name__)


class TransformPointPen(_TransformPointPen):
    def __init__(self, outPointPen, transformation, modified=None):
        """
        Initialize the chat.

        Args:
            self: (todo): write your description
            outPointPen: (todo): write your description
            transformation: (todo): write your description
            modified: (todo): write your description
        """
        super().__init__(outPointPen, transformation)
        self.modified = modified if modified is not None else set()
        self._inverted = self._transformation.inverse()

    def addComponent(self, baseGlyph, transformation, identifier=None, **kwargs):
        """
        Adds a component to the glyph.

        Args:
            self: (todo): write your description
            baseGlyph: (str): write your description
            transformation: (str): write your description
            identifier: (todo): write your description
        """
        if baseGlyph in self.modified:
            # multiply the component's transformation matrix with the inverse
            # of the filter's transformation matrix to compensate for the
            # transformation already applied to the base glyph
            transformation = Transform(*transformation).transform(self._inverted)

        super().addComponent(baseGlyph, transformation, identifier=identifier, **kwargs)


class TransformationsFilter(BaseFilter):
    class Origin(IntEnum):
        CAP_HEIGHT = 0
        HALF_CAP_HEIGHT = 1
        X_HEIGHT = 2
        HALF_X_HEIGHT = 3
        BASELINE = 4

    _kwargs = {
        "OffsetX": 0,
        "OffsetY": 0,
        "ScaleX": 100,
        "ScaleY": 100,
        "Slant": 0,
        "Origin": 4,  # BASELINE
    }

    def start(self):
        """
        Starts the port

        Args:
            self: (todo): write your description
        """
        self.options.Origin = self.Origin(self.options.Origin)

    def get_origin_height(self, font, origin):
        """
        Return the height of the font.

        Args:
            self: (todo): write your description
            font: (str): write your description
            origin: (str): write your description
        """
        if origin is self.Origin.BASELINE:
            return 0
        elif origin is self.Origin.CAP_HEIGHT:
            return getAttrWithFallback(font.info, "capHeight")
        elif origin is self.Origin.HALF_CAP_HEIGHT:
            return otRound(getAttrWithFallback(font.info, "capHeight") / 2)
        elif origin is self.Origin.X_HEIGHT:
            return getAttrWithFallback(font.info, "xHeight")
        elif origin is self.Origin.HALF_X_HEIGHT:
            return otRound(getAttrWithFallback(font.info, "xHeight") / 2)
        else:
            raise AssertionError(origin)

    def set_context(self, font, glyphSet):
        """
        Set the context of the font.

        Args:
            self: (todo): write your description
            font: (todo): write your description
            glyphSet: (todo): write your description
        """
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
                m = m.scale(sx / 100, sy / 100)
            if angle != 0:
                m = m.skew(math.radians(angle))
            if origin_height != 0:
                m = m.translate(0, -origin_height)

        ctx.matrix = m

        return ctx

    def filter(self, glyph):
        """
        Filter this glyph by a glyph.

        Args:
            self: (todo): write your description
            glyph: (todo): write your description
        """
        matrix = self.context.matrix
        if matrix == Identity or not (glyph or glyph.components or glyph.anchors):
            return False  # nothing to do

        modified = self.context.modified
        glyphSet = self.context.glyphSet
        for component in glyph.components:
            base_name = component.baseGlyph
            if base_name in modified:
                continue
            base_glyph = glyphSet[base_name]
            if self.include(base_glyph) and self.filter(base_glyph):
                # base glyph is included but was not transformed yet; we
                # call filter recursively until all the included bases are
                # transformed, or there are no more components
                modified.add(base_name)

        rec = RecordingPointPen()
        glyph.drawPoints(rec)
        glyph.clearContours()
        glyph.clearComponents()

        outpen = glyph.getPointPen()
        filterpen = TransformPointPen(outpen, matrix, modified)
        rec.replay(filterpen)

        # anchors are not drawn through the pen API,
        # must be transformed separately
        for a in glyph.anchors:
            a.x, a.y = matrix.transformPoint((a.x, a.y))

        return True
