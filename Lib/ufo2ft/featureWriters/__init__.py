from .baseFeatureWriter import BaseFeatureWriter
from .kernFeatureWriter import KernFeatureWriter
from .markFeatureWriter import MarkFeatureWriter

import importlib
from inspect import isclass
import logging


__all__ = [
    "BaseFeatureWriter",
    "KernFeatureWriter",
    "MarkFeatureWriter",
    "loadFeatureWriters",
]

logger = logging.getLogger(__name__)

FEATURE_WRITERS_KEY = "com.github.googlei18n.ufo2ft.featureWriters"


def loadFeatureWriters(ufo):
    """Check UFO lib for key "com.github.googlei18n.ufo2ft.featureWriters",
    containing a list of dicts, each having the following key/value pairs:
    For example:

      {
        "module": "myTools.featureWriters",  # default: ufo2ft.featureWriters
        "class": "MyKernFeatureWriter",  # required
        "options": {"doThis": False, "doThat": True},
      }

    Import each feature writer class from the specified module (default is
    the built-in ufo2ft.featureWriters), and instantiate it with the given
    'options' dict.

    Return the list of feature writer objects.
    If the 'featureWriters' key is missing from the UFO lib, return None.

    If an exception occurs while loading or initializing a feature writer,
    log the exception message and continue.
    """
    if FEATURE_WRITERS_KEY not in ufo.lib:
        return None
    writers = []
    for wdict in ufo.lib[FEATURE_WRITERS_KEY]:
        try:
            moduleName = wdict.get("module", __name__)
            className = wdict["class"]
            options = wdict.get("options", {})
            if not isinstance(options, dict):
                raise TypeError(
                    "expected options dict, found %s" % type(options).__name__
                )
            module = importlib.import_module(moduleName)
            klass = getattr(module, className)
            if not (isclass(klass) and hasattr(klass, "write")):
                raise TypeError(
                    "expected feature writer class, found %s"
                    % type(klass).__name__
                )
            writer = klass(**options)
        except (KeyError, ImportError, AttributeError, TypeError, ValueError):
            logger.exception("failed to load feature writer: %r", wdict)
            continue
        writers.append(writer)
    return writers
