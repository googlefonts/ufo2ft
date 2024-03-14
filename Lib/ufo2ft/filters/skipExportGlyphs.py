from __future__ import annotations

from ufo2ft.filters import BaseFilter, BaseIFilter
from ufo2ft.util import decomposeCompositeGlyph, zip_strict


class SkipExportGlyphsFilter(BaseFilter):
    """Subset a glyphSet while decomposing references to pruned component glyphs."""

    _pre = True
    _args = ("skipExportGlyphs",)

    def start(self):
        self.options.skipExportGlyphs = frozenset(self.options.skipExportGlyphs)

    def filter(self, glyph) -> bool:
        if not glyph.components or self.options.skipExportGlyphs.isdisjoint(
            comp.baseGlyph for comp in glyph.components
        ):
            return False

        # decomposeNested=False because at this stage we are only interested
        # in pruning component references to specific non-export glyphs, not
        # decomposing entire composite glyphs per se; it's conceivable that
        # after a component is replaced by its direct referent and the latter
        # in turn only comprises components, the parent can remain a composite
        # glyph and need not be fully decomposed to contours; any further
        # decompositions (e.g. of mixed glyphs) can be performed later.
        decomposeCompositeGlyph(
            glyph,
            self.context.glyphSet,
            decomposeNested=False,
            include=self.options.skipExportGlyphs,
        )
        return True

    def __call__(self, font, glyphSet=None):
        if not self.options.skipExportGlyphs:
            return self.context.modified  # nothing to do

        modified = super().__call__(font, glyphSet)

        # now that all component references to non-export glyphs have been removed,
        # the glyphSet can be subset in-place
        glyphSet = self.context.glyphSet
        for glyphName in self.options.skipExportGlyphs:
            if glyphName in glyphSet:
                del glyphSet[glyphName]
                # technically this glyph was 'removed' rather than 'modified' but
                # filters only return one set...
                modified.add(glyphName)

        return modified


class SkipExportGlyphsIFilter(BaseIFilter):
    """Interpolatable variant of SkipExportGlyphsFilter."""

    _pre = True
    _args = ("skipExportGlyphs",)

    def start(self):
        self.options.skipExportGlyphs = frozenset(self.options.skipExportGlyphs)

    def filter(self, glyphName: str, glyphs: list) -> bool:
        if not any(glyph.components for glyph in glyphs) or all(
            self.options.skipExportGlyphs.isdisjoint(
                comp.baseGlyph for comp in glyph.components
            )
            for glyph in glyphs
        ):
            return False

        self.ensureCompositeDefinedAtComponentLocations(
            glyphName, include=self.options.skipExportGlyphs
        )

        for glyphSet, interpolatedLayer in zip_strict(
            self.context.glyphSets, self.getInterpolatedLayers()
        ):
            glyph = glyphSet.get(glyphName)
            if glyph is not None:
                decomposeCompositeGlyph(
                    glyph,
                    interpolatedLayer or glyphSet,
                    decomposeNested=False,
                    include=self.options.skipExportGlyphs,
                )
        return True

    def __call__(self, fonts, glyphSets=None, instantiator=None, **kwargs):
        if not self.options.skipExportGlyphs:
            return self.context.modified  # nothing to do

        modified = super().__call__(
            fonts, glyphSets, instantiator=instantiator, **kwargs
        )

        for glyphName in self.options.skipExportGlyphs:
            for glyphSet in self.context.glyphSets:
                if glyphName in glyphSet:
                    del glyphSet[glyphName]
                    # mark removed glyphs among the 'modified' ones
                    modified.add(glyphName)

        return modified
