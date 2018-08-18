from __future__ import (
    print_function, division, absolute_import, unicode_literals)

from fontTools.misc.py23 import basestring
from ufo2ft.filters import loadFilters
from ufo2ft.filters.decomposeComponents import DecomposeComponentsFilter
from ufo2ft.util import copyGlyphSet


class BasePreProcessor(object):
    """Base class for objects that performs pre-processing operations on
    the UFO glyphs, such as decomposing composites, removing overlaps, or
    applying custom filters.

    By default the input UFO is **not** modified. The ``process`` method
    returns a dictionary containing the new modified glyphset, keyed by
    glyph name. If ``inplace`` is True, the input UFO is modified directly
    without the need to first copy the glyphs.

    Subclasses can override the ``initDefaultFilters`` method and return
    a list of built-in filters which are performed in a predefined order,
    between the user-defined pre- and post-filters.
    The extra kwargs passed to the constructor can be used to customize the
    initialization of the default filters.

    Custom filters can be applied before or after the default filters.
    These are specified in the UFO lib.plist under the private key
    "com.github.googlei18n.ufo2ft.filters".
    """

    def __init__(self, ufo, inplace=False, **kwargs):
        self.ufo = ufo
        self.inplace = inplace
        if inplace:
            self.glyphSet = {g.name: g for g in ufo}
        else:
            self.glyphSet = copyGlyphSet(ufo)
        self.defaultFilters = self.initDefaultFilters(**kwargs)
        self.preFilters, self.postFilters = loadFilters(ufo)

    def initDefaultFilters(self, **kwargs):
        return []  # pragma: no cover

    def process(self):
        ufo = self.ufo
        glyphSet = self.glyphSet
        for func in self.preFilters + self.defaultFilters + self.postFilters:
            func(ufo, glyphSet)
        return glyphSet


class OTFPreProcessor(BasePreProcessor):
    """Preprocessor for building CFF-flavored OpenType fonts.

    By default, it decomposes all the components.

    If ``removeOverlaps`` is True, it performs a union boolean operation on
    all the glyphs' contours.

    By default, booleanOperations is used to remove overlaps. You can choose
    skia-pathops by setting ``overlapsBackend`` to the enum value
    ``RemoveOverlapsFilter.SKIA_PATHOPS``, or the string "pathops".
    """

    def initDefaultFilters(
        self, removeOverlaps=False, overlapsBackend=None
    ):
        filters = [DecomposeComponentsFilter()]
        if removeOverlaps:
            from ufo2ft.filters.removeOverlaps import RemoveOverlapsFilter

            if overlapsBackend is not None:
                filters.append(
                    RemoveOverlapsFilter(backend=overlapsBackend)
                )
            else:
                filters.append(RemoveOverlapsFilter())

        return filters


class TTFPreProcessor(OTFPreProcessor):
    """Preprocessor for building TrueType-flavored OpenType fonts.

    By default, it decomposes all the glyphs with mixed component/contour
    outlines.

    If ``removeOverlaps`` is True, it performs a union boolean operation on
    all the glyphs' contours.

    By default, booleanOperations is used to remove overlaps. You can choose
    skia-pathops by setting ``overlapsBackend`` to the enum value
    ``RemoveOverlapsFilter.SKIA_PATHOPS``, or the string "pathops".

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

    If both ``inplace`` and ``rememberCurveType`` options are True, the curve
    type "quadratic" is saved in font' lib under a private cu2qu key; the
    preprocessor will not try to convert them again if the curve type is
    already set to "quadratic".
    """

    def initDefaultFilters(
        self,
        removeOverlaps=False,
        overlapsBackend=None,
        convertCubics=True,
        conversionError=None,
        reverseDirection=True,
        rememberCurveType=True
    ):
        # len(g) is the number of contours, so we include the all glyphs
        # that have both components and at least one contour
        filters = [DecomposeComponentsFilter(include=lambda g: len(g))]

        if removeOverlaps:
            from ufo2ft.filters.removeOverlaps import RemoveOverlapsFilter

            if overlapsBackend is not None:
                filters.append(
                    RemoveOverlapsFilter(backend=overlapsBackend)
                )
            else:
                filters.append(RemoveOverlapsFilter())

        if convertCubics:
            from ufo2ft.filters.cubicToQuadratic import CubicToQuadraticFilter

            filters.append(
                CubicToQuadraticFilter(
                    conversionError=conversionError,
                    reverseDirection=reverseDirection,
                    rememberCurveType=rememberCurveType and self.inplace,
                )
            )
        return filters


class TTFInterpolatablePreProcessor(object):
    """Preprocessor for building TrueType-flavored OpenType fonts with
    interpolatable quadratic outlines.

    The constructor takes a list of UFO fonts, and the ``process`` method
    returns the modified glyphsets (list of dicts) in the same order.

    Currently, only the conversion from cubic to quadratic, and the
    decomposition of mixed contour/component glyphs is performed,
    and no additional custom filter is applied.

    The ``conversionError``, ``reverseDirection`` and ``rememberCurveType``
    arguments work in the same way as in the ``TTFPreProcessor``.
    """

    def __init__(self, ufos, inplace=False, conversionError=None,
                 reverseDirection=True, rememberCurveType=True):
        from cu2qu.ufo import DEFAULT_MAX_ERR

        self.ufos = ufos
        self.inplace = inplace
        if inplace:
            self.glyphSets = [{g.name: g for g in ufo} for ufo in ufos]
        else:
            self.glyphSets = [copyGlyphSet(ufo) for ufo in ufos]
        self._conversionErrors = [
            (conversionError or DEFAULT_MAX_ERR) * ufo.info.unitsPerEm
            for ufo in ufos]
        self._reverseDirection = reverseDirection
        self._rememberCurveType = rememberCurveType

    def process(self):
        from cu2qu.ufo import fonts_to_quadratic

        fonts_to_quadratic(
            self.ufos if self.inplace else self.glyphSets,
            max_err=self._conversionErrors,
            reverse_direction=self._reverseDirection,
            dump_stats=True,
            remember_curve_type=self._rememberCurveType and self.inplace,
        )

        decompose = DecomposeComponentsFilter(include=lambda g: len(g))
        for ufo, glyphSet in zip(self.ufos, self.glyphSets):
            decompose(ufo, glyphSet)

        return self.glyphSets
