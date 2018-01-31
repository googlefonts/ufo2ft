from __future__ import (
    print_function, division, absolute_import, unicode_literals)
from fontTools.misc.py23 import SimpleNamespace


class BaseFeatureWriter(object):
    """Abstract features writer.

    The `supportedFeatures` class attribute defines the list of all
    the features that this writer supports. By the default all the features
    supported by the writer will be outputted.
    If you want to only write some of the available features you can provide
    a smaller set with the `features` keyword argument of the `write` method.

    The `options` class attribute contains a mapping of option
    names with their default values. These can be overridden on an
    instance by passing keyword arguments to the constructor.
    """

    supportedFeatures = ()
    options = {}

    def __init__(self, **kwargs):
        options = dict(self.__class__.options)
        for k in kwargs:
            if k not in options:
                raise TypeError("unsupported keyword argument: %r" % k)
            options[k] = kwargs[k]
        self.options = SimpleNamespace(**options)

    def set_context(self, font, feaFile, features=None):
        """ Populate a temporary `self.context` namespace, which is reset
        before each new call to `_write` method, and return the object.

        Subclasses can use this to store contextual information related to
        the font currently being processed, or set any other temporary
        attributes.
        """
        if features is None:
            # generate all supported features by default
            features = set(self.supportedFeatures)
        self.context = SimpleNamespace(
            font=font, feaFile=feaFile, features=features)
        return self.context

    def write(self, font, feaFile, features=None):
        """Write features and class definitions for this font.

        Resets the `self.context` and delegates to ``self._write()` method.

        Returns a string containing the text of the features that are
        listed in `self.features`.
        """
        if features is not None:
            features = features.intersection(self.supportedFeatures)
            if not features:
                # none included, nothing to do
                return False

        self.set_context(font, feaFile, features)
        try:
            result = self._write()
            if not result:
                return False
            feaFile.statements.extend(result)
            return bool(result)
        finally:
            del self.context

    def _write(self):
        """Subclasses must override this."""
        raise NotImplementedError
