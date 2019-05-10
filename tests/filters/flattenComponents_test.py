from __future__ import print_function, division, absolute_import
from ufo2ft.filters.flattenComponents import FlattenComponentsFilter, logger
from fontTools.misc.loggingTools import CapturingLogHandler
import pytest


@pytest.fixture(
    params=[
        {
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
                },
                {
                    "name": "b",
                    "width": 350,
                    "outline": [("addComponent", ("a", (1, 0, 0, 1, 0, 0)))],
                },
                {
                    "name": "c",
                    "width": 350,
                    "outline": [("addComponent", ("b", (1, 0, 0, 1, 0, 0)))],
                },
                {
                    "name": "d",
                    "width": 700,
                    "outline": [
                        ("addComponent", ("a", (1, 0, 0, 1, 0, 0))),
                        ("addComponent", ("b", (1, 0, 0, 1, 350, 0))),
                        ("addComponent", ("c", (1, 0, 0, 1, 700, 0))),
                    ],
                },
            ]
        }
    ]
)
def font(request, FontClass):
    font = FontClass()
    for param in request.param["glyphs"]:
        glyph = font.newGlyph(param["name"])
        glyph.width = param.get("width", 0)
        pen = glyph.getPen()
        for operator, operands in param.get("outline", []):
            getattr(pen, operator)(*operands)
    return font


class FlattenComponentsFilterTest(object):
    def test_empty_glyph(self, font):
        philter = FlattenComponentsFilter(include={"space"})
        assert not philter(font)

    def test_contour_glyph(self, font):
        philter = FlattenComponentsFilter(include={"a"})
        assert not philter(font)

    def test_component_glyph(self, font):
        philter = FlattenComponentsFilter(include={"b"})
        assert not philter(font)

    def test_nested_components_glyph(self, font):
        philter = FlattenComponentsFilter(include={"c"})
        modified = philter(font)
        assert modified == set(["c"])
        assert [(c.baseGlyph, c.transformation) for c in font["c"].components] == [
            ("a", (1, 0, 0, 1, 0, 0))
        ]

    def test_whole_font(self, font):
        philter = FlattenComponentsFilter()
        modified = philter(font)
        assert modified == set(["c", "d"])
        assert [(c.baseGlyph, c.transformation) for c in font["c"].components] == [
            ("a", (1, 0, 0, 1, 0, 0))
        ]
        assert [(c.baseGlyph, c.transformation) for c in font["d"].components] == [
            ("a", (1, 0, 0, 1, 0, 0)),
            ("a", (1, 0, 0, 1, 350, 0)),
            ("a", (1, 0, 0, 1, 700, 0)),
        ]

    def test_logger(self, font):
        with CapturingLogHandler(logger, level="INFO") as captor:
            philter = FlattenComponentsFilter()
            modified = philter(font)
        captor.assertRegex("Flattened composite glyphs: 2")
