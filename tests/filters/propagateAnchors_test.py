import math

import pytest
from fontTools.designspaceLib import DesignSpaceDocument
from fontTools.misc.loggingTools import CapturingLogHandler
from fontTools.misc.transform import Transform

import ufo2ft.filters
from ufo2ft.constants import (
    _PRELIMINARY_CATEGORIES_KEY,
    GLYPHS_COMPONENT_INFO_KEY,
    OPENTYPE_CATEGORIES_KEY,
)
from ufo2ft.filters.propagateAnchors import (
    AnchorData,
    PropagateAnchorsFilter,
    PropagateAnchorsIFilter,
    _finalize_categories,
    get_xy_rotation,
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
    categories = {
        g["name"]: "mark"
        for g in request.param["glyphs"]
        if g.get("width", 0) == 0 and "comb" in g["name"]
    }
    categories["a_a"] = "ligature"
    font.lib["public.openTypeCategories"] = categories
    return font


EXPECTED = {
    # single component glyph
    "a-cyr": ([("bottom", 175, 0), ("top", 175, 300)], {"a-cyr"}),
    # two component glyph
    "adieresis": ([("bottom", 175, 0), ("top", 175, 480)], {"adieresis"}),
    # one anchor, two component glyph (amacron has its own 'top' anchor)
    "amacron": ([("bottom", 175, 0), ("top", 176, 481)], {"amacron"}),
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
    # partial propagation: 'e' component is missing, but macroncomb's anchors
    # still propagate (with a warning about the missing component)
    "emacron": ([("top", 175, 480)], {"emacron"}),
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
        expected_modified = {k for k in EXPECTED if k in EXPECTED[k][1]}
        assert modified == expected_modified
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
        captor.assertRegex("Glyphs with propagated anchors: 7")


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


# ---------------------------------------------------------------------------
# Tests ported from glyphsLib and fontc to keep the three implementations in sync.
# glyphsLib source: tests/builder/transformations/propagate_anchors_test.py
# fontc source: fontir/src/propagate_anchors.rs (test module)
#
# glyphsLib classifies marks/ligatures from GlyphData.xml (GSGlyph.category/
# subCategory); ufo2ft uses explicit public.openTypeCategories.  Where glyphsLib
# auto-detects a mark, we set categories explicitly here.
# ---------------------------------------------------------------------------


def _make_glyph(font, name, width=0, anchors=(), components=(), contour=True):
    """Helper matching glyphsLib's GlyphBuilder for defcon/ufoLib2 fonts."""
    g = font.newGlyph(name)
    g.width = width
    pen = g.getPen()
    if contour and not components:
        pen.moveTo((0, 0))
        pen.lineTo((width or 100, 0))
        pen.endPath()
    for base, pos in components:
        pen.addComponent(base, (1, 0, 0, 1, pos[0], pos[1]))
    for a in anchors:
        g.appendAnchor(dict(x=a[1][0], y=a[1][1], name=a[0]))
    return g


def _assert_anchors(font, glyph_name, expected):
    """Assert anchors match expected list of (name, (x, y)) tuples."""
    actual = [(a.name, (a.x, a.y)) for a in font[glyph_name].anchors]
    assert sorted(actual) == sorted(expected), (
        f"anchors for '{glyph_name}':\n"
        f"  actual:   {sorted(actual)}\n"
        f"  expected: {sorted(expected)}"
    )


def test_affine_scale():
    """Ported from glyphsLib test_affine_scale."""
    assert get_xy_rotation(
        Transform().translate(589, 502).rotate(math.radians(180))
    ) == (-1, -1)
    assert get_xy_rotation(Transform().translate(10, 10)) == (1, 1)
    assert get_xy_rotation(Transform().scale(1, -1)) == (1, -1)
    assert get_xy_rotation(Transform().scale(-1, 1)) == (-1, 1)
    assert get_xy_rotation(
        Transform().translate(589, 502).rotate(math.radians(180)).scale(-1, 1)
    ) == (1, -1)


class PortedAlgorithmTest:
    """Tests ported from glyphsLib/fontc to verify the three implementations
    stay in sync.  Uses the same glyph names and coordinates as the originals."""

    def test_no_components_anchors_are_unchanged(self, FontClass):
        """Ported from glyphsLib test_no_components_anchors_are_unchanged."""
        font = FontClass()
        _make_glyph(
            font,
            "A",
            600,
            anchors=[
                ("bottom", (234, 0)),
                ("ogonek", (411, 0)),
                ("top", (234, 810)),
            ],
        )
        _make_glyph(
            font,
            "acutecomb",
            0,
            anchors=[
                ("_top", (0, 578)),
                ("top", (0, 810)),
            ],
        )
        font.lib["public.openTypeCategories"] = {"acutecomb": "mark"}

        philter = PropagateAnchorsFilter()
        philter(font)

        _assert_anchors(
            font,
            "A",
            [
                ("bottom", (234, 0)),
                ("ogonek", (411, 0)),
                ("top", (234, 810)),
            ],
        )
        _assert_anchors(
            font,
            "acutecomb",
            [
                ("_top", (0, 578)),
                ("top", (0, 810)),
            ],
        )

    def test_basic_composite_anchor(self, FontClass):
        """Ported from glyphsLib test_basic_composite_anchor."""
        font = FontClass()
        _make_glyph(
            font,
            "A",
            600,
            anchors=[
                ("bottom", (234, 0)),
                ("ogonek", (411, 0)),
                ("top", (234, 810)),
            ],
        )
        _make_glyph(
            font,
            "acutecomb",
            0,
            anchors=[
                ("_top", (0, 578)),
                ("top", (0, 810)),
            ],
        )
        _make_glyph(
            font,
            "Aacute",
            600,
            contour=False,
            components=[
                ("A", (0, 0)),
                ("acutecomb", (234, 232)),
            ],
        )
        font.lib["public.openTypeCategories"] = {"acutecomb": "mark"}

        philter = PropagateAnchorsFilter()
        philter(font)

        _assert_anchors(
            font,
            "Aacute",
            [
                ("bottom", (234, 0)),
                ("ogonek", (411, 0)),
                ("top", (234, 1042)),
            ],
        )

    def test_propagate_ligature_anchors(self, FontClass):
        """Ported from glyphsLib test_propagate_ligature_anchors.
        Based on the IJ glyph in Oswald (ExtraLight)."""
        font = FontClass()
        _make_glyph(
            font,
            "I",
            206,
            anchors=[
                ("bottom", (103, 0)),
                ("ogonek", (103, 0)),
                ("top", (103, 810)),
                ("topleft", (20, 810)),
            ],
        )
        _make_glyph(
            font,
            "J",
            266,
            anchors=[
                ("bottom", (133, 0)),
                ("top", (163, 810)),
            ],
        )
        _make_glyph(
            font,
            "IJ",
            472,
            contour=False,
            components=[
                ("I", (0, 0)),
                ("J", (206, 0)),
            ],
        )
        font.lib["public.openTypeCategories"] = {"IJ": "ligature"}

        philter = PropagateAnchorsFilter()
        philter(font)

        _assert_anchors(
            font,
            "IJ",
            [
                ("bottom_1", (103, 0)),
                ("ogonek_1", (103, 0)),
                ("top_1", (103, 810)),
                ("topleft_1", (20, 810)),
                ("bottom_2", (339, 0)),
                ("top_2", (369, 810)),
            ],
        )

    def test_digraphs_arent_ligatures(self, FontClass):
        """Ported from glyphsLib test_digraphs_arent_ligatures.
        Same glyphs as test_propagate_ligature_anchors but IJ is NOT
        classified as ligature — anchors are not numbered."""
        font = FontClass()
        _make_glyph(
            font,
            "I",
            206,
            anchors=[
                ("bottom", (103, 0)),
                ("ogonek", (103, 0)),
                ("top", (103, 810)),
                ("topleft", (20, 810)),
            ],
        )
        _make_glyph(
            font,
            "J",
            266,
            anchors=[
                ("bottom", (133, 0)),
                ("top", (163, 810)),
            ],
        )
        _make_glyph(
            font,
            "IJ",
            472,
            contour=False,
            components=[
                ("I", (0, 0)),
                ("J", (206, 0)),
            ],
        )
        font.lib["public.openTypeCategories"] = {}

        philter = PropagateAnchorsFilter()
        philter(font)

        _assert_anchors(
            font,
            "IJ",
            [
                ("bottom", (339, 0)),
                ("ogonek", (103, 0)),
                ("top", (369, 810)),
                ("topleft", (20, 810)),
            ],
        )

    def test_remove_exit_anchor_on_component(self, FontClass):
        """Ported from glyphsLib test_remove_exit_anchor_on_component."""
        font = FontClass()
        _make_glyph(font, "comma", 250)
        _make_glyph(
            font,
            "ain-ar.init",
            400,
            anchors=[
                ("top", (294, 514)),
                ("exit", (0, 0)),
            ],
        )
        _make_glyph(
            font,
            "ain-ar.init.alt",
            400,
            contour=False,
            components=[
                ("ain-ar.init", (0, 0)),
                ("comma", (0, 0)),
            ],
        )
        font.lib["public.openTypeCategories"] = {}

        philter = PropagateAnchorsFilter()
        philter(font)

        _assert_anchors(font, "ain-ar.init.alt", [("top", (294, 514))])

    def test_component_anchor(self, FontClass):
        """Ported from glyphsLib test_component_anchor / fontc component_anchor."""
        font = FontClass()
        _make_glyph(
            font,
            "acutecomb",
            0,
            anchors=[
                ("_top", (150, 580)),
                ("top", (170, 792)),
            ],
        )
        g = _make_glyph(
            font,
            "aa",
            960,
            anchors=[
                ("bottom_1", (218, 8)),
                ("bottom_2", (742, 7)),
                ("ogonek_1", (398, 9)),
                ("ogonek_2", (902, 9)),
                ("top_1", (227, 548)),
                ("top_2", (746, 548)),
            ],
        )
        _make_glyph(
            font,
            "a_a",
            960,
            contour=False,
            components=[
                ("aa", (0, 0)),
            ],
        )
        g = _make_glyph(
            font,
            "a_aacute",
            960,
            contour=False,
            components=[
                ("a_a", (0, 0)),
                ("acutecomb", (596, -32)),
            ],
        )
        # UFO components have no lib, so glyphsLib stores per-component
        # properties in the composite glyph's lib; index 1 = acutecomb
        g.lib[GLYPHS_COMPONENT_INFO_KEY] = [
            {"index": 1, "anchor": "top_2"},
        ]
        font.lib["public.openTypeCategories"] = {
            "acutecomb": "mark",
            "aa": "ligature",
            "a_a": "ligature",
            "a_aacute": "ligature",
        }

        philter = PropagateAnchorsFilter()
        philter(font)

        _assert_anchors(
            font,
            "a_aacute",
            [
                ("bottom_1", (218, 8)),
                ("bottom_2", (742, 7)),
                ("ogonek_1", (398, 9)),
                ("ogonek_2", (902, 9)),
                ("top_1", (227, 548)),
                # top_2 replaced by acutecomb's "top" renamed via ComponentInfo:
                # (170, 792) + offset (596, -32) = (766, 760)
                ("top_2", (766, 760)),
            ],
        )

    def test_origin_anchor(self, FontClass):
        """Ported from glyphsLib test_origin_anchor."""
        font = FontClass()
        _make_glyph(
            font,
            "a",
            500,
            anchors=[
                ("*origin", (-20, 0)),
                ("bottom", (242, 7)),
                ("ogonek", (402, 9)),
                ("top", (246, 548)),
            ],
        )
        _make_glyph(
            font,
            "acutecomb",
            0,
            anchors=[
                ("_top", (150, 580)),
                ("top", (170, 792)),
            ],
        )
        _make_glyph(
            font,
            "aacute",
            500,
            contour=False,
            components=[
                ("a", (0, 0)),
                ("acutecomb", (116, -32)),
            ],
        )
        font.lib["public.openTypeCategories"] = {"acutecomb": "mark"}

        philter = PropagateAnchorsFilter()
        philter(font)

        _assert_anchors(
            font,
            "aacute",
            [
                ("bottom", (262, 7)),
                ("ogonek", (422, 9)),
                ("top", (286, 760)),
            ],
        )

    def test_invert_names_on_rotation(self, FontClass):
        """Ported from glyphsLib test_invert_names_on_rotation."""
        font = FontClass()
        _make_glyph(font, "comma", 250)
        _make_glyph(
            font,
            "commaaccentcomb",
            0,
            anchors=[
                ("_bottom", (289, 0)),
                ("mybottom", (277, -308)),
            ],
        )
        # Add a component to commaaccentcomb
        pen = font["commaaccentcomb"].getPen()
        pen.addComponent("comma", (1, 0, 0, 1, 9, -164))

        # 180° rotated component
        g = font.newGlyph("commaturnedabovecomb")
        g.width = 0
        pen = g.getPen()
        t = Transform().translate(589, 502).rotate(math.radians(180))
        pen.addComponent("commaaccentcomb", tuple(t))
        font.lib["public.openTypeCategories"] = {
            "commaaccentcomb": "mark",
            "commaturnedabovecomb": "mark",
        }

        philter = PropagateAnchorsFilter()
        philter(font)

        _assert_anchors(
            font,
            "commaturnedabovecomb",
            [
                ("_top", (300, 502)),
                ("mytop", (312, 810)),
            ],
        )

    def test_entry_anchor_on_non_first_component(self, FontClass):
        """Ported from glyphsLib test_entry_anchor_on_non_first_component."""
        font = FontClass()
        _make_glyph(font, "part1", 200, anchors=[("top", (10, 0))])
        _make_glyph(font, "part2", 200, anchors=[("entry.2", (10, 0))])
        _make_glyph(
            font,
            "combo",
            400,
            contour=False,
            components=[
                ("part1", (0, 0)),
                ("part2", (100, 0)),
            ],
        )
        font.lib["public.openTypeCategories"] = {}

        philter = PropagateAnchorsFilter()
        philter(font)

        _assert_anchors(font, "combo", [("top", (10, 0))])

    def test_cursive_anchors_ligature(self, FontClass):
        """Ported from glyphsLib test_cursive_anchors_ligature."""
        font = FontClass()
        _make_glyph(
            font,
            "part1_part2",
            200,
            anchors=[
                ("entry.1", (10, 0)),
                ("exit.1", (100, 0)),
            ],
        )
        _make_glyph(
            font,
            "combo",
            200,
            contour=False,
            components=[
                ("part1_part2", (0, 0)),
            ],
        )
        font.lib["public.openTypeCategories"] = {"combo": "ligature"}

        philter = PropagateAnchorsFilter()
        philter(font)

        _assert_anchors(
            font,
            "combo",
            [
                ("entry.1", (10, 0)),
                ("exit.1", (100, 0)),
            ],
        )


class CharacterizationTest:
    """Tests for ufo2ft-specific behavior not covered by the ported suite."""

    def test_mixed_mark_base_anchor_component(self, FontClass):
        """A component with both _bottomright (mark-attaching) and bottom
        (base anchor for mark-to-mark stacking) should propagate the base
        anchor. The old algorithm classifies the entire component as 'mark'
        and drops all its anchors. This documents the known bug."""
        font = FontClass()
        # Base glyph with a 'top' anchor
        g = font.newGlyph("A")
        g.width = 600
        pen = g.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((600, 0))
        pen.lineTo((300, 700))
        pen.closePath()
        g.appendAnchor(dict(x=300, y=700, name="top"))
        g.appendAnchor(dict(x=300, y=0, name="bottom"))

        # Mark component with both _bottomright (mark-attaching) and
        # bottom (base anchor for stacking another mark below)
        g = font.newGlyph("ogonek")
        g.width = 0
        pen = g.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((100, -200))
        pen.lineTo((50, -100))
        pen.closePath()
        g.appendAnchor(dict(x=50, y=0, name="_bottomright"))
        g.appendAnchor(dict(x=50, y=-200, name="bottom"))

        # Composite: A + ogonek
        g = font.newGlyph("Aogonek")
        g.width = 600
        pen = g.getPen()
        pen.addComponent("A", (1, 0, 0, 1, 0, 0))
        pen.addComponent("ogonek", (1, 0, 0, 1, 300, 0))

        font.lib["public.openTypeCategories"] = {"ogonek": "mark"}

        philter = PropagateAnchorsFilter()
        philter(font)

        anchors = {(a.name, a.x, a.y) for a in font["Aogonek"].anchors}

        # The new algorithm processes each anchor individually, so ogonek's
        # "bottom" anchor (a base anchor for mark-to-mark stacking) is
        # correctly propagated. ogonek's "bottom" overwrites A's "bottom"
        # because ogonek attaches to A and the mark's stacking anchor
        # takes precedence.
        assert ("top", 300, 700) in anchors
        assert ("bottom", 350, -200) in anchors

    def test_mark_with_existing_anchors_skips_propagation(self, FontClass):
        """A mark glyph that already has anchors should not have component
        anchors propagated into it."""
        font = FontClass()
        g = font.newGlyph("dotbelow")
        g.width = 0
        pen = g.getPen()
        pen.moveTo((-50, -100))
        pen.lineTo((50, -100))
        pen.lineTo((50, 0))
        pen.lineTo((-50, 0))
        pen.closePath()
        g.appendAnchor(dict(x=0, y=-100, name="_bottom"))
        g.appendAnchor(dict(x=0, y=0, name="bottom"))

        g = font.newGlyph("brevecomb")
        g.width = 0
        pen = g.getPen()
        pen.moveTo((-60, 500))
        pen.lineTo((60, 500))
        pen.lineTo((0, 550))
        pen.closePath()
        g.appendAnchor(dict(x=0, y=480, name="_top"))
        g.appendAnchor(dict(x=0, y=580, name="top"))

        # A mark composed of another mark, with its own anchors
        g = font.newGlyph("dotbelow_special")
        g.width = 0
        pen = g.getPen()
        pen.addComponent("dotbelow", (1, 0, 0, 1, 0, 0))
        g.appendAnchor(dict(x=10, y=-110, name="_bottom"))
        g.appendAnchor(dict(x=10, y=10, name="bottom"))

        font.lib["public.openTypeCategories"] = {
            "dotbelow": "mark",
            "brevecomb": "mark",
            "dotbelow_special": "mark",
        }

        philter = PropagateAnchorsFilter()
        modified = philter(font)

        # Mark with own anchors: propagation skipped
        assert "dotbelow_special" not in modified
        anchors = [(a.name, a.x, a.y) for a in font["dotbelow_special"].anchors]
        assert anchors == [("_bottom", 10, -110), ("bottom", 10, 10)]

    def test_nested_composites_shared_component(self, FontClass):
        """Nested composites sharing a common component should get consistent
        anchor propagation regardless of processing order."""
        font = FontClass()
        g = font.newGlyph("base")
        g.width = 500
        pen = g.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((500, 0))
        pen.lineTo((250, 600))
        pen.closePath()
        g.appendAnchor(dict(x=250, y=600, name="top"))
        g.appendAnchor(dict(x=250, y=0, name="bottom"))

        g = font.newGlyph("mark1")
        g.width = 0
        pen = g.getPen()
        pen.moveTo((-30, 0))
        pen.lineTo((30, 0))
        pen.lineTo((0, 50))
        pen.closePath()
        g.appendAnchor(dict(x=0, y=0, name="_top"))
        g.appendAnchor(dict(x=0, y=50, name="top"))

        g = font.newGlyph("mark2")
        g.width = 0
        pen = g.getPen()
        pen.moveTo((-40, 0))
        pen.lineTo((40, 0))
        pen.lineTo((0, 60))
        pen.closePath()
        g.appendAnchor(dict(x=0, y=0, name="_top"))
        g.appendAnchor(dict(x=0, y=60, name="top"))

        # shared_comp uses base
        g = font.newGlyph("shared_comp")
        g.width = 500
        pen = g.getPen()
        pen.addComponent("base", (1, 0, 0, 1, 0, 0))

        # comp_a = shared_comp + mark1
        g = font.newGlyph("comp_a")
        g.width = 500
        pen = g.getPen()
        pen.addComponent("shared_comp", (1, 0, 0, 1, 0, 0))
        pen.addComponent("mark1", (1, 0, 0, 1, 250, 0))

        # comp_b = shared_comp + mark2
        g = font.newGlyph("comp_b")
        g.width = 500
        pen = g.getPen()
        pen.addComponent("shared_comp", (1, 0, 0, 1, 0, 0))
        pen.addComponent("mark2", (1, 0, 0, 1, 250, 0))

        font.lib["public.openTypeCategories"] = {
            "mark1": "mark",
            "mark2": "mark",
        }

        philter = PropagateAnchorsFilter()
        philter(font)

        # shared_comp should have same anchors as base
        assert {(a.name, a.x, a.y) for a in font["shared_comp"].anchors} == {
            ("top", 250, 600),
            ("bottom", 250, 0),
        }

        # comp_a: top replaced by mark1's top position (transformed)
        anchors_a = {(a.name, a.x, a.y) for a in font["comp_a"].anchors}
        assert ("bottom", 250, 0) in anchors_a
        assert ("top", 250, 50) in anchors_a  # mark1's top at (0+250, 50+0)

        # comp_b: top replaced by mark2's top position (transformed)
        anchors_b = {(a.name, a.x, a.y) for a in font["comp_b"].anchors}
        assert ("bottom", 250, 0) in anchors_b
        assert ("top", 250, 60) in anchors_b  # mark2's top at (0+250, 60+0)

    def test_anchor_ordering_deterministic(self, FontClass):
        """Propagated anchors should be in a deterministic order."""
        font = FontClass()
        g = font.newGlyph("base")
        g.width = 500
        pen = g.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((500, 0))
        pen.lineTo((250, 600))
        pen.closePath()
        g.appendAnchor(dict(x=250, y=600, name="top"))
        g.appendAnchor(dict(x=250, y=0, name="bottom"))
        g.appendAnchor(dict(x=250, y=300, name="center"))

        g = font.newGlyph("comp")
        g.width = 500
        pen = g.getPen()
        pen.addComponent("base", (1, 0, 0, 1, 0, 0))

        font.lib["public.openTypeCategories"] = {}

        philter = PropagateAnchorsFilter()
        philter(font)

        names = [a.name for a in font["comp"].anchors]
        assert names == sorted(names)

    def test_include_root_with_transitive_deps(self, FontClass):
        """When include is set, transitive component dependencies must also
        be written (the reduced Cantarell test depends on this)."""
        font = FontClass()
        g = font.newGlyph("base")
        g.width = 500
        pen = g.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((500, 0))
        pen.lineTo((250, 600))
        pen.closePath()
        g.appendAnchor(dict(x=250, y=600, name="top"))

        g = font.newGlyph("mid")
        g.width = 500
        pen = g.getPen()
        pen.addComponent("base", (1, 0, 0, 1, 0, 0))

        g = font.newGlyph("topglyph")
        g.width = 500
        pen = g.getPen()
        pen.addComponent("mid", (1, 0, 0, 1, 0, 0))

        font.lib["public.openTypeCategories"] = {}

        # Only include the top-level glyph
        philter = PropagateAnchorsFilter(include={"topglyph"})
        modified = philter(font)

        # Both mid and topglyph should be modified (mid is a transitive dep)
        assert "mid" in modified
        assert "topglyph" in modified
        assert [(a.name, a.x, a.y) for a in font["mid"].anchors] == [("top", 250, 600)]
        assert [(a.name, a.x, a.y) for a in font["topglyph"].anchors] == [
            ("top", 250, 600)
        ]


class AlgorithmDetailTest:
    """Tests for ufo2ft-specific algorithm details not covered by the ported suite."""

    def test_bottom_top_cancellation(self, FontClass):
        """When a non-mark composite has _bottom in its own anchors,
        propagated 'top' and '_top' from components are removed."""
        font = FontClass()
        g = font.newGlyph("base")
        g.width = 500
        pen = g.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((500, 0))
        pen.lineTo((250, 600))
        pen.closePath()
        g.appendAnchor(dict(x=250, y=600, name="top"))
        g.appendAnchor(dict(x=250, y=0, name="bottom"))

        # Non-mark composite that declares _bottom (attaches below something)
        # but is NOT classified as mark, so propagation runs
        g = font.newGlyph("comp")
        g.width = 500
        pen = g.getPen()
        pen.addComponent("base", (1, 0, 0, 1, 0, 0))
        g.appendAnchor(dict(x=250, y=-50, name="_bottom"))

        # Explicitly classify as base so the mark heuristic doesn't trigger
        font.lib["public.openTypeCategories"] = {"comp": "base"}

        philter = PropagateAnchorsFilter()
        philter(font)

        anchors = {(a.name, a.x, a.y) for a in font["comp"].anchors}
        # _bottom is present on the composite itself, so propagated 'top'
        # and '_top' from components should be cancelled
        assert ("_bottom", 250, -50) in anchors
        assert ("bottom", 250, 0) in anchors
        assert not any(a[0] == "top" for a in anchors)
        assert not any(a[0] == "_top" for a in anchors)

    def test_absent_categories_fallback_heuristics(self, FontClass):
        """When public.openTypeCategories is completely absent, the algorithm
        falls back to heuristics: _-prefixed anchors -> mark, _ in name -> ligature."""
        font = FontClass()
        g = font.newGlyph("a")
        g.width = 350
        pen = g.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((300, 0))
        pen.lineTo((300, 300))
        pen.lineTo((0, 300))
        pen.closePath()
        g.appendAnchor(dict(x=150, y=300, name="top"))
        g.appendAnchor(dict(x=150, y=0, name="bottom"))

        g = font.newGlyph("acutecomb")
        g.width = 0
        pen = g.getPen()
        pen.moveTo((0, 500))
        pen.lineTo((50, 600))
        pen.lineTo((-50, 600))
        pen.closePath()
        g.appendAnchor(dict(x=0, y=500, name="_top"))
        g.appendAnchor(dict(x=0, y=620, name="top"))

        # Mark (inferred from _top anchor)
        g = font.newGlyph("aacute")
        g.width = 350
        pen = g.getPen()
        pen.addComponent("a", (1, 0, 0, 1, 0, 0))
        pen.addComponent("acutecomb", (1, 0, 0, 1, 150, 0))

        # Ligature (inferred from _ in name)
        g = font.newGlyph("a_a")
        g.width = 700
        pen = g.getPen()
        pen.addComponent("a", (1, 0, 0, 1, 0, 0))
        pen.addComponent("a", (1, 0, 0, 1, 350, 0))

        # No categories at all
        font.lib["public.openTypeCategories"] = {}

        from fontTools.misc.loggingTools import CapturingLogHandler

        with CapturingLogHandler(logger, level="WARNING") as captor:
            philter = PropagateAnchorsFilter()
            philter(font)

        captor.assertRegex("public.openTypeCategories not found or empty")

        # aacute: mark attachment works via heuristic
        anchors_aacute = {(a.name, a.x, a.y) for a in font["aacute"].anchors}
        assert ("bottom", 150, 0) in anchors_aacute
        assert ("top", 150, 620) in anchors_aacute

        # a_a: no ligature inference from name alone, and no caret_N anchors;
        # second component's anchors overwrite first's
        anchors_aa = {(a.name, a.x, a.y) for a in font["a_a"].anchors}
        assert ("top", 500, 300) in anchors_aa
        assert ("bottom", 500, 0) in anchors_aa
        assert not any("_1" in a[0] or "_2" in a[0] for a in anchors_aa)

    def test_partial_categories(self, FontClass):
        """When public.openTypeCategories is present but partial, the fallback
        heuristic does NOT activate — only explicitly classified glyphs are
        marked/ligature."""
        font = FontClass()
        g = font.newGlyph("a")
        g.width = 350
        pen = g.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((300, 0))
        pen.lineTo((300, 300))
        pen.lineTo((0, 300))
        pen.closePath()
        g.appendAnchor(dict(x=150, y=300, name="top"))
        g.appendAnchor(dict(x=150, y=0, name="bottom"))

        # a_a is NOT classified as ligature in the partial categories
        g = font.newGlyph("a_a")
        g.width = 700
        pen = g.getPen()
        pen.addComponent("a", (1, 0, 0, 1, 0, 0))
        pen.addComponent("a", (1, 0, 0, 1, 350, 0))

        # Partial categories: only 'a' is classified
        font.lib["public.openTypeCategories"] = {"a": "base"}

        philter = PropagateAnchorsFilter()
        philter(font)

        # Without ligature classification, second 'a' overwrites first
        anchors = {(a.name, a.x, a.y) for a in font["a_a"].anchors}
        assert ("top", 500, 300) in anchors
        assert ("bottom", 500, 0) in anchors
        assert not any("_1" in a[0] or "_2" in a[0] for a in anchors)


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

    def test_openTypeCategories_from_kwargs(self, FontClass):
        """When openTypeCategories is passed via kwargs (from the DS lib),
        the IFilter uses it for classification instead of reading from
        individual UFO libs."""
        font = FontClass()
        for name, width, anchors in [
            ("a", 350, [("top", 175, 300), ("bottom", 175, 0)]),
            ("b", 350, [("top", 175, 300), ("bottom", 175, 0)]),
        ]:
            g = font.newGlyph(name)
            g.width = width
            pen = g.getPen()
            pen.moveTo((0, 0))
            pen.lineTo((300, 0))
            pen.lineTo((300, 300))
            pen.lineTo((0, 300))
            pen.closePath()
            for aname, ax, ay in anchors:
                g.appendAnchor(dict(name=aname, x=ax, y=ay))
        # a_b is a composite ligature with no own anchors
        g = font.newGlyph("a_b")
        g.width = 700
        pen = g.getPen()
        pen.addComponent("a", (1, 0, 0, 1, 0, 0))
        pen.addComponent("b", (1, 0, 0, 1, 350, 0))

        # No categories in font.lib — the IFilter would fall back to heuristics
        assert "public.openTypeCategories" not in font.lib

        glyphSets = [_GlyphSet.from_layer(font)]
        philter = PropagateAnchorsIFilter()

        # Without categories: a_b gets unnumbered anchors (not a ligature)
        philter([font], glyphSets)
        anchors_no_cats = {a.name for a in glyphSets[0]["a_b"].anchors}
        assert "top_1" not in anchors_no_cats

        # Reset
        glyphSets = [_GlyphSet.from_layer(font)]

        # With DS-level categories via kwargs: a_b gets numbered anchors
        ds_categories = {"a_b": "ligature"}
        philter([font], glyphSets, openTypeCategories=ds_categories)
        anchor_names = {a.name for a in glyphSets[0]["a_b"].anchors}
        assert "top_1" in anchor_names
        assert "top_2" in anchor_names
        assert "bottom_1" in anchor_names
        assert "bottom_2" in anchor_names

    def test_preliminary_categories_finalization(self, FontClass):
        """preliminaryOpenTypeCategories are used for classification during
        propagation, then finalized (anchorless ligatures pruned, bases
        inferred) and written to font.lib."""
        font = FontClass()
        # Base glyph with attaching anchors
        g = font.newGlyph("a")
        g.width = 350
        pen = g.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((300, 0))
        pen.lineTo((300, 300))
        pen.lineTo((0, 300))
        pen.closePath()
        g.appendAnchor(dict(name="top", x=150, y=300))
        g.appendAnchor(dict(name="bottom", x=150, y=0))

        # Mark glyph
        g = font.newGlyph("acutecomb")
        g.width = 0
        pen = g.getPen()
        pen.moveTo((0, 400))
        pen.lineTo((100, 500))
        pen.lineTo((0, 500))
        pen.closePath()
        g.appendAnchor(dict(name="_top", x=50, y=400))
        g.appendAnchor(dict(name="top", x=50, y=550))

        # Composite ligature a_a — should get numbered anchors
        g = font.newGlyph("a_a")
        g.width = 700
        pen = g.getPen()
        pen.addComponent("a", (1, 0, 0, 1, 0, 0))
        pen.addComponent("a", (1, 0, 0, 1, 350, 0))

        # Composite glyph, not explicitly categorized — should be inferred as base
        g = font.newGlyph("aacute")
        g.width = 350
        pen = g.getPen()
        pen.addComponent("a", (1, 0, 0, 1, 0, 0))
        pen.addComponent("acutecomb", (1, 0, 0, 1, 0, 0))

        # Ligature without any anchors — should be pruned
        g = font.newGlyph("noanchors_liga")
        g.width = 350
        pen = g.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((300, 0))
        pen.lineTo((300, 300))
        pen.lineTo((0, 300))
        pen.closePath()

        # Spacing glyph (acute, not a combining mark) — should NOT become mark
        g = font.newGlyph("acute")
        g.width = 200
        pen = g.getPen()
        pen.addComponent("acutecomb", (1, 0, 0, 1, 100, 0))

        assert "public.openTypeCategories" not in font.lib

        preliminary = {
            "acutecomb": "mark",
            "a_a": "ligature",
            "noanchors_liga": "ligature",
        }

        glyphSets = [_GlyphSet.from_layer(font)]
        philter = PropagateAnchorsIFilter()
        philter([font], glyphSets, preliminaryOpenTypeCategories=preliminary)

        # Finalized categories should be written to font.lib
        assert "public.openTypeCategories" in font.lib
        cats = font.lib["public.openTypeCategories"]

        # Mark stays mark
        assert cats["acutecomb"] == "mark"
        # Ligature with attaching anchors stays ligature
        assert cats["a_a"] == "ligature"
        # Ligature without attaching anchors is pruned (not in result)
        assert "noanchors_liga" not in cats
        # Base glyph inferred from attaching anchors
        assert cats["a"] == "base"
        # Composite base inferred
        assert cats["aacute"] == "base"
        # Spacing acute: has propagated _top + top from acutecomb.
        # top is attaching, so it becomes base (not mark — not in preliminary marks)
        assert cats["acute"] == "base"

        # Check a_a got numbered anchors (ligature propagation worked)
        anchor_names = {a.name for a in glyphSets[0]["a_a"].anchors}
        assert "top_1" in anchor_names
        assert "top_2" in anchor_names

    def test_preliminary_categories_ignored_when_source_has_categories(self, FontClass):
        """Source-level openTypeCategories takes precedence over preliminary."""
        font = FontClass()
        g = font.newGlyph("a")
        g.width = 350
        pen = g.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((300, 0))
        pen.lineTo((300, 300))
        pen.lineTo((0, 300))
        pen.closePath()
        g.appendAnchor(dict(name="top", x=150, y=300))

        # Source has explicit categories
        ds_categories = {"a": "base"}
        preliminary = {"a": "mark"}  # conflicting

        glyphSets = [_GlyphSet.from_layer(font)]
        philter = PropagateAnchorsIFilter()
        philter(
            [font],
            glyphSets,
            openTypeCategories=ds_categories,
            preliminaryOpenTypeCategories=preliminary,
        )

        # Source-level takes precedence: no finalized categories written
        # (source already has them)
        assert OPENTYPE_CATEGORIES_KEY not in font.lib

    def test_preliminary_categories_ignored_when_ufo_has_categories(self, FontClass):
        """UFO-level openTypeCategories takes precedence over preliminary."""
        font = FontClass()
        _make_glyph(
            font,
            "a",
            350,
            anchors=[("top", (150, 300)), ("bottom", (150, 0))],
        )
        _make_glyph(
            font,
            "a_a",
            700,
            contour=False,
            components=[("a", (0, 0)), ("a", (350, 0))],
        )

        font.lib[OPENTYPE_CATEGORIES_KEY] = {"a_a": "base"}
        preliminary = {"a_a": "ligature"}

        glyphSets = [_GlyphSet.from_layer(font)]
        philter = PropagateAnchorsIFilter()
        philter([font], glyphSets, preliminaryOpenTypeCategories=preliminary)

        assert font.lib[OPENTYPE_CATEGORIES_KEY] == {"a_a": "base"}
        anchor_names = {a.name for a in glyphSets[0]["a_a"].anchors}
        assert "top" in anchor_names
        assert "top_1" not in anchor_names
        assert "top_2" not in anchor_names

    def test_depth_sort_uses_component_graphs_from_all_masters(self, FontClass):
        """IFilter ordering must honor deeper component chains in any master."""
        font1 = FontClass()
        _make_glyph(font1, "zz", 350, anchors=[("top", (150, 300))])
        _make_glyph(font1, "mid", 350, anchors=[("top", (150, 300))])
        _make_glyph(
            font1,
            "root",
            350,
            contour=False,
            components=[("mid", (0, 0))],
        )

        font2 = FontClass()
        _make_glyph(font2, "zz", 350, anchors=[("top", (150, 300))])
        _make_glyph(font2, "mid", 350, contour=False, components=[("zz", (0, 0))])
        _make_glyph(
            font2,
            "root",
            350,
            contour=False,
            components=[("mid", (0, 0))],
        )

        glyphSets = [_GlyphSet.from_layer(font1), _GlyphSet.from_layer(font2)]
        philter = PropagateAnchorsIFilter()
        philter([font1, font2], glyphSets)

        assert [(a.name, a.x, a.y) for a in glyphSets[1]["mid"].anchors] == [
            ("top", 150, 300)
        ]
        assert [(a.name, a.x, a.y) for a in glyphSets[1]["root"].anchors] == [
            ("top", 150, 300)
        ]


def test_single_master_preliminary_categories_finalization(FontClass):
    """The single-master filter reads preliminary categories from the private
    lib key (written by the preprocessor) and finalizes after propagation."""
    font = FontClass()
    g = font.newGlyph("a")
    g.width = 350
    pen = g.getPen()
    pen.moveTo((0, 0))
    pen.lineTo((300, 0))
    pen.lineTo((300, 300))
    pen.lineTo((0, 300))
    pen.closePath()
    g.appendAnchor(dict(name="top", x=150, y=300))
    g.appendAnchor(dict(name="bottom", x=150, y=0))

    g = font.newGlyph("acutecomb")
    g.width = 0
    pen = g.getPen()
    pen.moveTo((0, 400))
    pen.lineTo((100, 500))
    pen.lineTo((0, 500))
    pen.closePath()
    g.appendAnchor(dict(name="_top", x=50, y=400))
    g.appendAnchor(dict(name="top", x=50, y=550))

    g = font.newGlyph("a_a")
    g.width = 700
    pen = g.getPen()
    pen.addComponent("a", (1, 0, 0, 1, 0, 0))
    pen.addComponent("a", (1, 0, 0, 1, 350, 0))

    g = font.newGlyph("aacute")
    g.width = 350
    pen = g.getPen()
    pen.addComponent("a", (1, 0, 0, 1, 0, 0))
    pen.addComponent("acutecomb", (1, 0, 0, 1, 0, 0))

    preliminary = {"acutecomb": "mark", "a_a": "ligature"}
    font.lib[_PRELIMINARY_CATEGORIES_KEY] = preliminary

    philter = PropagateAnchorsFilter()
    philter(font)

    assert _PRELIMINARY_CATEGORIES_KEY not in font.lib
    cats = font.lib[OPENTYPE_CATEGORIES_KEY]
    assert cats["acutecomb"] == "mark"
    assert cats["a_a"] == "ligature"
    assert cats["a"] == "base"
    assert cats["aacute"] == "base"

    anchor_names = {a.name for a in font["a_a"].anchors}
    assert "top_1" in anchor_names
    assert "top_2" in anchor_names


def test_single_master_preliminary_ignored_when_source_has_categories(FontClass):
    """Source-level categories take precedence over preliminary in single-master."""
    font = FontClass()
    g = font.newGlyph("a")
    g.width = 350
    pen = g.getPen()
    pen.moveTo((0, 0))
    pen.lineTo((300, 0))
    pen.lineTo((300, 300))
    pen.lineTo((0, 300))
    pen.closePath()
    g.appendAnchor(dict(name="top", x=150, y=300))

    font.lib[OPENTYPE_CATEGORIES_KEY] = {"a": "base"}
    font.lib[_PRELIMINARY_CATEGORIES_KEY] = {"a": "mark"}

    philter = PropagateAnchorsFilter()
    philter(font)

    assert font.lib[OPENTYPE_CATEGORIES_KEY] == {"a": "base"}


class FinalizeCategoriesTest:
    def test_marks_unchanged(self):
        done_anchors = {
            "acutecomb": [AnchorData("_top", 0, 400), AnchorData("top", 0, 550)],
        }
        result = _finalize_categories({"acutecomb": "mark"}, done_anchors)
        assert result["acutecomb"] == "mark"

    def test_ligature_with_anchors_kept(self):
        done_anchors = {
            "f_i": [AnchorData("top_1", 100, 700), AnchorData("top_2", 300, 700)],
        }
        result = _finalize_categories({"f_i": "ligature"}, done_anchors)
        assert result["f_i"] == "ligature"

    def test_ligature_without_anchors_pruned(self):
        done_anchors = {
            "f_i": [],
        }
        result = _finalize_categories({"f_i": "ligature"}, done_anchors)
        assert "f_i" not in result

    def test_ligature_with_only_underscore_anchors_pruned(self):
        done_anchors = {
            "f_i": [AnchorData("_top", 0, 400)],
        }
        result = _finalize_categories({"f_i": "ligature"}, done_anchors)
        assert "f_i" not in result

    def test_base_inferred_from_attaching_anchors(self):
        done_anchors = {
            "a": [AnchorData("top", 150, 300), AnchorData("bottom", 150, 0)],
        }
        result = _finalize_categories({}, done_anchors)
        assert result["a"] == "base"

    def test_no_category_without_attaching_anchors(self):
        done_anchors = {
            "space": [],
        }
        result = _finalize_categories({}, done_anchors)
        assert "space" not in result

    def test_mark_not_reclassified_as_base(self):
        done_anchors = {
            "acutecomb": [AnchorData("_top", 0, 400), AnchorData("top", 0, 550)],
        }
        result = _finalize_categories({"acutecomb": "mark"}, done_anchors)
        assert result["acutecomb"] == "mark"
