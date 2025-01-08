from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

from ufo2ft.constants import (
    COLOR_LAYER_MAPPING_KEY,
    COLOR_LAYERS_KEY,
    COLOR_PALETTES_KEY,
)
from ufo2ft.filters import isValidFilter, loadFilters
from ufo2ft.filters.base import BaseFilter, BaseIFilter
from ufo2ft.filters.decomposeComponents import (
    DecomposeComponentsFilter,
    DecomposeComponentsIFilter,
)
from ufo2ft.fontInfoData import getAttrWithFallback
from ufo2ft.util import _GlyphSet, zip_strict

if TYPE_CHECKING:
    from ufo2ft.instantiator import Instantiator


def _load_custom_filters(ufo, filters=None):
    # Args:
    #   ufo: Font
    #   filters: Optional[List[Union[Filter, EllipsisType]]])
    # Returns: List[Filter]

    # by default, load the filters from the lib; ellipsis is used as a placeholder
    # so one can optionally insert additional filters=[f1, ..., f2] either
    # before or after these, or override them by omitting the ellipsis.
    if filters is None:
        filters = [...]
    seen_ellipsis = False
    result = []
    for f in filters:
        if f is ...:
            if seen_ellipsis:
                raise ValueError("ellipsis not allowed more than once")
            result.extend(itertools.chain(*loadFilters(ufo)))
            seen_ellipsis = True
        else:
            if not isValidFilter(type(f)):
                raise TypeError(f"Invalid filter: {f!r}")
            result.append(f)
    return result


class BasePreProcessor:
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
    These can be specified in the UFO lib.plist under the private key
    "com.github.googlei18n.ufo2ft.filters".
    Alternatively the optional ``filters`` parameter can be used. This is a
    list of filter instances (subclasses of BaseFilter) that overrides
    those defined in the UFO lib. The list can be empty, meaning no custom
    filters are run. If ``filters`` contain the special value ``...`` (i.e.
    the actual ``ellipsis`` singleton, not the str literal '...'), then all
    the filters from the UFO lib are loaded in its place. This allows to
    insert additional filters before or after those already defined in the
    UFO lib, as opposed to discard/replace them which is the default behavior
    when ``...`` is absent.
    """

    def __init__(
        self,
        ufo,
        inplace=False,
        layerName=None,
        skipExportGlyphs=None,
        filters=None,
        **kwargs,
    ):
        self.ufo = ufo
        self.inplace = inplace
        self.layerName = layerName
        self.glyphSet = _GlyphSet.from_layer(
            ufo, layerName, copy=not inplace, skipExportGlyphs=skipExportGlyphs
        )
        self.defaultFilters = self.initDefaultFilters(**kwargs)

        filters = _load_custom_filters(ufo, filters)
        self.preFilters = [f for f in filters if f.pre]
        self.postFilters = [f for f in filters if not f.pre]

    def initDefaultFilters(self, **kwargs):
        return []  # pragma: no cover

    def process(self):
        ufo = self.ufo
        glyphSet = self.glyphSet
        for func in self.preFilters + self.defaultFilters + self.postFilters:
            func(ufo, glyphSet)
        return glyphSet


def _init_explode_color_layer_glyphs_filter(ufo, filters):
    # Initialize ExplodeColorLayerGlyphsFilter, which copies color glyph layers
    # as standalone glyphs to the default glyph set (for building COLR table), if the
    # UFO contains the required 'colorPalettes' key, as well as 'colorLayerMapping' lib
    # keys (in either the font's or glyph's lib).
    # Skip doing that if an explicit 'colorLayers' key is already present.
    if (
        COLOR_PALETTES_KEY in ufo.lib
        and COLOR_LAYERS_KEY not in ufo.lib
        and (
            COLOR_LAYER_MAPPING_KEY in ufo.lib
            or any(COLOR_LAYER_MAPPING_KEY in g.lib for g in ufo)
        )
    ):
        from ufo2ft.filters.explodeColorLayerGlyphs import ExplodeColorLayerGlyphsFilter

        filters.append(ExplodeColorLayerGlyphsFilter())


class OTFPreProcessor(BasePreProcessor):
    """Preprocessor for building CFF-flavored OpenType fonts.

    By default, it decomposes all the components.

    If ``removeOverlaps`` is True, it performs a union boolean operation on
    all the glyphs' contours.

    By default, booleanOperations is used to remove overlaps. You can choose
    skia-pathops by setting ``overlapsBackend`` to the enum value
    ``RemoveOverlapsFilter.SKIA_PATHOPS``, or the string "pathops".
    """

    def initDefaultFilters(self, removeOverlaps=False, overlapsBackend=None):
        filters = []

        _init_explode_color_layer_glyphs_filter(self.ufo, filters)

        filters.append(DecomposeComponentsFilter())

        if removeOverlaps:
            from ufo2ft.filters.removeOverlaps import RemoveOverlapsFilter

            if overlapsBackend is not None:
                filters.append(RemoveOverlapsFilter(backend=overlapsBackend))
            else:
                filters.append(RemoveOverlapsFilter())

        return filters


class TTFPreProcessor(OTFPreProcessor):
    """Preprocessor for building TrueType-flavored OpenType fonts.

    By default, it decomposes all the glyphs with mixed component/contour
    outlines. If the ``flattenComponents`` setting is True, glyphs with
    nested components are flattened so that they have at most one level of
    components.

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
        flattenComponents=False,
        convertCubics=True,
        conversionError=None,
        allQuadratic=True,
        reverseDirection=True,
        rememberCurveType=True,
    ):
        filters = []

        _init_explode_color_layer_glyphs_filter(self.ufo, filters)

        # len(g) is the number of contours, so we include the all glyphs
        # that have both components and at least one contour
        filters.append(DecomposeComponentsFilter(include=lambda g: len(g)))

        if flattenComponents:
            from ufo2ft.filters.flattenComponents import FlattenComponentsFilter

            filters.append(FlattenComponentsFilter())

        if removeOverlaps:
            from ufo2ft.filters.removeOverlaps import RemoveOverlapsFilter

            if overlapsBackend is not None:
                filters.append(RemoveOverlapsFilter(backend=overlapsBackend))
            else:
                filters.append(RemoveOverlapsFilter())

        if convertCubics:
            from ufo2ft.filters.cubicToQuadratic import CubicToQuadraticFilter

            filters.append(
                CubicToQuadraticFilter(
                    conversionError=conversionError,
                    reverseDirection=reverseDirection,
                    rememberCurveType=rememberCurveType and self.inplace,
                    allQuadratic=allQuadratic,
                )
            )
        elif reverseDirection:
            from ufo2ft.filters.reverseContourDirection import (
                ReverseContourDirectionFilter,
            )

            filters.append(ReverseContourDirectionFilter(include=lambda g: len(g)))
        return filters


class BaseInterpolatablePreProcessor:
    """Base class for interpolatable pre-processors.

    These apply filters to same-named glyphs from multiple source layers at once,
    ensuring that outlines are kept interpolation compatible.

    The optional `instantiator` can be used by filters to interpolate glyph
    instances (e.g. when decomposing composite glyphs defined at more or less
    source locations as some of their components' base glyphs).
    """

    def __init__(
        self,
        ufos,
        inplace=False,
        layerNames=None,
        skipExportGlyphs=None,
        filters=None,
        *,
        instantiator: Instantiator | None = None,
        **kwargs,
    ):
        self.ufos = ufos
        self.inplace = inplace

        if layerNames is None:
            layerNames = [None] * len(ufos)
        assert len(ufos) == len(layerNames)
        self.layerNames = layerNames

        if instantiator is not None and len(instantiator.source_layers) != len(ufos):
            raise ValueError(
                f"Expected {len(ufos)} sources for instantiator; "
                f"found {len(instantiator.source_layers)}"
            )
        self.instantiator = instantiator

        # For each UFO, make a mapping of name to glyph object (and ensure it
        # contains none of the glyphs to be skipped, or any references to it).
        self.glyphSets = [
            _GlyphSet.from_layer(ufo, layerName, copy=not inplace)
            for ufo, layerName in zip_strict(ufos, layerNames)
        ]
        if skipExportGlyphs:
            from ufo2ft.filters.skipExportGlyphs import SkipExportGlyphsIFilter

            self._run(SkipExportGlyphsIFilter(skipExportGlyphs))

        self.defaultFilters = self.initDefaultFilters(**kwargs)

        filterses = [_load_custom_filters(ufo, filters) for ufo in ufos]
        self.preFilters = [[f for f in filters if f.pre] for filters in filterses]
        self.postFilters = [[f for f in filters if not f.pre] for filters in filterses]

    def initDefaultFilters(self, **kwargs):
        filterses = []
        for ufo in self.ufos:
            filterses.append([])
            _init_explode_color_layer_glyphs_filter(ufo, filterses[-1])
        return filterses

    def process(self):
        # first apply all custom pre-filters, then all default filters, and finally
        # all custom post-filters
        for filterses in (self.preFilters, self.defaultFilters, self.postFilters):
            for filters in itertools.zip_longest(*filterses):
                self._run(*filters)
        return self.glyphSets

    def _update_instantiator(self):
        # the instantiator's source layers must be updated after each filter is run,
        # since each filter can modify/remove/add glyphs.
        if self.instantiator is not None:
            self.instantiator.replace_source_layers(self.glyphSets)

    def _run_interpolatable(self, filter_: BaseIFilter) -> set[str]:
        # apply a single, interpolatable filter to all the glyphSets
        modified = filter_(self.ufos, self.glyphSets, self.instantiator)
        if modified:
            self._update_instantiator()
        return modified

    @staticmethod
    def _try_as_interpolatable_filter(
        filters: list[BaseFilter | None],
    ) -> BaseIFilter | None:
        # Try to combine multiple filters into a single interpolatable variant
        assert len(filters) > 0
        filter_ = next(filter(None, filters))
        filter_class = type(filter_)

        if not all(
            (
                type(f) is filter_class
                and f.options == filter_.options
                and f.pre == filter_.pre
            )
            for f in filters[1:]
        ):
            return None

        if isinstance(filter_, BaseIFilter):
            return filter_

        ifilter_class = None
        try:
            ifilter_class = filter_class.getInterpolatableFilterClass()
        except AttributeError:
            pass
        if ifilter_class is None:
            return None

        if not isValidFilter(ifilter_class, BaseIFilter):
            raise ValueError(f"Invalid interpolatable filter class: {ifilter_class!r}")

        # in the unlikely scenario individual filters have different includes,
        # this effectively takes the union of those
        def include(g):
            return any(f.include(g) for f in filters)

        return ifilter_class(
            pre=filter_.pre,
            include=include,
            **filter_.options.__dict__,
        )

    def _run(self, *filters: tuple[BaseFilter | None]) -> set[str]:
        # apply either multiple (one per glyphSet) or a single filter to all glyphSets
        if len(filters) == 1:
            assert filters[0] is not None
            if isinstance(filters[0], BaseIFilter):
                return self._run_interpolatable(filters[0])

            filters = [filters[0]] * len(self.ufos)

        # attempt to convert mutltiple filters to single interpolatable variant (if any)
        if ifilter := self._try_as_interpolatable_filter(filters):
            return self._run_interpolatable(ifilter)

        # or else apply individual filters to the respective glyphSet, one at a time,
        # and hope for the best...
        modified = set()
        for filter_, ufo, glyphSet in zip_strict(filters, self.ufos, self.glyphSets):
            if filter_ is not None:
                modified |= filter_(ufo, glyphSet)
        if modified:
            self._update_instantiator()
        return modified


class TTFInterpolatablePreProcessor(BaseInterpolatablePreProcessor):
    """Preprocessor for building TrueType-flavored OpenType fonts with
    interpolatable quadratic outlines.

    The constructor takes a list of UFO fonts, and the ``process`` method
    returns the modified glyphsets (list of dicts) in the same order.

    The pre-processor performs the conversion from cubic to quadratic on
    all the UFOs at once, then decomposes mixed contour/component glyphs.

    Additional pre/post custom filter are also applied to each single UFOs,
    respectively before or after the default filters, if they are specified
    in the UFO's lib.plist under the private key
    "com.github.googlei18n.ufo2ft.filters".
    NOTE: If you use any custom filters, the resulting glyphsets may no longer
    be interpolation compatible, depending on the particular filter used or
    whether they are applied to only some vs all of the UFOs.

    The ``conversionError``, ``reverseDirection``, ``flattenComponents`` and
    ``rememberCurveType`` arguments work in the same way as in the
    ``TTFPreProcessor``.
    """

    def __init__(
        self,
        ufos,
        inplace=False,
        flattenComponents=False,
        convertCubics=True,
        conversionError=None,
        reverseDirection=True,
        rememberCurveType=True,
        layerNames=None,
        skipExportGlyphs=None,
        filters=None,
        allQuadratic=True,
        *,
        instantiator: Instantiator | None = None,
        **kwargs,
    ):
        from fontTools.cu2qu.ufo import DEFAULT_MAX_ERR

        super().__init__(
            ufos,
            inplace=inplace,
            layerNames=layerNames,
            skipExportGlyphs=skipExportGlyphs,
            filters=filters,
            instantiator=instantiator,
            **kwargs,
        )
        self.flattenComponents = flattenComponents
        self.convertCubics = convertCubics
        self._conversionErrors = [
            (conversionError or DEFAULT_MAX_ERR)
            * getAttrWithFallback(ufo.info, "unitsPerEm")
            for ufo in self.ufos
        ]
        self._reverseDirection = reverseDirection
        self._rememberCurveType = rememberCurveType
        self.allQuadratic = allQuadratic

    def process(self):
        from fontTools.cu2qu.ufo import fonts_to_quadratic

        # first apply all custom pre-filters
        for funcs in itertools.zip_longest(*self.preFilters):
            self._run(*funcs)

        # TrueType fonts cannot mix contours and components, so pick out all glyphs
        # that have both contours _and_ components.
        needs_decomposition = {
            gname
            for glyphSet in self.glyphSets
            for gname, glyph in glyphSet.items()
            if len(glyph) > 0 and glyph.components
        }
        # Variable fonts can only variate glyf components' x or y offsets, not their
        # 2x2 transformation matrix; decompose of these don't match across masters
        self.check_for_nonmatching_components(needs_decomposition)
        if needs_decomposition:
            self._run(DecomposeComponentsIFilter(include=needs_decomposition))

        # then apply all default filters
        for funcs in itertools.zip_longest(*self.defaultFilters):
            self._run(*funcs)

        if self.convertCubics:
            if fonts_to_quadratic(
                self.glyphSets,
                max_err=self._conversionErrors,
                reverse_direction=self._reverseDirection,
                dump_stats=True,
                remember_curve_type=self._rememberCurveType and self.inplace,
                all_quadratic=self.allQuadratic,
            ):
                self._update_instantiator()
        elif self._reverseDirection:
            from ufo2ft.filters.reverseContourDirection import (
                ReverseContourDirectionFilter,
            )

            self._run(ReverseContourDirectionFilter(include=lambda g: len(g)))

        if self.flattenComponents:
            from ufo2ft.filters.flattenComponents import FlattenComponentsIFilter

            self._run(FlattenComponentsIFilter(include=lambda g: len(g.components)))

        # finally apply all custom post-filters
        for funcs in itertools.zip_longest(*self.postFilters):
            self._run(*funcs)

        return self.glyphSets

    def check_for_nonmatching_components(self, needs_decomposition):
        # Look through all the glyphsets and if we find any glyphs
        # where the transforms don't match across masters, we add it
        # to the needs_decomposition list. See #507

        all_glyphs = set.union(*[set(x.keys()) for x in self.glyphSets])

        for glyph in all_glyphs:
            if glyph in needs_decomposition:
                continue  # We know there's an issue here
            layers = [
                glyphset[glyph] for glyphset in self.glyphSets if glyph in glyphset
            ]

            # Skip early if there aren't any components
            component_counts = [len(layer.components) for layer in layers]
            if not any(component_counts):
                continue

            # Other bits of the system will check for incompatible construction,
            # we just want to stay alive.
            for component_index in range(0, min(component_counts)):
                # We only care about the two-by-twos; translations can differ
                transforms = [
                    layer.components[component_index].transformation[0:4]
                    for layer in layers
                ]

                if any(transform != transforms[0] for transform in transforms):
                    needs_decomposition.add(glyph)
                    break


class OTFInterpolatablePreProcessor(BaseInterpolatablePreProcessor):
    """Interpolatable pre-processor for CFF-flavored fonts.

    By default, besides any user-defined custom pre/post filters, this decomposes
    all composite glyphs, which aren't a thing in PostScript outlines.

    Unlike the non-interpolatable OTFPreProcessor, overlaps are *not* removed as
    that could make outlines incompatible for interpolation.
    """

    def initDefaultFilters(self, **kwargs):
        filterses = super().initDefaultFilters(**kwargs)
        # this interpolatable filter will only run once on all the glyphSets,
        # (see _try_as_interpolatable_filter)
        decompose = DecomposeComponentsIFilter()
        for filters in filterses:
            filters.append(decompose)
        return filterses
