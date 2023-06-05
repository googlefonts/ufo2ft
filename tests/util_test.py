"""Tests for utility functions that ufo2ft provides."""

import re

import pytest

from ufo2ft import util
from ufo2ft.errors import InvalidFontData


def test_overloaded_mapping_raises_error(FontClass):
    """Test that util.makeUnicodeToGlyphNameMapping() raises an error when
    multiple glyphs are mapped to the same codepoint."""

    # Make an empty font in memory with glyphs 'A' and 'B'.
    test_ufo = FontClass()
    glyph_a = test_ufo.newGlyph("A")
    glyph_b = test_ufo.newGlyph("B")

    # Test that the util function DOES NOT raise an error when the glyphs are
    # mapped to distinct codepoints, and that the function returns the correct
    # mapping.
    glyph_a.unicodes = [0x0041]
    glyph_b.unicodes = [0x0042]
    assert util.makeUnicodeToGlyphNameMapping(test_ufo) == {0x0041: "A", 0x0042: "B"}

    # Test that the util function DOES raise an error when multiple glyphs are
    # mapped to the same codepoint, and that this error is generally
    # descriptive.
    glyph_a.unicodes = [0x0041]
    glyph_b.unicodes = [0x0041]
    with pytest.raises(
        InvalidFontData,
        match=re.escape("cannot map 'B' to U+0041; already mapped to 'A'"),
    ):
        util.makeUnicodeToGlyphNameMapping(test_ufo)
