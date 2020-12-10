import logging

from ufo2ft.filters.decomposeComponents import DecomposeComponentsFilter
from ufo2ft.util import logger


def test_missing_component_is_dropped(FontClass, caplog):
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

    with caplog.at_level(logging.WARNING, logger=logger.name):
        filter_ = DecomposeComponentsFilter()

    assert filter_(ufo)
    assert len(ufo["aacute"]) == 1
    assert len(ufo["aacute"].components) == 0

    assert len(caplog.records) == 1
    assert "dropping non-existent component" in caplog.text


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
