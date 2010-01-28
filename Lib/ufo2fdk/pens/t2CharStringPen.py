from fontTools.misc.psCharStrings import T2CharString
from ufo2fdk.pens import RelativeCoordinatePen, roundInt, roundIntPoint


class T2CharStringPen(RelativeCoordinatePen):

    def __init__(self, width, glyphSet):
        RelativeCoordinatePen.__init__(self, glyphSet)
        self._program = []
        if width is not None:
            self._program.append(roundInt(width))

    def _relativeMoveTo(self, pt):
        pt = roundIntPoint(pt)
        x, y = pt
        self._program.extend([x, y, "rmoveto"])

    def _relativeLineTo(self, pt):
        pt = roundIntPoint(pt)
        x, y = pt
        self._program.extend([x, y, "rlineto"])

    def _relativeCurveToOne(self, pt1, pt2, pt3):
        pt1 = roundIntPoint(pt1)
        pt2 = roundIntPoint(pt2)
        pt3 = roundIntPoint(pt3)
        x1, y1 = pt1
        x2, y2 = pt2
        x3, y3 = pt3
        self._program.extend([x1, y1, x2, y2, x3, y3, "rrcurveto"])

    def _closePath(self):
        pass

    def _endPath(self):
        pass

    def getCharString(self, private=None, globalSubrs=None):
        program = self._program + ["endchar"]
        charString = T2CharString(program=program, private=private, globalSubrs=globalSubrs)
        return charString