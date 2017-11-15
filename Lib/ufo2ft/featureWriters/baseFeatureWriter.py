from __future__ import (
    print_function, division, absolute_import, unicode_literals)


class BaseFeatureWriter(object):
    """Abstract features writer"""

    def __init__(self, font, features=()):
        self.font = font
        self.features = features

    def write(self, **kwargs):
        """Write features and class definitions"""
        raise NotImplementedError

    @staticmethod
    def liststr(glyphs):
        """Return string representation of a list of glyph names."""
        return "[%s]" % " ".join(glyphs)
