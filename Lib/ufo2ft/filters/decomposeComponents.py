from __future__ import annotations

from typing import TYPE_CHECKING

from ufo2ft.filters import BaseFilter, BaseIFilter
from ufo2ft.util import decomposeCompositeGlyph, zip_strict

if TYPE_CHECKING:
    from ufoLib2.objects import Glyph


class DecomposeComponentsFilter(BaseFilter):
    # pre=True so by default this is run before the RemoveOverlaps filter,
    # in case a component overlaps other contours or components, to ensure
    # the decomposed contours will be merged correctly:
    # https://github.com/googlefonts/gftools/pull/425
    _pre = True

    def filter(self, glyph: Glyph) -> bool:
        if not glyph.components:
            return False
        decomposeCompositeGlyph(glyph, self.context.glyphSet)
        return True


class DecomposeComponentsIFilter(BaseIFilter):
    _pre = True

    def filter(self, glyphName: str, glyphs: list[Glyph]) -> bool:
        if not any(glyph.components for glyph in glyphs):
            return False

        self.ensureCompositeDefinedAtComponentLocations(glyphName)

        for glyphSet, interpolatedLayer in zip_strict(
            self.context.glyphSets, self.getInterpolatedLayers()
        ):
            glyph = glyphSet.get(glyphName)
            if glyph is not None:
                decomposeCompositeGlyph(glyph, interpolatedLayer or glyphSet)
        return True
