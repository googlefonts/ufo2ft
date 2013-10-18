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
        self._heldAbsoluteMove = None

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
        self._heldAbsoluteMove = pt
    
    def _releaseHeldMove(self):
        if self._heldAbsoluteMove is not None:
            pt = self._makePointRelative(self._heldAbsoluteMove)
            self._relativeMoveTo(pt)
            self._heldAbsoluteMove = None
    
    def _relativeMoveTo(self, pt):
        raise NotImplementedError

    def _lineTo(self, pt):
        self._releaseHeldMove()
        pt = self._makePointRelative(pt)
        self._relativeLineTo(pt)

    def _relativeLineTo(self, pt):
        raise NotImplementedError

    def _curveToOne(self, pt1, pt2, pt3):
        self._releaseHeldMove()
        pt1 = self._makePointRelative(pt1)
        pt2 = self._makePointRelative(pt2)
        pt3 = self._makePointRelative(pt3)
        self._relativeCurveToOne(pt1, pt2, pt3)

    def _relativeCurveToOne(self, pt1, pt2, pt3):
        raise NotImplementedError
