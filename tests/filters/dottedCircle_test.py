import pytest
from fontTools.misc.loggingTools import CapturingLogHandler

import ufo2ft.filters
from ufo2ft.filters.dottedCircleFilter import DottedCircleFilter, logger

def test_dotted_circle_filter(FontClass, datadir):
    ufo_path = datadir.join("DottedCircleTest.ufo")
    font = FontClass(ufo_path)
    assert "uni25CC" not in font
    philter = DottedCircleFilter()
    modified = philter(font)
    assert "uni25CC" in modified
    anchors = list(sorted(font["uni25CC"].anchors, key=lambda x:x.name))
    assert anchors[0].x == 464
    assert anchors[0].y == -17
    assert anchors[0].name == "bottom"

    assert anchors[1].x == 563
    assert anchors[1].y == 546
    assert anchors[1].name == "top"

    assert len(font["uni25CC"]) == 12
    assert int(font["uni25CC"].width) == 688
