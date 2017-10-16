from __future__ import (
    print_function, division, absolute_import, unicode_literals)

from ufo2ft.filters import loadFilters
from ufo2ft.filters.decomposeComponents import DecomposeComponentsFilter

from copy import deepcopy


class BasePreProcessor(object):
    """Base class for objects that performs pre-processing operations on
    the UFO glyphs, such as decomposing composites, removing overlaps, or
    applying custom filters.

    The input UFO is **not** modified. The ``process`` method returns a
    dictionary containing the modified glyphset, keyed by glyph name.

    Subclasses can override the ``initDefaultFilters`` method and return
    a list of built-in filters which are performed in a predefined order,
    between the user-defined pre- and post-filters.
    The extra kwargs passed to the constructor can be used to customize the
    initialization of the default filters.

    Custom filters can be applied before or after the default filters.
    These are specified in the UFO lib.plist under the private key
    "com.github.googlei18n.ufo2ft.filters".
    """

    def __init__(self, ufo, **kwargs):
        self.ufo = ufo
        self.glyphSet = {g.name: _copyGlyph(g) for g in ufo}
        self.defaultFilters = self.initDefaultFilters(**kwargs)
        self.preFilters, self.postFilters = loadFilters(self.ufo)

    def initDefaultFilters(self, **kwargs):
        return []

    def process(self):
        glyphSet = self.glyphSet
        for func in self.preFilters + self.defaultFilters + self.postFilters:
            func(glyphSet)
        return glyphSet


class OTFPreProcessor(BasePreProcessor):
    """Preprocessor for building CFF-flavored OpenType fonts.

    By default, it decomposes all the components.

    If ``removeOverlaps`` is True, it performs a union boolean operation on
    all the glyphs' contours.
    """

    def initDefaultFilters(self, removeOverlaps=False):
        filters = [DecomposeComponentsFilter()]
        if removeOverlaps:
            from ufo2ft.filters.removeOverlaps import RemoveOverlapsFilter
            filters.append(RemoveOverlapsFilter())
        return filters


class TTFPreProcessor(OTFPreProcessor):
    """Preprocessor for building TrueType-flavored OpenType fonts.

    By default, it decomposes all the glyphs with mixed component/contour
    outlines.

    If ``removeOverlaps`` is True, it performs a union boolean operation on
    all the glyphs' contours.

    By default, it also converts all the PostScript cubic Bezier curves to
    TrueType quadratic splines. If the outlines are already quadratic, you
    can skip this by setting ``convertCubics`` to False.

    The optional ``conversionError`` argument controls the tolerance
    of the approximation algorithm. It is measured as the maximum distance
    between the original and converted curve, and it's relative to the UPM
    of the font (default: 1/1000 or 0.001).

    When converting curves to quadratic, it is assumed that the contours'
    winding direction is set following the PostScript counter-clockwise
    convention. Thus, by default the direction is reversed, in order to
    conform to opposite clockwise convention for TrueType outlines.
    You can disable this by setting ``reverseDirection`` to False.
    """

    def initDefaultFilters(self, removeOverlaps=False, convertCubics=True,
                           conversionError=None, reverseDirection=True):
        # len(g) is the number of contours, so we include the all glyphs
        # that have both components and at least one contour
        filters = [DecomposeComponentsFilter(include=lambda g: len(g))]

        if removeOverlaps:
            from ufo2ft.filters.removeOverlaps import RemoveOverlapsFilter
            filters.append(RemoveOverlapsFilter())

        if convertCubics:
            from ufo2ft.filters.cubicToQuadratic import CubicToQuadraticFilter
            filters.append(
                CubicToQuadraticFilter(conversionError=conversionError,
                                       unitsPerEm=self.ufo.info.unitsPerEm,
                                       reverseDirection=reverseDirection))

        return filters


def _copyGlyph(glyph):
    # copy everything except unused attributes: 'guidelines', 'note', 'image'
    copy = glyph.__class__()
    copy.name = glyph.name
    copy.width = glyph.width
    copy.height = glyph.height
    copy.unicodes = list(glyph.unicodes)
    copy.anchors = [dict(a) for a in glyph.anchors]
    copy.lib = deepcopy(glyph.lib)
    pointPen = copy.getPointPen()
    glyph.drawPoints(pointPen)
    return copy
