import importlib
import logging
from inspect import getfullargspec, isclass

from ufo2ft.constants import FILTERS_KEY
from ufo2ft.util import _loadPluginFromString

from .base import BaseFilter, BaseIFilter
from .cubicToQuadratic import CubicToQuadraticFilter
from .decomposeComponents import DecomposeComponentsFilter, DecomposeComponentsIFilter
from .decomposeTransformedComponents import (
    DecomposeTransformedComponentsFilter,
    DecomposeTransformedComponentsIFilter,
)
from .dottedCircle import DottedCircleFilter
from .explodeColorLayerGlyphs import ExplodeColorLayerGlyphsFilter
from .flattenComponents import FlattenComponentsFilter, FlattenComponentsIFilter
from .propagateAnchors import PropagateAnchorsFilter, PropagateAnchorsIFilter
from .removeOverlaps import RemoveOverlapsFilter
from .reverseContourDirection import ReverseContourDirectionFilter
from .skipExportGlyphs import SkipExportGlyphsFilter, SkipExportGlyphsIFilter
from .sortContours import SortContoursFilter
from .transformations import TransformationsFilter

__all__ = [
    "BaseFilter",
    "BaseIFilter",
    "CubicToQuadraticFilter",
    "DecomposeComponentsFilter",
    "DecomposeComponentsIFilter",
    "DecomposeTransformedComponentsFilter",
    "DecomposeTransformedComponentsIFilter",
    "DottedCircleFilter",
    "ExplodeColorLayerGlyphsFilter",
    "FlattenComponentsFilter",
    "FlattenComponentsIFilter",
    "PropagateAnchorsFilter",
    "PropagateAnchorsIFilter",
    "RemoveOverlapsFilter",
    "ReverseContourDirectionFilter",
    "SkipExportGlyphsFilter",
    "SkipExportGlyphsIFilter",
    "SortContoursFilter",
    "TransformationsFilter",
    "loadFilters",
    "loadFilterFromString",
]


logger = logging.getLogger(__name__)


def getFilterClass(filterName, pkg="ufo2ft.filters"):
    """Given a filter name, import and return the filter class.
    By default, filter modules are searched within the ``ufo2ft.filters``
    package.
    """
    # TODO add support for third-party plugin discovery?
    # if filter name is 'Foo Bar', the module should be called 'fooBar'
    filterName = filterName.replace(" ", "")
    moduleName = filterName[0].lower() + filterName[1:]
    module = importlib.import_module(".".join([pkg, moduleName]))
    # if filter name is 'Foo Bar', the class should be called 'FooBarFilter'
    className = filterName[0].upper() + filterName[1:]
    if not className.endswith("Filter"):
        className += "Filter"
    return getattr(module, className)


def loadFilters(ufo):
    """Parse custom filters from the ufo's lib.plist. Return two lists,
    one for the filters that are applied before decomposition of composite
    glyphs, another for the filters that are applied after decomposition.
    """
    preFilters, postFilters = [], []
    for filterDict in ufo.lib.get(FILTERS_KEY, []):
        namespace = filterDict.get("namespace", "ufo2ft.filters")
        try:
            filterClass = getFilterClass(filterDict["name"], namespace)
        except (ImportError, AttributeError):
            from pprint import pformat

            logger.exception("Failed to load filter: %s", pformat(filterDict))
            continue
        filterObj = filterClass(
            *filterDict.get("args", []),
            include=filterDict.get("include"),
            exclude=filterDict.get("exclude"),
            pre=filterDict.get("pre", False),
            **filterDict.get("kwargs", {}),
        )
        if filterObj.pre:
            preFilters.append(filterObj)
        else:
            postFilters.append(filterObj)
    return preFilters, postFilters


def isValidFilter(klass, *bases):
    """Return True if 'klass' is a valid filter class.
    A valid filter class is a class (of type 'type'), that has
    a '__call__' (bound method), with the signature matching the same method
    from the BaseFilter or BaseIFilter classes, respectively:

           def __call__(self, font, glyphSet=None)

           def __call__(self, fonts, glyphSets=None, instantiator=None, **kwargs)
    """
    if not isclass(klass):
        logger.error(f"{klass!r} is not a class")
        return False
    if not callable(klass):
        logger.error(f"{klass!r} is not callable")
        return False
    for baseClass in bases or (BaseFilter, BaseIFilter):
        if (
            getfullargspec(klass.__call__).args
            == getfullargspec(baseClass.__call__).args
        ):
            return True
    logger.error(f"{klass!r} '__call__' method has incorrect signature")
    return False


def loadFilterFromString(spec):
    """Take a string specifying a filter class to load (either a built-in
    filter or one defined in an external, user-defined module), initialize it
    with given options and return the filter object.

    The string must conform to the following notation:
    - an optional python module, followed by '::'
    - a required class name; the class must have a method called 'filter'
      with the same signature as the BaseFilter.
    - an optional list of keyword-only arguments enclosed by parentheses

    Raises ValueError if the string doesn't conform to this specification;
    TypeError if imported name is not a filter class; and ImportError if the
    user-defined module cannot be imported.

    Examples:

    >>> loadFilterFromString("ufo2ft.filters.removeOverlaps::RemoveOverlapsFilter")
    <ufo2ft.filters.removeOverlaps.RemoveOverlapsFilter object at ...>
    """
    return _loadPluginFromString(spec, "ufo2ft.filters", isValidFilter)
