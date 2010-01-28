from fontTools.pens.basePen import BasePen

def roundInt(v):
    return int(round(v))

def roundIntPoint((x, y)):
    return roundInt(x), roundInt(y)


class RelativeCoordinatePen(BasePen):

    def __init__(self, glyphSet):
        BasePen.__init__(self, glyphSet)
        self._lastX = None
        self._lastY = None

    def _makePointRelative(self, pt):
        absX, absY = pt
        absX = absX
        absY = absY
        # no points have been added
        # so no conversion is needed
        if self._lastX is None:
            relX, relY = absX, absY
        # otherwise calculate the relative coordinates
        else:
            relX = absX - self._lastX
            relY = absY - self._lastY
        # store the absolute coordinates
        self._lastX = absX
        self._lastY = absY
        # now return the relative coordinates
        return relX, relY

    def _moveTo(self, pt):
        pt = self._makePointRelative(pt)
        self._relativeMoveTo(pt)

    def _relativeMoveTo(self, pt):
        raise NotImplementedError

    def _lineTo(self, pt):
        pt = self._makePointRelative(pt)
        self._relativeLineTo(pt)

    def _relativeLineTo(self, pt):
        raise NotImplementedError

    def _curveToOne(self, pt1, pt2, pt3):
        pt1 = self._makePointRelative(pt1)
        pt2 = self._makePointRelative(pt2)
        pt3 = self._makePointRelative(pt3)
        self._relativeCurveToOne(pt1, pt2, pt3)

    def _relativeCurveToOne(self, pt1, pt2, pt3):
        raise NotImplementedError
