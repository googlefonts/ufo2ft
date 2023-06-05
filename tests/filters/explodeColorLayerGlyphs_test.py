"""Comprises tests for the ExplodeColorLayerGlyphsFilter filter."""

from pathlib import Path

import pytest

from ufo2ft.filters.explodeColorLayerGlyphs import ExplodeColorLayerGlyphsFilter
from ufo2ft.util import _GlyphSet


@pytest.fixture
def data_dir():
    return Path(__file__).parent.parent / "data"


def test_strip_color_codepoints(FontClass, data_dir):
    """Test that the filter strips codepoints from glyphs when copying them from
    color layers into default layer alternates.

    See: https://github.com/googlefonts/ufo2ft/pull/739#issuecomment-1516075892"""

    # Load a test UFO with color layers, and give a codepoint to one of the
    # glyphs in those layers.
    ufo = FontClass(data_dir / "ColorTest.ufo")

    color_glyph = ufo.layers["color1"]["a"]
    color_glyph.unicode = 0x3020

    # Apply the filter to the UFO.
    filter = ExplodeColorLayerGlyphsFilter()
    glyphset = _GlyphSet.from_layer(ufo)
    _ = filter(ufo, glyphset)

    # Test that the newly-copied alternate has had its codepoint removed.
    new_default_alt = glyphset["a.color1"]
    assert new_default_alt.unicode is None
