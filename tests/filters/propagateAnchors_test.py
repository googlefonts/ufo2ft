import pytest
from fontTools.misc.loggingTools import CapturingLogHandler

import ufo2ft.filters
from ufo2ft.filters.propagateAnchors import PropagateAnchorsFilter, logger


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
                {
                    "name": "r",
                    "width": 350,
                    "outline": [
                        ("moveTo", ((0, 0),)),
                        ("lineTo", ((0, 300),)),
                        ("lineTo", ((175, 300),)),
                        ("closePath", ()),
                    ],
                    "anchors": [(175, 300, "top"), (175, 0, "bottom")],
                },
                {
                    "name": "rcombbelow",
                    "width": 0,
                    "outline": [
                        ("addComponent", ("r", (0.5, 0, 0, 0.5, -100, -100))),
                    ],
                    "anchors": [(0, 0, "_bottom")],
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
    # classify as 'mark' all glyphs with zero width and 'comb' in their name
    font.lib["public.openTypeCategories"] = {
        g["name"]: "mark"
        for g in request.param["glyphs"]
        if g.get("width", 0) == 0 and "comb" in g["name"]
    }
    return font


EXPECTED = {
    # single component glyph
    "a-cyr": ([("bottom", 175, 0), ("top", 175, 300)], {"a-cyr"}),
    # two component glyph
    "adieresis": ([("bottom", 175, 0), ("top", 175, 480)], {"adieresis"}),
    # one anchor, two component glyph
    "amacron": ([("top", 176, 481), ("bottom", 175, 0)], {"amacron"}),
    # three component glyph
    "adieresismacron": ([("bottom", 175, 0), ("top", 175, 660)], {"adieresismacron"}),
    # nested component glyph
    "amacrondieresis": (
        [("bottom", 175, 0), ("top", 175, 660)],
        # 'amacron' is used as component by 'amacrondieresis' hence it is modified
        # as well...
        {"amacrondieresis", "amacron"},
    ),
    # ligature glyph
    "a_a": (
        [
            ("bottom_1", 175, 0),
            ("bottom_2", 525, 0),
            ("top_1", 175, 300),
            ("top_2", 525, 300),
        ],
        {"a_a"},
    ),
    # the composite glyph is a mark with anchors, hence propagation is not performed,
    # i.e. 'top' and 'bottom' are *not* copied to 'rcombbelow':
    # https://github.com/googlefonts/ufo2ft/issues/802
    "rcombbelow": ([("_bottom", 0, 0)], set()),
}


class PropagateAnchorsFilterTest:
    def test_empty_glyph(self, font):
        philter = PropagateAnchorsFilter(include={"space"})
        assert not philter(font)

    def test_contour_glyph(self, font):
        philter = PropagateAnchorsFilter(include={"a"})
        assert not philter(font)

    @pytest.mark.parametrize("name", list(EXPECTED))
    def test_include_one_glyph_at_a_time(self, font, name):
        philter = PropagateAnchorsFilter(include={name})
        modified = philter(font)

        expected_anchors, expected_modified = EXPECTED[name]
        assert modified == expected_modified
        assert [(a.name, a.x, a.y) for a in font[name].anchors] == expected_anchors

    def test_whole_font(self, font):
        philter = PropagateAnchorsFilter()
        modified = philter(font)
        assert modified == {k for k in EXPECTED if k in EXPECTED[k][1]}
        for name, (expected_anchors, _) in EXPECTED.items():
            assert [(a.name, a.x, a.y) for a in font[name].anchors] == expected_anchors

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
