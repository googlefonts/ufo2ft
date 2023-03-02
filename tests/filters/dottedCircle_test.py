import pytest

from ufo2ft.filters import loadFilters
from ufo2ft.filters.dottedCircle import DottedCircleFilter
from ufo2ft.util import _GlyphSet


def test_dotted_circle_filter(FontClass, datadir):
    ufo_path = datadir.join("DottedCircleTest.ufo")
    font = FontClass(ufo_path)
    assert "uni25CC" not in font
    philter = DottedCircleFilter()
    glyphset = _GlyphSet.from_layer(font)

    modified = philter(font, glyphset)

    assert "uni25CC" in modified

    dotted_circle = glyphset["uni25CC"]

    # check the Glyph's module is the same as the Font's (both ufoLib2 or defcon,
    # not mixed): https://github.com/googlefonts/ufo2ft/issues/644
    font_ufo_module = type(font).__module__.split(".")[0]
    glyph_ufo_module = type(dotted_circle).__module__.split(".")[0]
    assert glyph_ufo_module == font_ufo_module

    anchors = list(sorted(dotted_circle.anchors, key=lambda x: x.name))
    assert anchors[0].x == 464
    assert anchors[0].y == -17
    assert anchors[0].name == "bottom"

    assert anchors[1].x == 563
    assert anchors[1].y == 546
    assert anchors[1].name == "top"

    assert len(dotted_circle) == 12
    assert int(dotted_circle.width) == 688
    assert dotted_circle.unicodes == [0x25CC]


def test_empty_font(FontClass):
    """Check that the filter works on an empty font, i.e. uses fallbacks where
    appropriate."""

    font = FontClass()
    font.lib["com.github.googlei18n.ufo2ft.filters"] = [
        {"name": "dottedCircle", "pre": True}
    ]

    pre_filters, _ = loadFilters(font)
    (philter,) = pre_filters
    glyphset = _GlyphSet.from_layer(font)

    modified = philter(font, glyphset)

    assert "uni25CC" in modified


@pytest.mark.filterwarnings("ignore:Please update")
def test_empty_font_deprecated(FontClass):
    """Check that the module redirection works."""

    font = FontClass()
    font.lib["com.github.googlei18n.ufo2ft.filters"] = [
        {"name": "DottedCircleFilter", "pre": True}
    ]

    pre_filters, _ = loadFilters(font)
    (philter,) = pre_filters
    glyphset = _GlyphSet.from_layer(font)

    modified = philter(font, glyphset)

    assert "uni25CC" in modified
