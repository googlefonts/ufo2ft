from fontTools.misc.transform import Identity

from ufo2ft.filters.decomposeComponents import (
    DecomposeComponentsFilter,
    DecomposeComponentsIFilter,
)

IDENTITY_2x2 = Identity[:4]


def _isTransformed(component):
    return component.transformation[:4] != IDENTITY_2x2


class DecomposeTransformedComponentsFilter(DecomposeComponentsFilter):
    def filter(self, glyph):
        if any(_isTransformed(c) for c in glyph.components):
            return super().filter(glyph)
        return False


class DecomposeTransformedComponentsIFilter(DecomposeComponentsIFilter):
    def filter(self, glyphName, glyphs):
        # We decomposes the glyph in *all* masters if any contains a transformed
        # component: https://github.com/googlefonts/ufo2ft/issues/507
        if not any(any(_isTransformed(c) for c in g.components) for g in glyphs):
            return False
        return super().filter(glyphName, glyphs)
