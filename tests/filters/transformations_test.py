from math import isclose

import pytest

from ufo2ft.filters.transformations import TransformationsFilter


@pytest.fixture(
    params=[
        {
            "capHeight": 700,
            "xHeight": 500,
            "glyphs": [
                {"name": "space", "width": 500},
                {
                    "name": "a",
                    "width": 350,
                    "outline": [
                        ("moveTo", ((0, 0),)),
                        ("lineTo", ((300, 0),)),
                        ("lineTo", ((300, 300),)),
                        ("lineTo", ((0, 300),)),
                        ("closePath", ()),
                    ],
                    "anchors": [(100, 200, "top"), (100, -200, "bottom")],
                },
                {
                    "name": "b",
                    "width": 450,
                    "outline": [
                        ("addComponent", ("a", (1, 0, 0, 1, 0, 0))),
                        ("addComponent", ("c", (1, 0, 0, 1, 0, 0))),
                        ("addComponent", ("a", (1, 0, 0, 1, 10, -10))),
                    ],
                },
                {
                    "name": "c",
                    "outline": [
                        ("moveTo", ((0, 0),)),
                        ("lineTo", ((300, 0),)),
                        ("lineTo", ((150, 300),)),
                        ("closePath", ()),
                    ],
                },
                {
                    "name": "d",
                    "outline": [("addComponent", ("b", (1, 0, 0, -1, 0, 0)))],
                },
            ],
        }
    ]
)
def font(request, FontClass):
    font = FontClass()
    font.info.capHeight = request.param["capHeight"]
    font.info.xHeight = request.param["xHeight"]
    for param in request.param["glyphs"]:
        glyph = font.newGlyph(param["name"])
        glyph.width = param.get("width", 0)
        pen = glyph.getPen()
        for operator, operands in param.get("outline", []):
            getattr(pen, operator)(*operands)
        for x, y, name in param.get("anchors", []):
            glyph.appendAnchor(dict(x=x, y=y, name=name))
    return font


@pytest.fixture(
    params=TransformationsFilter.Origin,
    ids=[e.name for e in TransformationsFilter.Origin],
)
def origin(request):
    return request.param


class TransformationsFilterTest:
    def test_invalid_origin_value(self):
        with pytest.raises(ValueError) as excinfo:
            TransformationsFilter(Origin=5)
        excinfo.match(r"is not a valid (TransformationsFilter\.)?Origin")

    def test_empty_glyph(self, font):
        filter_ = TransformationsFilter(OffsetY=51, include={"space"})
        assert not filter_(font)

    def test_Identity(self, font):
        filter_ = TransformationsFilter()
        assert not filter_(font)

    def test_OffsetX(self, font):
        filter_ = TransformationsFilter(OffsetX=-10)
        assert filter_(font)

        a = font["a"]
        assert (a[0][0].x, a[0][0].y) == (-10, 0)
        assert (a.anchors[1].x, a.anchors[1].y) == (90, -200)

        # base glyph was already transformed, component didn't change
        assert font["b"].components[0].transformation[-2:] == (0, 0)

    def test_OffsetY(self, font):
        filter_ = TransformationsFilter(OffsetY=51)
        assert filter_(font)

        a = font["a"]
        assert (a[0][0].x, a[0][0].y) == (0, 51)
        assert (a.anchors[1].x, a.anchors[1].y) == (100, -149)

        assert font["b"].components[0].transformation[-2:] == (0, 0)

    def test_OffsetXY(self, font):
        filter_ = TransformationsFilter(OffsetX=-10, OffsetY=51)
        assert filter_(font)

        a = font["a"]
        assert (a[0][0].x, a[0][0].y) == (-10, 51)
        assert (a.anchors[1].x, a.anchors[1].y) == (90, -149)

        assert font["b"].components[0].transformation[-2:] == (0, 0)

    def test_ScaleX(self, font, origin):
        # different Origin heights should not affect horizontal scale
        filter_ = TransformationsFilter(ScaleX=50, Origin=origin)
        assert filter_(font)

        a = font["a"]
        assert (a[0][0].x, a[0][0].y) == (0, 0)
        assert (a[0][2].x, a[0][2].y) == (150, 300)

        assert a.width == 350 * 0.50

    def test_ScaleY(self, font, origin):
        percent = 50
        filter_ = TransformationsFilter(ScaleY=percent, Origin=origin)
        assert filter_(font)

        factor = percent / 100
        origin_height = filter_.get_origin_height(font, origin)
        bottom = origin_height * factor
        top = bottom + 300 * factor

        a = font["a"]
        # only y coords change
        assert (a[0][0].x, a[0][0].y) == (0, bottom)
        assert (a[0][2].x, a[0][2].y) == (300, top)

    def test_ScaleXY(self, font, origin):
        percent = 50
        filter_ = TransformationsFilter(ScaleX=percent, ScaleY=percent, Origin=origin)
        assert filter_(font)

        factor = percent / 100
        origin_height = filter_.get_origin_height(font, origin)
        bottom = origin_height * factor
        top = bottom + 300 * factor

        a = font["a"]
        # both x and y change
        assert (a[0][0].x, a[0][0].y) == (0, bottom)
        assert (a[0][2].x, a[0][2].y) == (150, top)
        assert a.width == 350 * factor

    def test_Slant(self, font, origin):
        filter_ = TransformationsFilter(Slant=45, Origin=origin)
        assert filter_(font)

        origin_height = filter_.get_origin_height(font, origin)

        a = font["a"]
        assert isclose(a[0][0].x, -origin_height)
        assert a[0][0].y == 0

    def test_composite_glyphs(self, font):
        filter_ = TransformationsFilter(
            OffsetX=-10, OffsetY=51, ScaleX=50, ScaleY=50, exclude={"c"}
        )
        assert filter_(font)

        b = font["b"]
        # component 'a' #1 was not transformed, because the base glyph was already
        # transformed, and the component's own transformation is identity
        assert b.components[0].transformation == (1, 0, 0, 1, 0, 0)
        # component 'c' was transformed, because base glyph was not included
        assert b.components[1].transformation == (0.5, 0, 0, 0.5, -10, 51)
        # component 'a' #2 was partly transformed: the base glyph was transformed, but
        # the component's original transformation was not identity; thus
        # it was modified to compensate for the transformation already applied to
        # the base glyph (scale stays same, offsets are scaled)
        assert b.components[2].transformation == (1, 0, 0, 1, 5, -5)

        d = font["d"]
        # component 'b' was transformed as well as its base glyph, because
        # its original transform had a scale, so it was necessary to
        # compensate for the transformation applied on the base glyph
        assert d.components[0].transformation == (1, 0, 0, -1, 0, 102)

    def test_ScaleOffset_width(self, font, origin):
        percent = 50
        filter_ = TransformationsFilter(
            OffsetX=-100, ScaleX=percent, ScaleY=percent, Origin=origin
        )
        assert filter_(font)
        factor = percent / 100

        a = font["a"]
        # The offset value here should not change the fact that the glyph
        # bounding box is scaled by 50%.
        assert a.width == 350 * factor
