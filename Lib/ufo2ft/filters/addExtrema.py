import logging
from math import sqrt

from fontTools.misc.bezierTools import splitCubicAtT
from fontTools.pens.filterPen import FilterPen
from fontTools.pens.recordingPen import RecordingPen

from ufo2ft.filters import BaseFilter

logger = logging.getLogger(__name__)


def quadraticRoots(a, b, c):
    """Returns real roots of at^2 + bt + c = 0 if 0 < root < 1"""
    roots = []
    if a != 0.0 and b * b - 4 * a * c > 0.0:
        x = -b / (2 * a)
        y = sqrt(b * b - 4 * a * c) / (2 * a)
        t1 = x - y
        if 0.0 <= t1 <= 1.0:
            roots.append(t1)
        t2 = x + y
        if 0.0 <= t2 <= 1.0:
            roots.append(t2)
    return roots


class AddExtremaPen(FilterPen):
    def __init__(self, outPen):
        self._outPen = outPen
        self.affected = False

    def moveTo(self, pt):
        self.lastPt = pt
        self._outPen.moveTo(pt)

    def lineTo(self, pt):
        self.lastPt = pt
        self._outPen.lineTo(pt)

    def qCurveTo(self, *points):
        self.lastPt = points[-1]
        self._outPen.qCurveTo(*points)

    def curveTo(self, *points):
        # Make it a full segment
        points = [self.lastPt] + list(points)

        # Does this curve have extremes?
        derivative = [
            ((points[1][0] - points[0][0]) * 3, (points[1][1] - points[0][1]) * 3),
            ((points[2][0] - points[1][0]) * 3, (points[2][1] - points[1][1]) * 3),
            ((points[3][0] - points[2][0]) * 3, (points[3][1] - points[2][1]) * 3),
        ]
        roots = []
        roots.extend(
            quadraticRoots(
                derivative[0][0] - 2 * derivative[1][0] + derivative[2][0],
                2 * (derivative[1][0] - derivative[0][0]),
                derivative[0][0],
            )
        )
        roots.extend(
            quadraticRoots(
                derivative[0][1] - 2 * derivative[1][1] + derivative[2][1],
                2 * (derivative[1][1] - derivative[0][1]),
                derivative[0][1],
            )
        )

        # To find inflections, we need to take the second derivative
        d1 = derivative[0][0] - 2 * derivative[1][0] + derivative[2][0]
        d2 = derivative[0][1] - 2 * derivative[1][1] + derivative[2][1]
        if d1 != 0:
            r1 = (derivative[0][0] - derivative[1][0]) / d1
            roots.append(r1)
        if d2 != 0:
            r2 = (derivative[0][1] - derivative[1][1]) / d2
            roots.append(r2)

        roots = [x for x in roots if 0.01 <= x <= 0.99]
        if roots:
            for subcurve in splitCubicAtT(*points, *roots):
                self._outPen.curveTo(*subcurve[1:])
            self.affected = True
        else:
            self._outPen.curveTo(*points[1:])
        self.lastPt = points[-1]


class AddExtremaFilter(BaseFilter):
    def filter(self, glyph):
        if not len(glyph):
            return False

        contours = list(glyph)
        outpen = RecordingPen()
        p = AddExtremaPen(outpen)
        for contour in contours:
            contour.draw(p)
        if p.affected:
            glyph.clearContours()
            outpen.replay(glyph.getPen())
        return p.affected
