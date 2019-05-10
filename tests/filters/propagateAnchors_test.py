from __future__ import print_function, division, absolute_import

import ufo2ft.filters
from ufo2ft.filters.propagateAnchors import PropagateAnchorsFilter, logger
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
                    "anchors": [(175, 300, "top"), (175, 0, "bottom")],
                },
                {
                    "name": "dieresiscomb",
                    "width": 0,
                    "outline": [
                        ("moveTo", ((-120, 320),)),
                        ("lineTo", ((-60, 320),)),
                        ("lineTo", ((-60, 360),)),
                        ("lineTo", ((-120, 360),)),
                        ("closePath", ()),
                        ("moveTo", ((120, 320),)),
                        ("lineTo", ((60, 320),)),
                        ("lineTo", ((60, 360),)),
                        ("lineTo", ((120, 360),)),
                        ("closePath", ()),
                    ],
                    "anchors": [(0, 300, "_top"), (0, 480, "top")],
                },
                {
                    "name": "macroncomb",
                    "width": 0,
                    "outline": [
                        ("moveTo", ((-120, 330),)),
                        ("lineTo", ((120, 330),)),
                        ("lineTo", ((120, 350),)),
                        ("lineTo", ((-120, 350),)),
                        ("closePath", ()),
                    ],
                    "anchors": [(0, 300, "_top"), (0, 480, "top")],
                },
                {
                    "name": "a-cyr",
                    "width": 350,
                    "outline": [("addComponent", ("a", (1, 0, 0, 1, 0, 0)))],
                },
                {
                    "name": "amacron",
                    "width": 350,
                    "outline": [
                        ("addComponent", ("a", (1, 0, 0, 1, 0, 0))),
                        ("addComponent", ("macroncomb", (1, 0, 0, 1, 175, 0))),
                    ],
                    "anchors": [(176, 481, "top")],
                },
                {
                    "name": "adieresis",
                    "width": 350,
                    "outline": [
                        ("addComponent", ("a", (1, 0, 0, 1, 0, 0))),
                        ("addComponent", ("dieresiscomb", (1, 0, 0, 1, 175, 0))),
                    ],
                },
                {
                    "name": "amacrondieresis",
                    "width": 350,
                    "outline": [
                        ("addComponent", ("amacron", (1, 0, 0, 1, 0, 0))),
                        ("addComponent", ("dieresiscomb", (1, 0, 0, 1, 175, 180))),
                    ],
                },
                {
                    "name": "adieresismacron",
                    "width": 350,
                    "outline": [
                        ("addComponent", ("a", (1, 0, 0, 1, 0, 0))),
                        ("addComponent", ("dieresiscomb", (1, 0, 0, 1, 175, 0))),
                        ("addComponent", ("macroncomb", (1, 0, 0, 1, 175, 180))),
                    ],
                },
                {
                    "name": "a_a",
                    "width": 700,
                    "outline": [
                        ("addComponent", ("a", (1, 0, 0, 1, 0, 0))),
                        ("addComponent", ("a", (1, 0, 0, 1, 350, 0))),
                    ],
                },
                {
                    "name": "emacron",
                    "width": 350,
                    "outline": [
                        ("addComponent", ("e", (1, 0, 0, 1, 0, 0))),
                        ("addComponent", ("macroncomb", (1, 0, 0, 1, 175, 0))),
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
        for x, y, name in param.get("anchors", []):
            glyph.appendAnchor(dict(x=x, y=y, name=name))
    return font


class PropagateAnchorsFilterTest(object):
    def test_empty_glyph(self, font):
        philter = PropagateAnchorsFilter(include={"space"})
        assert not philter(font)

    def test_contour_glyph(self, font):
        philter = PropagateAnchorsFilter(include={"a"})
        assert not philter(font)

    def test_single_component_glyph(self, font):
        philter = PropagateAnchorsFilter(include={"a-cyr"})
        assert philter(font) == {"a-cyr"}
        assert [(a.name, a.x, a.y) for a in font["a-cyr"].anchors] == [
            ("bottom", 175, 0),
            ("top", 175, 300),
        ]

    def test_two_component_glyph(self, font):
        name = "adieresis"
        philter = PropagateAnchorsFilter(include={name})
        assert philter(font) == {name}
        assert [(a.name, a.x, a.y) for a in font[name].anchors] == [
            ("bottom", 175, 0),
            ("top", 175, 480),
        ]

    def test_one_anchor_two_component_glyph(self, font):
        name = "amacron"
        philter = PropagateAnchorsFilter(include={name})
        assert philter(font) == {name}
        assert [(a.name, a.x, a.y) for a in font[name].anchors] == [
            ("top", 176, 481),
            ("bottom", 175, 0),
        ]

    def test_three_component_glyph(self, font):
        name = "adieresismacron"
        philter = PropagateAnchorsFilter(include={name})
        assert philter(font) == {name}
        assert [(a.name, a.x, a.y) for a in font[name].anchors] == [
            ("bottom", 175, 0),
            ("top", 175, 660),
        ]

    def test_nested_component_glyph(self, font):
        name = "amacrondieresis"
        philter = PropagateAnchorsFilter(include={name})
        assert philter(font) == {name}
        assert [(a.name, a.x, a.y) for a in font[name].anchors] == [
            ("bottom", 175, 0),
            ("top", 175, 660),
        ]

    def test_ligature_glyph(self, font):
        name = "a_a"
        philter = PropagateAnchorsFilter(include={name})
        assert philter(font) == {name}
        assert [(a.name, a.x, a.y) for a in font[name].anchors] == [
            ("bottom_1", 175, 0),
            ("bottom_2", 525, 0),
            ("top_1", 175, 300),
            ("top_2", 525, 300),
        ]

    def test_whole_font(self, font):
        philter = PropagateAnchorsFilter()
        modified = philter(font)
        assert modified == set(
            [
                "a-cyr",
                "amacron",
                "adieresis",
                "adieresismacron",
                "amacrondieresis",
                "a_a",
            ]
        )

    def test_fail_during_anchor_propagation(self, font):
        name = "emacron"
        with CapturingLogHandler(logger, level="WARNING") as captor:
            philter = PropagateAnchorsFilter(include={name})
            philter(font)
        captor.assertRegex(
            "Anchors not propagated for inexistent component e " "in glyph emacron"
        )

    def test_logger(self, font):
        with CapturingLogHandler(logger, level="INFO") as captor:
            philter = PropagateAnchorsFilter()
            philter(font)
        captor.assertRegex("Glyphs with propagated anchors: 6")


def test_CantarellAnchorPropagation(FontClass, datadir):
    ufo_path = datadir.join("CantarellAnchorPropagation.ufo")
    ufo = FontClass(ufo_path)
    pre_filters, _ = ufo2ft.filters.loadFilters(ufo)

    philter = pre_filters[0]
    philter(ufo)

    anchors_combined = {
        (a.name, a.x, a.y) for a in ufo["circumflexcomb_tildecomb"].anchors
    }
    assert ("top", 214.0, 730.0) in anchors_combined
    assert ("_top", 213.0, 482.0) in anchors_combined

    anchors_o = {(a.name, a.x, a.y) for a in ufo["ocircumflextilde"].anchors}
    assert ("top", 284.0, 730.0) in anchors_o


def test_CantarellAnchorPropagation_reduced_filter(FontClass, datadir):
    ufo_path = datadir.join("CantarellAnchorPropagation.ufo")
    ufo = FontClass(ufo_path)
    ufo.lib["com.github.googlei18n.ufo2ft.filters"][0]["include"] = ["ocircumflextilde"]
    pre_filters, _ = ufo2ft.filters.loadFilters(ufo)

    philter = pre_filters[0]
    philter(ufo)

    anchors_combined = {
        (a.name, a.x, a.y) for a in ufo["circumflexcomb_tildecomb"].anchors
    }
    assert ("top", 214.0, 730.0) in anchors_combined
    assert ("_top", 213.0, 482.0) in anchors_combined

    anchors_o = {(a.name, a.x, a.y) for a in ufo["ocircumflextilde"].anchors}
    assert ("top", 284.0, 730.0) in anchors_o
