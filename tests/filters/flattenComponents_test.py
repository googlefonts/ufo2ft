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
                {
                    "name": "contourAndComponentGlyph",
                    "width": 600,
                    "outline": [
                        ("moveTo", ((400, 0),)),
                        ("lineTo", ((400, 100),)),
                        ("lineTo", ((500, 100),)),
                        ("lineTo", ((500, 0),)),
                        ("closePath", ()),
                        ("addComponent", ("contourGlyph", (1, 0, 0, 1, 0, 0))),
                    ],
                },
                {
                    "name": "nestedContourAndComponentGlyph",
                    "width": 600,
                    "outline": [
                        (
                            "addComponent",
                            ("contourAndComponentGlyph", (1, 0, 0, 1, 50, 0)),
                        ),
                    ],
                },
                {
                    "name": "nestedNestedContourAndComponentGlyph",
                    "width": 600,
                    "outline": [
                        (
                            "addComponent",
                            ("nestedContourAndComponentGlyph", (1, 0, 0, 1, 45, 0)),
                        ),
                    ],
                },
                {
                    "name": "scaledComponentGlyph",
                    "width": 600,
                    "outline": [
                        (
                            "addComponent",
                            ("contourGlyph", (0.5, 0, 0, 0.5, 50, 50)),
                        ),
                    ],
                },
                {
                    "name": "nestedScaledComponentGlyph",
                    "width": 600,
                    "outline": [
                        (
                            "addComponent",
                            ("scaledComponentGlyph", (1, 0, 0, 1, 40, 40)),
                        ),
                    ],
                },
                {
                    "name": "scaledNestedComponentGlyph",
                    "width": 600,
                    "outline": [
                        (
                            "addComponent",
                            ("scaledComponentGlyph", (1.2, 0, 0, 1.2, 40, 40)),
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

    def test_nested_contour_and_component_glyph(self, font):
        philter = FlattenComponentsFilter(
            include={
                "nestedContourAndComponentGlyph",
                "nestedNestedContourAndComponentGlyph",
            }
        )
        modified = philter(font)
        assert modified == {"nestedNestedContourAndComponentGlyph"}
        assert [
            (c.baseGlyph, c.transformation)
            for c in font["nestedNestedContourAndComponentGlyph"].components
        ] == [("contourAndComponentGlyph", (1, 0, 0, 1, 95, 0))]

    def test_scaled_component_glyph(self, font):
        philter = FlattenComponentsFilter(
            include={
                "scaledComponentGlyph",
                "nestedScaledComponentGlyph",
                "scaledNestedComponentGlyph",
            }
        )
        modified = philter(font)
        assert modified == {
            "nestedScaledComponentGlyph",
            "scaledNestedComponentGlyph",
        }
        assert [
            (c.baseGlyph, c.transformation)
            for c in font["nestedScaledComponentGlyph"].components
        ] == [("contourGlyph", (0.5, 0, 0, 0.5, 90, 90))]
        assert [
            (c.baseGlyph, c.transformation)
            for c in font["scaledNestedComponentGlyph"].components
        ] == [("contourGlyph", (0.6, 0, 0, 0.6, 100, 100))]

    def test_whole_font(self, font):
        philter = FlattenComponentsFilter()
        modified = philter(font)
        assert modified == {
            "nestedComponentGlyph",
            "componentAndNestedComponentsGlyph",
            "nestedNestedContourAndComponentGlyph",
            "nestedScaledComponentGlyph",
            "scaledNestedComponentGlyph",
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
        assert [
            (c.baseGlyph, c.transformation)
            for c in font["nestedContourAndComponentGlyph"].components
        ] == [
            ("contourAndComponentGlyph", (1, 0, 0, 1, 50, 0)),
        ]
        assert [
            (c.baseGlyph, c.transformation)
            for c in font["nestedNestedContourAndComponentGlyph"].components
        ] == [("contourAndComponentGlyph", (1, 0, 0, 1, 95, 0))]
        assert [
            (c.baseGlyph, c.transformation)
            for c in font["nestedScaledComponentGlyph"].components
        ] == [("contourGlyph", (0.5, 0, 0, 0.5, 90, 90))]
        assert [
            (c.baseGlyph, c.transformation)
            for c in font["scaledNestedComponentGlyph"].components
        ] == [("contourGlyph", (0.6, 0, 0, 0.6, 100, 100))]

    def test_logger(self, font):
        with CapturingLogHandler(logger, level="INFO") as captor:
            philter = FlattenComponentsFilter()
            _ = philter(font)
        captor.assertRegex("Flattened composite glyphs: 5")
