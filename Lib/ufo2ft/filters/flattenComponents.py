from __future__ import annotations

import logging

from fontTools.misc.transform import Transform

from ufo2ft.filters import BaseFilter, BaseIFilter
from ufo2ft.util import zip_strict

logger = logging.getLogger(__name__)


class FlattenComponentsFilter(BaseFilter):
    """Replace nested components with their referents so that max depth is 1."""

    def __call__(self, font, glyphSet=None):
        modified = super().__call__(font, glyphSet)
        if modified:
            logger.info("Flattened composite glyphs: %i" % len(modified))
        return modified

    def filter(self, glyph):
        return _flattenGlyphComponents(glyph, self.context.glyphSet)


class FlattenComponentsIFilter(BaseIFilter):
    """Interpolatable variant of FlattenComponentsFilter."""

    def __call__(self, fonts, glyphSets=None, instantiator=None, **kwargs):
        modified = super().__call__(fonts, glyphSets, instantiator, **kwargs)
        if modified:
            logger.info("Flattened composite glyphs: %i" % len(modified))
        return modified

    def filter(self, glyphName: str, glyphs: list) -> bool:
        flattened = False
        if not any(glyph.components for glyph in glyphs):
            return flattened

        defaultGlyphSet = self.getDefaultGlyphSet()
        if not any(_haveNestedComponents(g, defaultGlyphSet) for g in glyphs):
            return flattened

        for glyphSet, interpolatedLayer in zip_strict(
            self.context.glyphSets, self.getInterpolatedLayers()
        ):
            glyph = glyphSet.get(glyphName)
            if glyph is not None:
                flattened = _flattenGlyphComponents(
                    glyph, interpolatedLayer or glyphSet
                )

        return flattened


def _isSimpleOrMixed(glyph):
    return not glyph.components or len(glyph) > 0


def _haveNestedComponents(glyph, glyphSet):
    return not _isSimpleOrMixed(glyph) and any(
        glyphSet[compo.baseGlyph].components
        for compo in glyph.components
        if compo.baseGlyph in glyphSet
    )


def _flattenGlyphComponents(glyph, glyphSet):
    flattened = False
    if not glyph.components:
        return flattened
    components = list(glyph.components)
    glyph.clearComponents()
    pen = glyph.getPointPen()
    for comp in components:
        flattened_tuples = _flattenComponent(glyphSet, comp, found_in=glyph)
        if flattened_tuples[0] != (comp.baseGlyph, comp.transformation):
            flattened = True
        for flattened_tuple in flattened_tuples:
            pen.addComponent(*flattened_tuple)
    return flattened


def _flattenComponent(glyphSet, component, found_in):
    """Returns a list of tuples (baseGlyph, transform) of nested component."""
    if component.baseGlyph not in glyphSet:
        raise ValueError(
            f"Could not find component '{component.baseGlyph}' used in '{found_in.name}'"
        )

    glyph = glyphSet[component.baseGlyph]
    # Any contour will cause components to be decomposed
    if _isSimpleOrMixed(glyph):
        transformation = Transform(*component.transformation)
        return [(component.baseGlyph, transformation)]

    all_flattened_components = []
    for nested in glyph.components:
        flattened_components = _flattenComponent(glyphSet, nested, found_in=glyph)
        for i, (name, tr) in enumerate(flattened_components):
            flat_tr = Transform(*component.transformation)
            flat_tr = flat_tr.translate(tr.dx, tr.dy)
            flat_tr = flat_tr.transform((tr.xx, tr.xy, tr.yx, tr.yy, 0, 0))
            flattened_components[i] = (name, flat_tr)
        all_flattened_components.extend(flattened_components)
    return all_flattened_components
