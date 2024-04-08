from __future__ import annotations

import logging
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING, FrozenSet, Tuple

from fontTools.misc.loggingTools import Timer

from ufo2ft.util import (
    _getNewGlyphFactory,
    _GlyphSet,
    _LazyFontName,
    getMaxComponentDepth,
    zip_strict,
)

if TYPE_CHECKING:
    from typing import Any, TypeAlias

    from ufoLib2.objects import Font, Glyph

    from ufo2ft.instantiator import Instantiator, InterpolatedLayer

# reuse the "ufo2ft.filters" logger
logger = logging.getLogger("ufo2ft.filters")

# library-level logger specialized for timing info which apps like fontmake
# can selectively configure
timing_logger = logging.getLogger("ufo2ft.timer")


class BaseFilter:
    # tuple of strings listing the names of required positional arguments
    # which will be set as attributes of the filter instance
    _args = ()

    # dictionary containing the names of optional keyword arguments and
    # their default values, which will be set as instance attributes
    _kwargs = {}

    # pre-filter when True, post-filter when False, meaning before or after default
    # filters
    _pre = False

    def __init__(self, *args, **kwargs):
        self.options = options = SimpleNamespace()

        num_required = len(self._args)
        num_args = len(args)
        # process positional arguments as keyword arguments
        if num_args < num_required:
            args = (
                *args,
                *(kwargs.pop(a) for a in self._args[num_args:] if a in kwargs),
            )
            num_args = len(args)
            duplicated_args = [k for k in self._args if k in kwargs]
            if duplicated_args:
                num_duplicated = len(duplicated_args)
                raise TypeError(
                    "got {} duplicated positional argument{}: {}".format(
                        num_duplicated,
                        "s" if num_duplicated > 1 else "",
                        ", ".join(duplicated_args),
                    )
                )
        # process positional arguments
        if num_args < num_required:
            missing = [repr(a) for a in self._args[num_args:]]
            num_missing = len(missing)
            raise TypeError(
                "missing {} required positional argument{}: {}".format(
                    num_missing, "s" if num_missing > 1 else "", ", ".join(missing)
                )
            )
        elif num_args > num_required:
            extra = [repr(a) for a in args[num_required:]]
            num_extra = len(extra)
            raise TypeError(
                "got {} unsupported positional argument{}: {}".format(
                    num_extra, "s" if num_extra > 1 else "", ", ".join(extra)
                )
            )
        for key, value in zip(self._args, args):
            setattr(options, key, value)

        # process optional keyword arguments
        for key, default in self._kwargs.items():
            setattr(options, key, kwargs.pop(key, default))

        # process special pre argument
        self.pre = kwargs.pop("pre", self._pre)

        # process special include/exclude arguments
        include = kwargs.pop("include", None)
        exclude = kwargs.pop("exclude", None)
        if include is not None and exclude is not None:
            raise ValueError("'include' and 'exclude' arguments are mutually exclusive")
        if callable(include):
            # 'include' can be a function (e.g. lambda) that takes a
            # glyph object and returns True/False based on some test
            self.include = include
            self._include_repr = lambda: repr(include)
        elif include is not None:
            # or it can be a list of glyph names to be included
            included = set(include)
            self.include = lambda g: g.name in included
            self._include_repr = lambda: repr(include)
        elif exclude is not None:
            # alternatively one can provide a list of names to not include
            excluded = set(exclude)
            self.include = lambda g: g.name not in excluded
            self._exclude_repr = lambda: repr(exclude)
        else:
            # by default, all glyphs are included
            self.include = lambda g: True

        # raise if any unsupported keyword arguments
        if kwargs:
            num_left = len(kwargs)
            raise TypeError(
                "got {}unsupported keyword argument{}: {}".format(
                    "an " if num_left == 1 else "",
                    "s" if len(kwargs) > 1 else "",
                    ", ".join(f"'{k}'" for k in kwargs),
                )
            )

        # run the filter's custom initialization code
        self.start()

    def __repr__(self):
        items = []
        if self._args:
            items.append(
                ", ".join(repr(getattr(self.options, arg)) for arg in self._args)
            )
        if self._kwargs:
            items.append(
                ", ".join(
                    "{}={!r}".format(k, getattr(self.options, k))
                    for k in sorted(self._kwargs)
                )
            )
        if hasattr(self, "_include_repr"):
            items.append(f"include={self._include_repr()}")
        elif hasattr(self, "_exclude_repr"):
            items.append(f"exclude={self._exclude_repr()}")
        return "{}({})".format(type(self).__name__, ", ".join(items))

    def start(self):
        """Subclasses can perform here custom initialization code."""
        pass

    def set_context(self, font, glyphSet):
        """Populate a `self.context` namespace, which is reset before each
        new filter call.

        Subclasses can override this to provide contextual information
        which depends on other data in the font that is not available in
        the glyphs objects currently being filtered, or set any other
        temporary attributes.

        The default implementation simply sets the current font and glyphSet,
        and initializes an empty set that keeps track of the names of the
        glyphs that were modified.

        Returns the namespace instance.
        """
        self.context = SimpleNamespace(font=font, glyphSet=glyphSet)
        self.context.modified = set()
        proto = font.layers.defaultLayer.instantiateGlyphObject()
        self.context.glyphFactory = _getNewGlyphFactory(proto)
        return self.context

    def filter(self, glyph):
        """This is where the filter is applied to a single glyph.
        Subclasses must override this method, and return True
        when the glyph was modified.
        """
        raise NotImplementedError

    @property
    def name(self):
        return self.__class__.__name__

    def __call__(self, font, glyphSet=None):
        """Run this filter on all the included glyphs.
        Return the set of glyph names that were modified, if any.

        If `glyphSet` (dict) argument is provided, run the filter on
        the glyphs contained therein (which may be copies).
        Otherwise, run the filter in-place on the font's default
        glyph set.
        """
        fontName = _LazyFontName(font)
        if glyphSet is not None and getattr(glyphSet, "name", None):
            logger.info("Running %s on %s-%s", self.name, fontName, glyphSet.name)
        else:
            logger.info("Running %s on %s", self.name, fontName)

        if glyphSet is None:
            glyphSet = _GlyphSet.from_layer(font)

        context = self.set_context(font, glyphSet)

        filter_ = self.filter
        include = self.include
        modified = context.modified

        # process composite glyphs in decreasing component depth order (i.e. composites
        # with more deeply nested components before shallower ones) to avoid
        # order-dependent interferences while filtering glyphs with nested components
        # https://github.com/googlefonts/ufo2ft/issues/621
        orderedGlyphs = sorted(
            glyphSet.keys(), key=lambda g: -getMaxComponentDepth(glyphSet[g], glyphSet)
        )

        with Timer() as t:
            for glyphName in orderedGlyphs:
                if glyphName in modified:
                    continue
                glyph = glyphSet[glyphName]
                if include(glyph) and filter_(glyph):
                    modified.add(glyphName)

        num = len(modified)
        if num > 0:
            timing_logger.debug(
                "Took %.3fs to run %s on %d glyph%s",
                t,
                self.name,
                len(modified),
                "" if num == 1 else "s",
            )
        return modified

    @classmethod
    def getInterpolatableFilterClass(cls) -> BaseIFilter | None:
        """Return interpolatable filter class if one is found in the same module.

        We search for a class with the same name and the 'IFilter' suffix
        (where the 'I' stands for "interpolatable").

        Subclasses can override this if they wish to use a different class name
        or module.
        """
        module = sys.modules[cls.__module__]
        filter_name = cls.__name__
        if filter_name.endswith("Filter"):
            filter_name = filter_name[:-6]
        ifilter_name = f"{filter_name}IFilter"
        return getattr(module, ifilter_name, None)


HashableLocation: TypeAlias = FrozenSet[Tuple[str, float]]


class BaseIFilter(BaseFilter):
    """Interpolatable variant that zips through mutliple glyphs at a time."""

    def set_context(
        self,
        fonts: list[Font],
        glyphSets: list[dict[str, Glyph]],
        instantiator: Instantiator | None = None,
        **kwargs: dict[str, Any],
    ) -> SimpleNamespace:
        """Populate a `self.context` namespace, which is reset before each
        new filter call.

        Subclasses can override this to provide contextual information
        which depends on other data in the fonts that is not available in
        the glyphs objects currently being filtered, or set any other
        temporary attributes.

        The default implementation simply sets the current fonts, glyphSets,
        and optional instantiator and initializes an empty set that keeps track
        of the names of the glyphs that were modified.

        Any extra keyword arguments are passed to the context namespace.

        Returns the namespace instance.
        """
        assert len(fonts) == len(glyphSets)
        self.context = SimpleNamespace(
            fonts=fonts,
            glyphSets=glyphSets,
            instantiator=instantiator,
            **kwargs,
        )
        self.context.modified = set()
        # this is used to memoize locationsFromComponentGlyphs method below, to avoid
        # redoing the same work over and over again (especially when font has loads of
        # masters and many nested components).
        self.context.componentLocations = {}
        proto = fonts[0].layers.defaultLayer.instantiateGlyphObject()
        self.context.glyphFactory = _getNewGlyphFactory(proto)
        return self.context

    def filter(self, glyphName: str, glyphs: list) -> bool:
        """This is where the filter is applied to a set of interpolatable glyphs.

        Subclasses must override this method, and return True
        when the glyph was modified.
        """
        raise NotImplementedError

    def __call__(
        self,
        fonts: list[Font],
        glyphSets: list[dict[str, Glyph]] | None = None,
        instantiator: Instantiator | None = None,
        **kwargs: dict[str, Any],
    ) -> set[str]:
        """Run this filter on all the included glyphs from the given glyphSets.
        Return the set of glyph names that were modified, if any.

        If `glyphSets` (list[dict]) argument is provided, run the filter on
        the glyphs contained therein (which may be copies).
        Otherwise, run the filter in-place on the fonts' default
        glyph sets.

        The `instantiator` optional argument allows interpolatable filters to
        generate glyph instances on demand at any location in the designspace.

        Any extra keyword arguments are passed on to the `set_context` method.
        """
        logger.info("Running interpolatable %s", self.name)

        if glyphSets is None:
            glyphSets = [_GlyphSet.from_layer(font) for font in fonts]

        context = self.set_context(fonts, glyphSets, instantiator, **kwargs)

        filter_ = self.filter
        include = self.include
        modified = context.modified

        # process composite glyphs in decreasing component depth order (i.e. composites
        # with more deeply nested components before shallower ones) to avoid
        # order-dependent interferences while filtering glyphs with nested components
        # https://github.com/googlefonts/ufo2ft/issues/621
        allGlyphNames = set.union(*(set(glyphSet.keys()) for glyphSet in glyphSets))

        def comp_depth(g):
            for glyphSet in glyphSets:
                if g in glyphSet:
                    return -getMaxComponentDepth(glyphSet[g], glyphSet)
            raise AssertionError

        orderedGlyphs = sorted(allGlyphNames, key=comp_depth)

        with Timer() as t:
            for glyphName in orderedGlyphs:
                if glyphName in modified:
                    continue
                glyphs = [
                    glyphSet[glyphName]
                    for glyphSet in glyphSets
                    if glyphName in glyphSet
                ]
                if any(include(g) for g in glyphs) and filter_(glyphName, glyphs):
                    modified.add(glyphName)

        num = len(modified)
        if num > 0:
            timing_logger.debug(
                "Took %.3fs to run %s on %d glyph%s",
                t,
                self.name,
                len(modified),
                "" if num == 1 else "s",
            )
        return modified

    @classmethod
    def getInterpolatableFilterClass(cls) -> "BaseIFilter" | None:
        """Return the same class as self."""
        return cls  # no-op

    def getDefaultFont(self) -> Font:
        if self.context.instantiator is not None:
            return self.context.fonts[self.context.instantiator.default_source_idx]
        else:
            # as good a guess as any...
            return self.context.fonts[0]

    def getDefaultGlyphSet(self) -> dict[str, Glyph]:
        """Return the current glyphSet corresponding to the default location."""
        if self.context.instantiator is not None:
            default_idx = self.context.instantiator.default_source_idx
            for i, glyphSet in enumerate(self.context.glyphSets):
                if i == default_idx:
                    return glyphSet
            else:
                raise AssertionError("No default source?!")
        else:
            # we don't have enough info to know which glyphSet corresponds
            # to the default source location so we just guess it's going to
            # be the larger one given it contains all glyphs by definition.
            return max(self.context.glyphSets, key=lambda glyphSet: len(glyphSet))

    def getInterpolatedLayers(self) -> list[InterpolatedLayer] | list[None]:
        """Return InterpolatedLayers at source locations or Nones if no Instantiator."""
        if self.context.instantiator is not None:
            return self.context.instantiator.interpolated_layers
        else:
            return [None] * len(self.context.glyphSets)

    @staticmethod
    def hashableLocation(location: dict[str, float]) -> HashableLocation:
        """Convert (normalized) location dict to a hashable set of tuples."""
        return frozenset((k, v) for k, v in location.items() if v != 0.0)

    def glyphSourceLocations(self, glyphName) -> set[HashableLocation]:
        """Return locations of all the sources that have a glyph."""
        assert self.context.instantiator is not None
        return {
            self.hashableLocation(location)
            for glyphSet, location in zip_strict(
                self.context.glyphSets, self.context.instantiator.source_locations
            )
            if glyphName in glyphSet
        }

    def locationsFromComponentGlyphs(
        self,
        glyphName: str,
        include: set[str] | None = None,
    ) -> set[HashableLocation]:
        """Return locations from all the components' base glyphs, recursively."""
        logger.debug("Gathering all locations from component glyphs: %s", glyphName)
        assert self.context.instantiator is not None
        locations = set()
        cache = self.context.componentLocations
        for glyphSet in self.context.glyphSets:
            if glyphName in glyphSet:
                glyph = glyphSet[glyphName]
                for component in glyph.components:
                    baseGlyph = component.baseGlyph
                    if include is None or baseGlyph in include:
                        locations |= self.glyphSourceLocations(baseGlyph)
                        # using ternary operator instead of cache.setdefault because
                        # the latter always evaluates the second argument, whereas
                        # I want it to be lazy to avoid recursing too often.
                        locations |= (
                            cache[baseGlyph]
                            if baseGlyph in cache
                            else cache.setdefault(
                                baseGlyph,
                                self.locationsFromComponentGlyphs(baseGlyph, include),
                            )
                        )
        return locations

    def ensureCompositeDefinedAtComponentLocations(
        self,
        glyphName: str,
        include: set[str] | None = None,
    ):
        """Ensure the composite glyph is defined at all its components' locations.

        The Instantiator is used to interpolate the glyph at the missing locations.
        If we have no Instantiator, we can't interpolate so this does nothing.
        """
        if self.context.instantiator is None:
            return

        haveLocations = self.glyphSourceLocations(glyphName)
        needLocations = self.locationsFromComponentGlyphs(glyphName, include)
        locationsToAdd = needLocations - haveLocations
        if locationsToAdd:
            for glyphSet, interpolatedLayer in zip_strict(
                self.context.glyphSets, self.context.instantiator.interpolated_layers
            ):
                if self.hashableLocation(interpolatedLayer.location) in locationsToAdd:
                    assert glyphName not in glyphSet
                    logger.debug(
                        "Interpolating composite glyph %r at %s",
                        glyphName,
                        interpolatedLayer.location,
                    )
                    glyphSet[glyphName] = interpolatedLayer[glyphName]
