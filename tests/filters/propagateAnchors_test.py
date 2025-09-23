import pytest
from fontTools.designspaceLib import DesignSpaceDocument
from fontTools.misc.loggingTools import CapturingLogHandler

import ufo2ft.filters
from ufo2ft.filters.propagateAnchors import (
    PropagateAnchorsFilter,
    PropagateAnchorsIFilter,
    logger,
)
from ufo2ft.instantiator import Instantiator
from ufo2ft.util import _GlyphSet


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
            "Anchors not propagated for inexistent component e in glyph emacron"
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


class PropagateAnchorsIFilterTest:
    def test_propagate_from_interpolated_components(self, FontClass, data_dir):
        ds_path = data_dir / "SkipExportGlyphsTest.designspace"
        ds = DesignSpaceDocument.fromfile(ds_path)
        ds.loadSourceFonts(FontClass)

        ufos = [s.font for s in ds.sources]
        glyphSets = [_GlyphSet.from_layer(s.font, s.layerName) for s in ds.sources]

        assert len(ufos) == len(glyphSets) == 4

        # the composite glyph 'Astroke' has no anchors, but 'A' has some
        for glyphSet in glyphSets:
            if "Astroke" in glyphSet:
                assert not glyphSet["Astroke"].anchors
            if "A" in glyphSet:
                assert glyphSet["A"].anchors

        # in glyphSets[2] the 'Astroke' component base glyphs are missing so their
        # propagated anchors are supposed to be interpolated on the fly
        assert "Astroke" in glyphSets[2]
        assert {c.baseGlyph for c in glyphSets[2]["Astroke"].components}.isdisjoint(
            glyphSets[2].keys()
        )
        assert not glyphSets[2]["Astroke"].anchors

        instantiator = Instantiator.from_designspace(
            ds, do_kerning=False, do_info=False
        )

        philter = PropagateAnchorsIFilter()

        modified = philter(ufos, glyphSets, instantiator)

        assert modified == {"Astroke"}

        assert [dict(a) for a in glyphSets[2]["Astroke"].anchors] == [
            {"name": "bottom", "x": 458, "y": 0},
            {"name": "center", "x": 457, "y": 358},
            {"name": "top", "x": 457, "y": 714},
            {"name": "topright", "x": 716, "y": 714},
        ]
        assert {c.baseGlyph for c in glyphSets[2]["Astroke"].components}.isdisjoint(
            glyphSets[2].keys()
        )

    def test_propagate_from_shared_nested_component_is_order_independent(
        self, FontClass, data_dir
    ):
        """Reproduces https://github.com/googlefonts/fontc/issues/1646

        This particular test font contains the following composite glyphs:
        - A-cy: uses A as base
        - Abreve-cy: uses A-cy and brevecomb as bases
        - Adieresis-cy: uses A-cy and dieresiscomb as bases
        The base glyph A has the following anchors: bottom, ogonek, top; A-cy has only
        top anchor; Abreve-cy and Adieresis-cy have no anchors.

        After PropagateAnchorsIFilterTest, the anchors of Abreve-cy and Adieresis-cy
        should be the same as A-cy.

        PropagateAnchorsIFilter processes glyphs with the same component depth in a
        non-deterministic order which varies because of hash randomization, which is ok
        because the algorithm is supposed to be order independent.
        However this exposed another bug whereby, depending on whether Abreve-cy or
        Adieresis-cy was processed first, only _one_ of the two glyphs would receive the
        anchors from A while the other would only get a single "top" anchor from A-cy.
        """
        ds_path = data_dir / "PropagateAnchorsIFilterTest.designspace"
        ds = DesignSpaceDocument.fromfile(ds_path)
        ds.loadSourceFonts(FontClass)

        ufos = [s.font for s in ds.sources]
        glyphSets = [_GlyphSet.from_layer(s.font, s.layerName) for s in ds.sources]

        assert len(ufos) == len(glyphSets) == 2

        expected_anchors = {"bottom", "ogonek", "top"}

        for glyphSet in glyphSets:
            # A has all three anchors
            assert {a.name for a in glyphSet["A"].anchors} == expected_anchors
            # A-cy has only top anchor and uses A as component
            assert {a.name for a in glyphSet["A-cy"].anchors} == {"top"}
            assert {c.baseGlyph for c in glyphSet["A-cy"].components} == {"A"}
            # Abreve-cy and Adieresis-cy both have no anchors and use A-cy as component
            assert not {a.name for a in glyphSet["Abreve-cy"].anchors}
            assert {c.baseGlyph for c in glyphSet["Abreve-cy"].components} == {
                "A-cy",
                "brevecomb.cap",
            }

            assert not {a.name for a in glyphSet["Adieresis-cy"].anchors}
            assert {c.baseGlyph for c in glyphSet["Adieresis-cy"].components} == {
                "A-cy",
                "dieresiscomb.cap",
            }

        instantiator = Instantiator.from_designspace(
            ds, do_kerning=False, do_info=False
        )

        philter = PropagateAnchorsIFilter()
        modified = philter(ufos, glyphSets, instantiator)

        # We expect all three glyphs to have the same anchor names after propagation
        assert modified == {"A-cy", "Abreve-cy", "Adieresis-cy"}
        for glyphSet in glyphSets:
            # but sometimes the first assert would fail, sometimes the second...
            assert {
                a.name for a in glyphSet["Abreve-cy"].anchors
            } == expected_anchors, "Abreve-cy"
            assert {
                a.name for a in glyphSet["Adieresis-cy"].anchors
            } == expected_anchors, "Adieresis-cy"
            assert {a.name for a in glyphSet["A-cy"].anchors} == expected_anchors
