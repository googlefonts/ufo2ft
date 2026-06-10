import pytest

from ufo2ft import compileTTF

ufoLib2 = pytest.importorskip("ufoLib2")


def _make_ufo(glyph_count):
    font = ufoLib2.Font()
    font.info.familyName = "Test"
    font.info.styleName = "Regular"
    font.info.unitsPerEm = 1000
    font.info.ascender = 800
    font.info.descender = -200

    glyph_order = [f"glyph{i}" for i in range(glyph_count)]
    for glyph_name in glyph_order:
        font.newGlyph(glyph_name).width = 500
    font.lib["public.glyphOrder"] = glyph_order
    return font


def test_compile_ttf_keeps_compact_tables_for_small_font():
    ttf = compileTTF(_make_ufo(2))

    assert len(ttf.getGlyphOrder()) == 3
    assert {"glyf", "loca", "maxp", "hhea", "hmtx"} <= set(ttf.keys())
    assert not {"GLYF", "LOCA", "MAXP", "HHEA", "HMTX"} & set(ttf.keys())


def test_compile_ttf_uses_beyond64k_tables_for_large_font():
    ttf = compileTTF(_make_ufo(0x10000))

    assert len(ttf.getGlyphOrder()) == 0x10001
    assert {"GLYF", "LOCA", "MAXP", "HHEA", "HMTX"} <= set(ttf.keys())
    assert not {"glyf", "loca", "maxp", "hhea", "hmtx"} & set(ttf.keys())
