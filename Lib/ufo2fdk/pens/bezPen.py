"""
Tools for transforming glyph data to Bez and back.

BezPen
    fontTools pen for drawing Bez instructions

drawBez
    function that draws Bez data with a fontTools pen

To do:
-   need to support hint reading from Bez. I'm not sure
    what the hint instructions look like, so they will
    probably cause an error now.
-   need to support div token. i see that it divides
    one value by another, but what should be done with
    the resulting value? should it be used for calculating
    the absolute position of the next coordinate? i need
    to see some test cases before i can impliment this...

Experimentatal:
- flex, preflx1, preflx2 (need test cases)
"""

"""
---------------------
- Bez Specification -
---------------------

(taken from FDK/Tools/FontLab/Macros/System/Modules/BezChar.py)

Type    Action
Number  Convert from ascii to number, and push value on argList. Numbers may be int or fractions.
div     divide n-2 token by n-1 token in place in the stack, and pop off n-1 token.
sc      Start path command. Start new contour. Set CurX,Y to  (0,0)
cp      Close path. Do a Contour.close(). Set pt index to zero. Note: any drawing command
        for Pt 0 will also start a new path.
rmt     Relative moveto. Do move to CurX + n-1, CurY + n. 
hmt     Relative h moveto. Do move to CurX + n. 
vmt     Relative v moveto. Do move to  CurY + n. 

vdt     Relative v line to. Do line-to CurY + n. Set start/end points as a corner pt.
hdt     Relative h line to. Do line-to CurX + n  Set start/end points as a corner pt.
rdt     Relative line to.  Do line-to CurX + n-1, CurY + n.  Set start/end points as a corner pt.

rct     Relative curve to. Calculate:
                                dx1 = n-5, dy1 = n-4
                                dx2 = dx1 + n-3, dy2 = dy1 + n-2
                                dx3 = dx2 + n-1, dy3 = dx2 + n
                                Do CurveTo (CurX + dx1, CurY + dy1),
                                         (CurX +dx2, CurY + dy2)
                                         (CurX + x3, CurY + dx3)
                                         Update CurX += dx3, CurY += dx3.
                                         Set new pt to be a curve pt.
vhct    Relative vertical horizontal curve to. Calculate:
                                dx1 = 0, dy1 = n-3
                                dx2 = n-2, dy2 = dy1 + n-1
                                dx3 = dx2 + n, dy3 = dy2
                                Do Curve to as above.
hvct    Relative horizontal vertical curve to.
                                dx1 = n-3, dy1 = 0
                                dx2 = dx1 + n-2, dy2 = n-1
                                dx3 = dx2, dy3 = dy2 +n
                                Do Curve to as above.

prflx1  Start of Type1 style flex ommands. Discard all
flx     Flex coommand. Push back on stack as to rct's.

rb, ry, rm, rv Stem hint, stem3 hint commands. Discard args and command.

sol/eol Dot Sections. Discard these and arg list.
beginsubr/endsubr Hint replacement subroutine block. Discard
snc/enc  hint replacement block. Discarded.
newcolors   end of hint replacement block. Discard.
id      Discard
"""

from fontTools.pens.basePen import BasePen
from ufo2fdk.pens import RelativeCoordinatePen, roundInt, roundIntPoint


class BezPen(RelativeCoordinatePen):

    def __init__(self, glyphSet=None):
        RelativeCoordinatePen.__init__(self, glyphSet)
        self._output = []
        self._lastX = None
        self._lastY = None
        self._lastPointType = None

    def _relativeMoveTo(self, pt):
        self._lastPointType = "move"
        x, y = pt
        if x == 0 and y != 0:
            self._output.append("%d vmt" % y)
        elif y == 0 and x != 0:
            self._output.append("%d hmt" % x)
        else:
            self._output.append("%d %d rmt" % (x, y))

    def _relativeLineTo(self, pt):
        self._lastPointType = "line"
        x, y = pt
        if x == 0:
            self._output.append("%d vdt" % y)
        elif y == 0:
            self._output.append("%d hdt" % x)
        else:
            self._output.append("%d %d rdt" % (x, y))

    def _relativeCurveToOne(self, pt1, pt2, pt3):
        self._lastPointType = "curve"
        x1, y1 = pt1
        x2, y2 = pt2
        x3, y3 = pt3
        if x1 == 0 and y3 == 0:
            self._output.append("%d %d %d %d vhct" % (y1, x2, y2, x3))
        elif y1 == 0 and x3 == 0:
            self._output.append("%d %d %d %d hvct" % (x1, x2, y2, y3))
        else:
            self._output.append("%d %d %d %d %d %d rct" % (x1, y1, x2, y2, x3, y3))

    def _closePath(self):
        if self._lastPointType != "move":
            self._output.append("cp")

    def _endPath(self):
        self._closePath()

    def getBez(self):
        bez = list(self._output)
        # add the start path command if outline data is present
        if bez:
            bez.insert(0, "sc")
        # add the final drawing command
        bez.append("ed\n")
        # the bez data must be joined with \n
        # not os.linesep, because ACLib requires \n
        bez = "\n".join(bez)
        return bez


def _absolutePoint(pt, last):
    if last is None:
        return pt
    relX, relY = pt
    absX, absY = last
    absX += relX
    absY += relY
    return absX, absY

# tokens that should be ignored during drawing
ignoredTokens = set([
    "sc", "ed",
    "rb", "ry", "rm", "rv",
    "sol", "eol",
    "beginsubr", "endsubr",
    "snc", "enc",
    "newcolors",
    "id"
])

def intPoint(pt):
    x, y = pt
    if int(x) == x:
        x = int(x)
    if int(y) == y:
        y = int(y)
    return x, y

def drawBez(bez, pen):
    """
    A function for drawing Bez data with a standard pen.
    Hint data in the Bez is ignored.
    """
    #
    lastPoint = None
    lastToken = None
    for line in bez.splitlines():
        # empty line
        if not line:
            continue
        # misplaced log entry
        if line.startswith("Wrote"):
            continue
        # character name
        if line.startswith("%"):
            continue
        token = line.split(" ")[-1]
        # test for ignore tokens
        if token in ignoredTokens:
            continue
        ## Flex Tokens
        # flex token. convert to rct.
        if token == "flex":
            token = "rct"
        # preflx tokens. remove 
        elif token == "preflx1" or token == "preflx2":
            lastPoint = None
            lastToken = None
            continue
        ## Drawing Tokens
        # closePath
        if token == "cp":
            pen.closePath()
            lastToken = "close"
            continue
        coordinates = [float(i) for i in line.split(" ")[:-1]]
        # moveTo
        if token == "rmt":
            if lastToken == "move":
                pen.closePath()
            lastPoint = _absolutePoint(coordinates, lastPoint)
            lastPoint = intPoint(lastPoint)
            pen.moveTo(lastPoint)
            lastToken = "move"
        elif token == "vmt":
            if lastToken == "move":
                pen.closePath()
            lastPoint = _absolutePoint((0, coordinates[0]), lastPoint)
            lastPoint = intPoint(lastPoint)
            pen.moveTo(lastPoint)
            lastToken = "move"
        elif token == "hmt":
            if lastToken == "move":
                pen.closePath()
            lastPoint = _absolutePoint((coordinates[0], 0), lastPoint)
            lastPoint = intPoint(lastPoint)
            pen.moveTo(lastPoint)
            lastToken = "move"
        # lineTo
        elif token == "rdt":
            lastPoint = _absolutePoint((coordinates), lastPoint)
            lastPoint = intPoint(lastPoint)
            pen.lineTo(lastPoint)
            lastToken = "line"
        elif token == "vdt":
            lastPoint = _absolutePoint((0, coordinates[0]), lastPoint)
            lastPoint = intPoint(lastPoint)
            pen.lineTo(lastPoint)
            lastToken = "line"
        elif token == "hdt":
            lastPoint = _absolutePoint((coordinates[0], 0), lastPoint)
            lastPoint = intPoint(lastPoint)
            pen.lineTo(lastPoint)
            lastToken = "line"
        # curveTo
        elif token == "rct":
            p1 = (coordinates[0], coordinates[1])
            p1 = lastPoint = _absolutePoint(p1, lastPoint)
            p2 = (coordinates[2], coordinates[3])
            p2 = lastPoint = _absolutePoint(p2, lastPoint)
            p3 = (coordinates[4], coordinates[5])
            p3 = lastPoint = _absolutePoint(p3, lastPoint)
            p1 = intPoint(p1)
            p2 = intPoint(p2)
            p3 = intPoint(p3)
            pen.curveTo(p1, p2, p3)
            lastToken = "curve"
        elif token == "vhct":
            p1 = (0, coordinates[0])
            p1 = lastPoint = _absolutePoint(p1, lastPoint)
            p2 = (coordinates[1], coordinates[2])
            p2 = lastPoint = _absolutePoint(p2, lastPoint)
            p3 = (coordinates[3], 0)
            p3 = lastPoint = _absolutePoint(p3, lastPoint)
            p1 = intPoint(p1)
            p2 = intPoint(p2)
            p3 = intPoint(p3)
            pen.curveTo(p1, p2, p3)
            lastToken = "curve"
        elif token == "hvct":
            p1 = (coordinates[0], 0)
            p1 = lastPoint = _absolutePoint(p1, lastPoint)
            p2 = (coordinates[1], coordinates[2])
            p2 = lastPoint = _absolutePoint(p2, lastPoint)
            p3 = (0, coordinates[3])
            p3 = lastPoint = _absolutePoint(p3, lastPoint)
            p1 = intPoint(p1)
            p2 = intPoint(p2)
            p3 = intPoint(p3)
            pen.curveTo(p1, p2, p3)
            lastToken = "curve"
        else:
            raise NotImplementedError, line
