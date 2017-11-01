from __future__ import (
    print_function, division, absolute_import, unicode_literals)

from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.misc.transform import Transform, Identity
from fontTools.pens.transformPen import TransformPen
from ufo2ft.filters import BaseFilter


class DecomposeComponentsFilter(BaseFilter):

    def filter(self, glyph):
        if not glyph.components:
            return False
        _deepCopyContours(self.context.glyphSet, glyph, glyph, Transform())
        glyph.clearComponents()
        return True


def _deepCopyContours(glyphSet, parent, component, transformation):
    """Copy contours from component to parent, including nested components."""

    for nested in component.components:
        _deepCopyContours(
            glyphSet, parent, glyphSet[nested.baseGlyph],
            transformation.transform(nested.transformation))

    if component != parent:
        if transformation == Identity:
            pen = parent.getPen()
        else:
            pen = TransformPen(parent.getPen(), transformation)
            # if the transformation has a negative determinant, it will
            # reverse the contour direction of the component
            xx, xy, yx, yy = transformation[:4]
            if xx*yy - xy*yx < 0:
                pen = ReverseContourPen(pen)

        component.draw(pen)
