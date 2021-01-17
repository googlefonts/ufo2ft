import pytest
from fontTools.misc.loggingTools import CapturingLogHandler

from ufo2ft.filters.flattenComponents import FlattenComponentsFilter, logger


@pytest.fixture(
    params=[
        {
            "glyphs": [
                {"name": "space", "width": 500},
                {
                    "name": "contourGlyph",
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
                    "name": "componentGlyph",
                    "width": 350,
                    "outline": [("addComponent", ("contourGlyph", (1, 0, 0, 1, 0, 0)))],
                },
                {
                    "name": "nestedComponentGlyph",
                    "width": 350,
                    "outline": [
                        ("addComponent", ("componentGlyph", (1, 0, 0, 1, 0, 0)))
                    ],
                },
                {
                    "name": "componentAndNestedComponentsGlyph",
                    "width": 700,
                    "outline": [
                        ("addComponent", ("contourGlyph", (1, 0, 0, 1, 0, 0))),
                        ("addComponent", ("componentGlyph", (1, 0, 0, 1, 350, 0))),
                        (
                            "addComponent",
                            ("nestedComponentGlyph", (1, 0, 0, 1, 700, 0)),
                        ),
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


class FlattenComponentsFilterTest:
    def test_empty_glyph(self, font):
        philter = FlattenComponentsFilter(include={"space"})
        assert not philter(font)

    def test_contour_glyph(self, font):
        philter = FlattenComponentsFilter(include={"contourGlyph"})
        assert not philter(font)

    def test_component_glyph(self, font):
        philter = FlattenComponentsFilter(include={"componentGlyph"})
        assert not philter(font)

    def test_nested_components_glyph(self, font):
        philter = FlattenComponentsFilter(include={"nestedComponentGlyph"})
        modified = philter(font)
        assert modified == {"nestedComponentGlyph"}
        assert [
            (c.baseGlyph, c.transformation)
            for c in font["nestedComponentGlyph"].components
        ] == [("contourGlyph", (1, 0, 0, 1, 0, 0))]

    def test_whole_font(self, font):
        philter = FlattenComponentsFilter()
        modified = philter(font)
        assert modified == {
            "nestedComponentGlyph",
            "componentAndNestedComponentsGlyph",
        }
        assert [
            (c.baseGlyph, c.transformation)
            for c in font["nestedComponentGlyph"].components
        ] == [("contourGlyph", (1, 0, 0, 1, 0, 0))]
        assert [
            (c.baseGlyph, c.transformation)
            for c in font["componentAndNestedComponentsGlyph"].components
        ] == [
            ("contourGlyph", (1, 0, 0, 1, 0, 0)),
            ("contourGlyph", (1, 0, 0, 1, 350, 0)),
            ("contourGlyph", (1, 0, 0, 1, 700, 0)),
        ]

    def test_logger(self, font):
        with CapturingLogHandler(logger, level="INFO") as captor:
            philter = FlattenComponentsFilter()
            _ = philter(font)
        captor.assertRegex("Flattened composite glyphs: 2")
