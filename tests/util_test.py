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


def test_getMaxComponentDepth_cyclical_reference():
    # ufoLib2 lets you create cyclical component references (defcon would fail with
    # RecursionError while creating them so we don't test it below).
    # Here we test that we properly detect them and provide a descriptive error message.
    # https://github.com/googlefonts/fontmake/issues/1066
    test_ufo = pytest.importorskip("ufoLib2").Font()
    glyph_a = test_ufo.newGlyph("A")
    glyph_b = test_ufo.newGlyph("B")
    glyph_c = test_ufo.newGlyph("C")

    glyph_a.getPen().addComponent("C", (1, 0, 0, 1, 0, 0))
    glyph_b.getPen().addComponent("A", (1, 0, 0, 1, 0, 0))
    glyph_c.getPen().addComponent("B", (1, 0, 0, 1, 0, 0))

    with pytest.raises(
        InvalidFontData, match="cyclical component reference: A -> C -> B => A"
    ):
        util.getMaxComponentDepth(glyph_a, test_ufo)
    with pytest.raises(
        InvalidFontData, match="cyclical component reference: B -> A -> C => B"
    ):
        util.getMaxComponentDepth(glyph_b, test_ufo)
    with pytest.raises(
        InvalidFontData, match="cyclical component reference: C -> B -> A => C"
    ):
        util.getMaxComponentDepth(glyph_c, test_ufo)

    glyph_d = test_ufo.newGlyph("D")
    glyph_e = test_ufo.newGlyph("E")
    glyph_f = test_ufo.newGlyph("F")
    glyph_g = test_ufo.newGlyph("G")
    glyph_h = test_ufo.newGlyph("H")

    # adding same component multiple times should not cause infinite recursion
    glyph_d.getPen().addComponent("E", (1, 0, 0, 1, 0, 0))
    glyph_d.getPen().addComponent("E", (1, 0, 0, 1, 0, 0))
    # G is reachable from both E and F, but there is no cycle.
    glyph_e.getPen().addComponent("F", (1, 0, 0, 1, 0, 0))
    glyph_f.getPen().addComponent("G", (1, 0, 0, 1, 0, 0))
    glyph_e.getPen().addComponent("G", (1, 0, 0, 1, 0, 0))
    glyph_g.getPen().addComponent("H", (1, 0, 0, 1, 0, 0))

    assert util.getMaxComponentDepth(glyph_d, test_ufo) == 4
    assert util.getMaxComponentDepth(glyph_e, test_ufo) == 3
    assert util.getMaxComponentDepth(glyph_f, test_ufo) == 2
    assert util.getMaxComponentDepth(glyph_g, test_ufo) == 1
    assert util.getMaxComponentDepth(glyph_h, test_ufo) == 0
