from __future__ import (
    print_function, division, absolute_import, unicode_literals)
from fontTools.misc.py23 import SimpleNamespace


_SUPPORTED_MODES = ("skip", "append")


class BaseFeatureWriter(object):
    """Abstract features writer.

    The 'features' class attribute defines the list of all the features
    that this writer supports. If you want to only write some of the
    available features you can provide a smaller list to 'features'
    constructor argument. By the default all the features supported by
    this writer will be outputted.

    There are currently two possible writing modes:
    1) "skip" (default) will not write anything if any of the features
       listed is already present;
    2) "append" will add additional lookups to an existing feature,
       if it's already present.

    The 'options' class attribute contains a mapping of option
    names with their default values. These can be overridden on an
    instance by passing keword arguments to the constructor.
    """

    features = []
    mode = "skip"
    options = {}

    def __init__(self, features=None, mode=None, linesep="\n", **kwargs):
        if features is not None:
            default_features = set(self.__class__.features)
            self.features = []
            for feat in features:
                if feat not in default_features:
                    raise ValueError(feat)
                self.features.append(feat)

        if mode is not None:
            if mode not in _SUPPORTED_MODES:
                raise ValueError(mode)
            self.mode = mode

        self.linesep = linesep

        options = dict(self.__class__.options)
        for k in kwargs:
            if k not in options:
                raise TypeError("unsupported keyword argument: %r" % k)
            options[k] = kwargs[k]
        self.options = SimpleNamespace(**options)

    def set_context(self, font):
        """ Populate a `self.context` namespace, which is reset before each
        new call to `_write` method.

        Subclasses can override this to provide contextual information
        which depends on other data in the font that is not available in
        the glyphs objects currently being filtered, or set any other
        temporary attributes.

        The default implementation simply sets the current font, and
        returns the namepace instance.
        """
        self.context = SimpleNamespace(font=font)
        return self.context

    def write(self, font):
        """Write features and class definitions for this font.

        Resets the `self.context` and delegates to ``self._write()` method.

        Returns a string containing the text of the features that are
        listed in `self.features`.
        """
        self.set_context(font)
        return self._write()

    def _write(self):
        """Subclasses must override this."""
        raise NotImplementedError

    @staticmethod
    def liststr(glyphs):
        """Return string representation of a list of glyph names."""
        return "[%s]" % " ".join(glyphs)
