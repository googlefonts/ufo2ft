from __future__ import (
    print_function, division, absolute_import, unicode_literals)

import importlib
import logging
from fontTools.misc.loggingTools import Timer


UFO2FT_FILTERS_KEY = "com.github.googlei18n.ufo2ft.filters"

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
    className = filterName[0].upper() + filterName[1:] + "Filter"
    return getattr(module, className)


def loadFilters(ufo):
    """Parse custom filters from the ufo's lib.plist. Return two lists,
    one for the filters that are applied before decomposition of composite
    glyphs, another for the filters that are applied after decomposition.
    """
    preFilters, postFilters = [], []
    for filterDict in ufo.lib.get(UFO2FT_FILTERS_KEY, []):
        try:
            filterClass = getFilterClass(filterDict["name"])
        except (ImportError, AttributeError):
            from pprint import pformat
            logger.exception("Failed to load filter: %s", pformat(filterDict))
            continue
        filterObj = filterClass(include=filterDict.get("include"),
                                exclude=filterDict.get("exclude"),
                                *filterDict.get("args", []),
                                **filterDict.get("kwargs", {}))
        if filterDict.get("pre"):
            preFilters.append(filterObj)
        else:
            postFilters.append(filterObj)
    return preFilters, postFilters


class BaseFilter(object):

    # tuple of strings listing the names of required positional arguments
    # which will be set as attributes of the filter instance
    _args = ()

    # dictionary containing the names of optional keyword arguments and
    # their default values, which will be set as instance attributes
    _kwargs = {}

    def __init__(self, *args, **kwargs):
        # process positional arguments
        num_required = len(self._args)
        num_args = len(args)
        if num_args < num_required:
            missing = [repr(a) for a in self._args[num_args:]]
            num_missing = len(missing)
            raise TypeError(
                "missing {0} required positional argument{1}: {2}".format(
                    num_missing,
                    "s" if num_missing > 1 else "",
                    ", ".join(missing)))
        elif num_args > num_required:
            extra = [repr(a) for a in args[num_required:]]
            num_extra = len(extra)
            raise TypeError(
                "got {0} unsupported positional argument{1}: {2}".format(
                    num_extra,
                    "s" if num_extra > 1 else "",
                    ", ".join(extra)))
        for option, value in zip(self._args, args):
            setattr(self, option, value)

        # process optional keyword arguments
        for option, default in self._kwargs.items():
            setattr(self, option, kwargs.pop(option, default))

        # process special include/exclude arguments
        include = kwargs.pop('include', None)
        exclude = kwargs.pop('exclude', None)
        if include is not None and exclude is not None:
            raise ValueError(
                "'include' and 'exclude' arguments are mutually exclusive")
        if callable(include):
            # 'include' can be a function (e.g. lambda) that takes a
            # glyph object and returns True/False based on some test
            self.include = include
        elif include is not None:
            # or it can be a list of glyph names to be included
            included = set(include)
            self.include = lambda g: g.name in included
        elif exclude is not None:
            # alternatively one can provide a list of names to not include
            excluded = set(exclude)
            self.include = lambda g: g.name not in excluded
        else:
            # by default, all glyphs are included
            self.include = lambda g: True

        # raise if any unsupported keyword arguments
        if kwargs:
            num_left = len(kwargs)
            raise TypeError(
                "got {0}unsupported keyword argument{1}: {2}".format(
                    "an " if num_left == 1 else "",
                    "s" if len(kwargs) > 1 else "",
                    ", ".join("'{}'".format(k) for k in kwargs)))

        # run the filter's custom initialization code
        self.start()

    def __repr__(self):
        items = ("{0}={1!r}".format(k, v)
                 for k, v in sorted(self.__dict__.items())
                 if v is not None and not k.startswith("_"))
        return "{0}({1})".format(type(self).__name__, ", ".join(items))

    def start(self):
        """ Subclasses can perform here custom initialization code.
        """
        pass

    def filter(self, glyph, glyphSet=None):
        """ This is where the filter is applied to a single glyph.
        Subclasses must override this method, and return True
        when the glyph was modified.
        """
        raise NotImplementedError

    @property
    def name(self):
        return self.__class__.__name__

    def __call__(self, glyphSet):
        """ Run this filter on all the included glyphs.
        Return the set of glyphs that were modified, if any.
        """
        filter_ = self.filter
        include = self.include
        modified = set()

        with Timer() as t:
            for glyphName in glyphSet.keys():
                glyph = glyphSet[glyphName]
                if include(glyph) and filter_(glyph, glyphSet):
                    modified.add(glyphName)

        logger.debug("Took %.3fs to run %s on %d glyphs",
                     t, self.name, len(modified))
        return modified
