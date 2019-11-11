from __future__ import absolute_import, division, print_function

import pytest

import ufo2ft


@pytest.fixture
def font(request, datadir, FontClass):
    font = FontClass(datadir.join("ContourOrderTest.ufo"))
    return font


def test_sort_contour_order(font):
    font_compiled = ufo2ft.compileTTF(font, inplace=True)

    font_glyf = font_compiled["glyf"]

    glyph_uniFFFC = font_glyf.glyphs["uniFFFC"]
    glyph_uniFFFC.expand(font_glyf)
    assert glyph_uniFFFC.endPtsOfContours == [
        5,
        9,
        13,
        17,
        23,
        35,
        47,
        51,
        55,
        59,
        63,
        79,
        88,
        96,
        100,
        104,
        119,
        125,
        131,
        135,
        139,
        143,
    ]

    glyph_graphemejoinercomb = font_glyf.glyphs["graphemejoinercomb"]
    glyph_graphemejoinercomb.expand(font_glyf)
    assert glyph_graphemejoinercomb.endPtsOfContours == [
        5,
        9,
        15,
        23,
        31,
        39,
        47,
        55,
        63,
        71,
        75,
        79,
        87,
        95,
        103,
        111,
        119,
        127,
        135,
        143,
        151,
        157,
        163,
        167,
    ]
