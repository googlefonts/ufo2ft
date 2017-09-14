from __future__ import (
    print_function, division, absolute_import, unicode_literals)


def liststr(glyphs):
    """Return string representation of a list of glyph names."""
    return "[%s]" % " ".join(glyphs)


class BaseFeatureWriter(object):
    """Abstract features writer"""

    def __init__(self, font, features=(), scriptLangs=()):
        self.font = font
        self.features = features
        self._scriptLangs = scriptLangs

    def write(self, **kwargs):
        """Write features and class definitions"""
        raise NotImplementedError

    def _get_scriptLangs(self):
        if self._scriptLangs:
            return self._scriptLangs
        else:
            return {"DFLT": ("dflt", )}

    scriptLangs = property(_get_scriptLangs)

    def scriptLangsLabel(self):
        label = []
        for script in self.scriptLangs:
            langs = "_".join(lang for lang in self.scriptLangs[script])
            label.append(script + "_" + langs)
        return "_".join(label)
