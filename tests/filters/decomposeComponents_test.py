from __future__ import (
    print_function,
    division,
    absolute_import,
    unicode_literals,
)
from ufo2ft.filters.decomposeComponents import (
    DecomposeComponentsFilter,
    logger,
)
import logging


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
