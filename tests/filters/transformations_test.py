from __future__ import print_function, division, absolute_import
from ufo2ft.filters.transformations import TransformationsFilter, log
from fontTools.misc.loggingTools import CapturingLogHandler
from fontTools.misc.py23 import isclose
import pytest


@pytest.fixture(params=[
    {
        'capHeight': 700,
        'xHeight': 500,
        'glyphs': [
            {
                'name': 'space',
                'width': 500,
            },
            {
                'name': 'a',
                'width': 350,
                'outline': [
                    ('moveTo', ((0, 0),)),
                    ('lineTo', ((300, 0),)),
                    ('lineTo', ((300, 300),)),
                    ('lineTo', ((0, 300),)),
                    ('closePath', ()),
                ],
                'anchors': [
                    (100, 200, 'top'),
                    (100, -200, 'bottom'),
                ],
            },
            {
                'name': 'b',
                'width': 450,
                'outline': [
                    ('addComponent', ('a', (1, 0, 0, 1, 0, 0))),
                    ('addComponent', ('c', (1, 0, 0, 1, 0, 0))),
                ]
            },
            {
                'name': 'c',
                'outline': [
                    ('moveTo', ((0, 0),)),
                    ('lineTo', ((300, 0),)),
                    ('lineTo', ((150, 300),)),
                    ('closePath', ()),
                ]
            },
            {
                'name': 'd',
                'outline': [
                    ('addComponent', ('b', (1, 0, 0, -1, 0, 0)))
                ],
            },
        ],
    }
])
def font(request, FontClass):
    font = FontClass()
    font.info.capHeight = request.param['capHeight']
    font.info.xHeight = request.param['xHeight']
    for param in request.param['glyphs']:
        glyph = font.newGlyph(param['name'])
        glyph.width = param.get('width', 0)
        pen = glyph.getPen()
        for operator, operands in param.get('outline', []):
            getattr(pen, operator)(*operands)
        for x, y, name in param.get('anchors', []):
            glyph.appendAnchor(dict(x=x, y=y, name=name))
    return font


@pytest.fixture(
    params=TransformationsFilter.Origin,
    ids=[e.name for e in TransformationsFilter.Origin],
)
def origin(request):
    return request.param


class TransformationsFilterTest(object):

    def test_invalid_origin_value(self):
        with pytest.raises(ValueError) as excinfo:
            TransformationsFilter(Origin=5)
        excinfo.match("is not a valid Origin")

    def test_empty_glyph(self, font):
        filter_ = TransformationsFilter(OffsetY=51, include={'space'})
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

    def test_ScaleY(self, font, origin):
        percent = 50
        filter_ = TransformationsFilter(ScaleY=percent, Origin=origin)
        assert filter_(font)

        factor = percent/100
        origin_height = filter_.get_origin_height(font, origin)
        bottom = origin_height * factor
        top = bottom + 300 * factor

        a = font["a"]
        # only y coords change
        assert (a[0][0].x, a[0][0].y) == (0, bottom)
        assert (a[0][2].x, a[0][2].y) == (300, top)

    def test_ScaleXY(self, font, origin):
        percent = 50
        filter_ = TransformationsFilter(
            ScaleX=percent, ScaleY=percent, Origin=origin)
        assert filter_(font)

        factor = percent/100
        origin_height = filter_.get_origin_height(font, origin)
        bottom = origin_height * factor
        top = bottom + 300 * factor

        a = font["a"]
        # both x and y change
        assert (a[0][0].x, a[0][0].y) == (0, bottom)
        assert (a[0][2].x, a[0][2].y) == (150, top)

    def test_Slant(self, font, origin):
        filter_ = TransformationsFilter(Slant=45, Origin=origin)
        assert filter_(font)

        origin_height = filter_.get_origin_height(font, origin)

        a = font["a"]
        assert isclose(a[0][0].x, -origin_height)
        assert a[0][0].y == 0

    def test_composite_glyphs(self, font):
        filter_ = TransformationsFilter(
            OffsetX=-10, OffsetY=51, ScaleX=50, ScaleY=50, exclude={'c'})
        assert filter_(font)

        b = font["b"]
        # component 'a' was not transformed, because it doesn't have a scale
        # or skew and the base glyph was already included
        assert b.components[0].transformation == (1, 0, 0, 1, 0, 0)
        # component 'c' was transformed, because base glyph was not included
        assert b.components[1].transformation == (.5, 0, 0, .5, -10, 51)

        d = font["d"]
        # component 'b' was transformed as well as its base glyph, because
        # its original transform had a scale, so it was necessary to
        # compensate for the transformation applied on the base glyph
        assert d.components[0].transformation == (1, 0, 0, -1, 0, 102)
