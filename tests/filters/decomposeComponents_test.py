import logging

import pytest
from fontTools.pens.basePen import MissingComponentError

from ufo2ft.filters.decomposeComponents import (
    DecomposeComponentsFilter,
    DecomposeComponentsIFilter,
)
from ufo2ft.instantiator import Instantiator
from ufo2ft.util import _GlyphSet


def test_missing_component_error(FontClass, caplog):
    ufo = FontClass()
    a = ufo.newGlyph("a")
    a.width = 100
    pen = a.getPen()
    pen.moveTo((0, 0))
    pen.lineTo((300, 0))
    pen.lineTo((300, 300))
    pen.lineTo((0, 300))
    pen.closePath()

    aacute = ufo.newGlyph("aacute")
    aacute.width = 100
    pen = aacute.getPen()
    pen.addComponent("a", (1, 0, 0, 1, 0, 0))
    pen.addComponent("acute", (1, 0, 0, 1, 350, 0))  # missing

    assert len(ufo["aacute"]) == 0
    assert len(ufo["aacute"].components) == 2

    filter_ = DecomposeComponentsFilter()

    with pytest.raises(MissingComponentError, match="'acute'"):
        filter_(ufo)


def test_nested_components(FontClass):
    ufo = FontClass()
    a = ufo.newGlyph("six.lf")
    a.width = 100
    pen = a.getPen()
    pen.moveTo((0, 0))
    pen.lineTo((300, 0))
    pen.lineTo((300, 300))
    pen.lineTo((0, 300))
    pen.closePath()

    b = ufo.newGlyph("nine.lf")
    b.width = 100
    pen = b.getPen()
    pen.addComponent("six.lf", (-1, 0, 0, -1, 0, 0))

    c = ufo.newGlyph("nine")
    c.width = 100
    pen = c.getPen()
    pen.addComponent("nine.lf", (1, 0, 0, 1, 0, 0))

    filter_ = DecomposeComponentsFilter()

    assert filter_(ufo)
    assert len(ufo["six.lf"]) == 1
    assert not ufo["six.lf"].components
    assert len(ufo["nine.lf"]) == 1
    assert not ufo["nine.lf"].components
    assert len(ufo["nine"]) == 1
    assert not ufo["nine"].components


@pytest.fixture
def ufos_and_glyphSets(FontClass):
    """Return two parallel lists of UFOs and glyphSets for testing.

    This fixture creates two UFOs, a Regular and a Bold, each containing 5 glyphs:
    "agrave" composite glyph composed from "a" and "gravecomb" components,
    both in turn simple contour glyphs, and "igrave" composed of "dotlessi" and
    "gravecomb" components.
    The Regular UFO also contains a 'sparse' Medium layer with only two glyphs:
    a different "agrave" composite glyph, but no "a" nor "gravecomb" components;
    and a different shape for the "dotlessi" glyph, but no "igrave" nor "gravecomb".

    The decomposing (interpolatable) filter should interpolate the missing
    components or composites on-the-fly using the instantiator, when available.
    """

    regular_ufo = FontClass()

    a = regular_ufo.newGlyph("a")
    a.width = 500
    a.unicodes = [ord("a")]
    pen = a.getPointPen()
    pen.beginPath()
    pen.addPoint((100, 0), "line")
    pen.addPoint((400, 0), "line")
    pen.addPoint((400, 500), "line")
    pen.addPoint((100, 500), "line")
    pen.endPath()

    i = regular_ufo.newGlyph("dotlessi")
    i.width = 300
    i.unicodes = [0x0131]
    pen = i.getPointPen()
    pen.beginPath()
    pen.addPoint((100, 0), "line")
    pen.addPoint((200, 0), "line")
    pen.addPoint((200, 500), "line")
    pen.addPoint((100, 500), "line")
    pen.endPath()

    gravecomb = regular_ufo.newGlyph("gravecomb")
    gravecomb.unicodes = [0x0300]
    pen = gravecomb.getPointPen()
    pen.beginPath()
    pen.addPoint((30, 550), "line")
    pen.addPoint((0, 750), "line")
    pen.addPoint((-50, 750), "line")
    pen.addPoint((0, 550), "line")
    pen.endPath()

    agrave = regular_ufo.newGlyph("agrave")
    agrave.width = a.width
    agrave.unicodes = [0x00E0]
    pen = agrave.getPointPen()
    pen.addComponent("a", (1, 0, 0, 1, 0, 0))
    pen.addComponent("gravecomb", (1, 0, 0, 1, 250, 0))

    igrave = regular_ufo.newGlyph("igrave")
    igrave.width = i.width
    igrave.unicodes = [0x00EC]
    pen = igrave.getPointPen()
    pen.addComponent("dotlessi", (1, 0, 0, 1, 0, 0))
    pen.addComponent("gravecomb", (1, 0, 0, 1, 150, 0))

    # The Medium layer has "agrave" but does not have "a" and "gravecomb"
    medium_layer = regular_ufo.newLayer("Medium")

    agrave = medium_layer.newGlyph("agrave")
    agrave.width = 550
    pen = agrave.getPointPen()
    pen.addComponent("a", (1, 0, 0, 1, 0, 0))
    pen.addComponent("gravecomb", (1, 0, 0, 1, 275, 0))

    # The Medium layer also has a different "dotlessi" glyph, which the
    # other layers don't have.
    i = medium_layer.newGlyph("dotlessi")
    i.width = 350
    pen = i.getPointPen()
    pen.beginPath()
    pen.addPoint((100, 0), "line")
    pen.addPoint((250, 0), "line")
    pen.addPoint((175, 500), "line")
    pen.addPoint((175, 500), "line")
    pen.endPath()

    bold_ufo = FontClass()

    a = bold_ufo.newGlyph("a")
    a.width = 600
    pen = a.getPointPen()
    pen.beginPath()
    pen.addPoint((150, 0), "line")
    pen.addPoint((450, 0), "line")
    pen.addPoint((450, 500), "line")
    pen.addPoint((150, 500), "line")
    pen.endPath()

    i = bold_ufo.newGlyph("dotlessi")
    i.width = 400
    pen = i.getPointPen()
    pen.beginPath()
    pen.addPoint((100, 0), "line")
    pen.addPoint((300, 0), "line")
    pen.addPoint((300, 500), "line")
    pen.addPoint((100, 500), "line")
    pen.endPath()

    gravecomb = bold_ufo.newGlyph("gravecomb")
    pen = gravecomb.getPointPen()
    pen.beginPath()
    pen.addPoint((40, 550), "line")
    pen.addPoint((0, 750), "line")
    pen.addPoint((-70, 750), "line")
    pen.addPoint((0, 550), "line")
    pen.endPath()

    agrave = bold_ufo.newGlyph("agrave")
    agrave.width = a.width
    pen = agrave.getPointPen()
    pen.addComponent("a", (1, 0, 0, 1, 0, 0))
    pen.addComponent("gravecomb", (1, 0, 0, 1, 300, 0))

    igrave = bold_ufo.newGlyph("igrave")
    igrave.width = i.width
    pen = igrave.getPointPen()
    pen.addComponent("dotlessi", (1, 0, 0, 1, 0, 0))
    pen.addComponent("gravecomb", (1, 0, 0, 1, 200, 0))

    ufos = [regular_ufo, regular_ufo, bold_ufo]
    glyphSets = [
        _GlyphSet.from_layer(regular_ufo),
        _GlyphSet.from_layer(regular_ufo, layerName="Medium"),
        _GlyphSet.from_layer(bold_ufo),
    ]
    return ufos, glyphSets


class DecomposeComponentsIFilterTest:
    def test_composite_with_intermediate_master(self, ufos_and_glyphSets):
        ufos, glyphSets = ufos_and_glyphSets
        regular_glyphs, medium_glyphs, bold_glyphs = glyphSets
        assert "agrave" in medium_glyphs
        assert {"a", "gravecomb"}.isdisjoint(medium_glyphs)

        instantiator = Instantiator(
            {"Weight": (100, 100, 200)},
            [
                ({"Weight": 100}, regular_glyphs),
                ({"Weight": 150}, medium_glyphs),
                ({"Weight": 200}, bold_glyphs),
            ],
        )
        filter_ = DecomposeComponentsIFilter(include={"agrave"})

        modified = filter_(ufos, glyphSets, instantiator=instantiator)

        assert modified == {"agrave"}

        agrave = regular_glyphs["agrave"]
        assert len(agrave.components) == 0
        assert [[(p.x, p.y) for p in c] for c in agrave] == [
            [(100, 0), (400, 0), (400, 500), (100, 500)],
            [(280, 550), (250, 750), (200, 750), (250, 550)],
        ]

        # 'agrave' was fully decomposed also in the medium layer, despite the
        # latter not containing sources for the "a" and "gravecomb" component glyphs.
        # These were interpolated on-the-fly while decomposing the composite glyph.
        agrave = medium_glyphs["agrave"]
        assert len(agrave.components) == 0
        assert [[(p.x, p.y) for p in c] for c in agrave] == [
            [(125, 0), (425, 0), (425, 500), (125, 500)],
            [(310, 550), (275, 750), (215, 750), (275, 550)],
        ]

        agrave = bold_glyphs["agrave"]
        assert len(agrave.components) == 0
        assert [[(p.x, p.y) for p in c] for c in agrave] == [
            [(150, 0), (450, 0), (450, 500), (150, 500)],
            [(340, 550), (300, 750), (230, 750), (300, 550)],
        ]

    def test_component_with_intermediate_master(self, ufos_and_glyphSets):
        ufos, glyphSets = ufos_and_glyphSets
        regular_glyphs, medium_glyphs, bold_glyphs = glyphSets
        assert {"dotlessi", "gravecomb", "igrave"}.issubset(regular_glyphs)
        assert {"dotlessi", "gravecomb", "igrave"}.issubset(bold_glyphs)
        assert "dotlessi" in medium_glyphs
        assert {"igrave", "gravecomb"}.isdisjoint(medium_glyphs)

        instantiator = Instantiator(
            {"Weight": (100, 100, 200)},
            [
                ({"Weight": 100}, regular_glyphs),
                ({"Weight": 150}, medium_glyphs),
                ({"Weight": 200}, bold_glyphs),
            ],
        )
        filter_ = DecomposeComponentsIFilter(include={"igrave"})

        modified = filter_(ufos, glyphSets, instantiator=instantiator)

        assert modified == {"igrave"}

        igrave = regular_glyphs["igrave"]
        assert len(igrave.components) == 0
        assert [[(p.x, p.y) for p in c] for c in igrave] == [
            [(100, 0), (200, 0), (200, 500), (100, 500)],
            [(180, 550), (150, 750), (100, 750), (150, 550)],
        ]

        # 'igrave' was also decomposed in the Medium layer, despite it was not
        # originally present; it was added by the filter and interpolated on-the-fly,
        # because Medium contained a different 'dotlessi' used as a component.
        igrave = medium_glyphs["igrave"]
        assert len(igrave.components) == 0
        assert [[(p.x, p.y) for p in c] for c in igrave] == [
            [(100, 0), (250, 0), (175, 500), (175, 500)],
            [(210, 550), (175, 750), (115, 750), (175, 550)],
        ]
        assert {"dotlessi", "igrave"}.issubset(medium_glyphs)
        assert "gravecomb" not in medium_glyphs

        igrave = bold_glyphs["igrave"]
        assert len(igrave.components) == 0
        assert [[(p.x, p.y) for p in c] for c in igrave] == [
            [(100, 0), (300, 0), (300, 500), (100, 500)],
            [(240, 550), (200, 750), (130, 750), (200, 550)],
        ]

    def test_without_instantiator(self, ufos_and_glyphSets):
        # without an instantiator (i.e. when the filter is run from the legacy
        # `compileInterpolatableTTFs` without a designspace as input but only a buch
        # of UFOs), the filter will raise a MissingComponentError while
        # trying to decompose 'agrave', because it can't interpolate the missing
        # components 'a' and 'gravecomb'
        ufos, glyphSets = ufos_and_glyphSets
        medium_glyphs = glyphSets[1]
        assert {"agrave", "dotlessi"}.issubset(medium_glyphs)
        assert {"a", "gravecomb", "igrave"}.isdisjoint(medium_glyphs)

        with pytest.raises(MissingComponentError, match="'a'"):
            DecomposeComponentsIFilter(include={"agrave"})(ufos, glyphSets)

        # the filter will not fail to decompose 'igrave' in Regular or Bold, however the
        # Medium master will not contain decomposed outlines for 'igrave', and
        # in the VF produced from these masters the 'igrave' will appear different
        # at runtime from 'dotlessi' when the Medium instance is selected.
        modified = DecomposeComponentsIFilter(include={"igrave"})(ufos, glyphSets)
        assert modified == {"igrave"}
        assert "igrave" not in medium_glyphs

    def test_locations_from_component_glyphs_get_cached(
        self, caplog, ufos_and_glyphSets
    ):
        ufos, glyphSets = ufos_and_glyphSets
        regular_glyphs, medium_glyphs, bold_glyphs = glyphSets
        instantiator = Instantiator(
            {"Weight": (100, 100, 200)},
            [
                ({"Weight": 100}, regular_glyphs),
                ({"Weight": 150}, medium_glyphs),
                ({"Weight": 200}, bold_glyphs),
            ],
        )
        philter = DecomposeComponentsIFilter()
        philter.set_context(ufos, glyphSets, instantiator)

        igrave_locations = philter.glyphSourceLocations("igrave")

        # igrave is defined only at Weight 100 and 200
        assert igrave_locations == {
            frozenset({("Weight", 100)}),
            frozenset({("Weight", 200)}),
        }

        # locationsFromComponentGlyphs logs DEBUG messages while traversing
        # recursively each component glyph
        with caplog.at_level(logging.DEBUG, logger="ufo2ft.filters"):
            component_locations = philter.locationsFromComponentGlyphs("igrave")

        assert "igrave" in caplog.text
        assert "dotlessi" in caplog.text
        assert "gravecomb" in caplog.text

        # one of igrave's components (dotlessi) is also defined at Weight 150
        expected_component_locations = igrave_locations | {frozenset({("Weight", 150)})}
        assert component_locations == expected_component_locations

        # locationsFromComponentGlyphs uses a cache to avoid traversing again component
        # glyphs that were visited before; its result isn't expected to change within
        # the current filter call.
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="ufo2ft.filters"):
            component_locations = philter.locationsFromComponentGlyphs("igrave")

        assert "igrave" in caplog.text
        assert "dotlessi" not in caplog.text
        assert "gravecomb" not in caplog.text
        assert component_locations == expected_component_locations
