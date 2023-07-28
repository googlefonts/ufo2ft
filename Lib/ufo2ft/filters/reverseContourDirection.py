from fontTools.pens.pointPen import ReverseContourPointPen

from ufo2ft.filters import BaseFilter


class ReverseContourDirectionFilter(BaseFilter):
    def filter(self, glyph):
        if not len(glyph):
            return False
        pen = ReverseContourPointPen(glyph.getPointPen())
        contours = list(glyph)
        glyph.clearContours()
        for contour in contours:
            contour.drawPoints(pen)
        return True
