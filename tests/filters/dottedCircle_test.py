from ufo2ft.filters.dottedCircleFilter import DottedCircleFilter
from ufo2ft.util import _GlyphSet


def test_dotted_circle_filter(FontClass, datadir):
    ufo_path = datadir.join("DottedCircleTest.ufo")
    font = FontClass(ufo_path)
    assert "uni25CC" not in font
    philter = DottedCircleFilter()
    glyphset = _GlyphSet.from_layer(font)
    modified = philter(font, glyphset)
    assert "uni25CC" in modified
    anchors = list(sorted(glyphset["uni25CC"].anchors, key=lambda x: x.name))
    assert anchors[0].x == 464
    assert anchors[0].y == -17
    assert anchors[0].name == "bottom"

    assert anchors[1].x == 563
    assert anchors[1].y == 546
    assert anchors[1].name == "top"

    assert len(glyphset["uni25CC"]) == 12
    assert int(glyphset["uni25CC"].width) == 688
