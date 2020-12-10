import logging

import pytest

import ufo2ft
import ufo2ft.filters.sortContours


@pytest.fixture
def font(request, datadir, FontClass):
    font = FontClass(datadir.join("ContourOrderTest.ufo"))
    return font


def test_sort_contour_order(font, FontClass):
    test_ufo = FontClass()
    font_compiled = ufo2ft.compileTTF(font, inplace=True)
    font_glyf = font_compiled["glyf"]

    glyph_uniFFFC = font_glyf["uniFFFC"]
    glyph_test1 = test_ufo.newGlyph("test1")
    glyph_uniFFFC.draw(glyph_test1.getPen(), font_glyf)
    assert [
        [(p.x, p.y, p.segmentType, p.smooth) for p in c] for c in glyph_test1
    ] == EXPECTED_glyph_uniFFFC

    glyph_graphemejoinercomb = font_glyf["graphemejoinercomb"]
    glyph_test2 = test_ufo.newGlyph("test2")
    glyph_graphemejoinercomb.draw(glyph_test2.getPen(), font_glyf)
    assert [
        [(p.x, p.y, p.segmentType, p.smooth) for p in c] for c in glyph_test2
    ] == EXPECTED_glyph_graphemejoinercomb


def test_no_sort_contour_order(font, FontClass):
    test_ufo = FontClass()
    del font.lib["com.github.googlei18n.ufo2ft.filters"]
    font_compiled = ufo2ft.compileTTF(font, inplace=True)
    font_glyf = font_compiled["glyf"]

    glyph_uniFFFC = font_glyf["uniFFFC"]
    glyph_test1 = test_ufo.newGlyph("test1")
    glyph_uniFFFC.draw(glyph_test1.getPen(), font_glyf)
    assert [
        [(p.x, p.y, p.segmentType, p.smooth) for p in c] for c in glyph_test1
    ] != EXPECTED_glyph_uniFFFC

    glyph_graphemejoinercomb = font_glyf["graphemejoinercomb"]
    glyph_test2 = test_ufo.newGlyph("test2")
    glyph_graphemejoinercomb.draw(glyph_test2.getPen(), font_glyf)
    assert [
        [(p.x, p.y, p.segmentType, p.smooth) for p in c] for c in glyph_test2
    ] != EXPECTED_glyph_graphemejoinercomb


def test_warn_pre_filter(font, caplog):
    font.lib["com.github.googlei18n.ufo2ft.filters"][0]["pre"] = True
    font.lib["com.github.googlei18n.ufo2ft.filters"][0]["include"].append("xxx")

    with caplog.at_level(
        logging.WARNING, logger=ufo2ft.filters.sortContours.logger.name
    ):
        _ = ufo2ft.compileTTF(font, inplace=True)

    assert len(caplog.records) == 1
    assert "contains components which will not be sorted" in caplog.text


def test_no_warn_post_filter(font, caplog):
    font.lib["com.github.googlei18n.ufo2ft.filters"][0]["include"].append("xxx")

    with caplog.at_level(
        logging.WARNING, logger=ufo2ft.filters.sortContours.logger.name
    ):
        _ = ufo2ft.compileTTF(font, inplace=True)

    assert len(caplog.records) == 0


EXPECTED_glyph_uniFFFC = [
    [
        (41, -187, "line", False),
        (41, -39, "line", False),
        (95, -39, "line", False),
        (95, -134, "line", False),
        (189, -134, "line", False),
        (189, -187, "line", False),
    ],
    [
        (95, 19, "line", False),
        (41, 19, "line", False),
        (41, 151, "line", False),
        (95, 151, "line", False),
    ],
    [
        (95, 210, "line", False),
        (41, 210, "line", False),
        (41, 343, "line", False),
        (95, 343, "line", False),
    ],
    [
        (95, 402, "line", False),
        (41, 402, "line", False),
        (41, 534, "line", False),
        (95, 534, "line", False),
    ],
    [
        (41, 593, "line", False),
        (41, 741, "line", False),
        (189, 741, "line", False),
        (189, 687, "line", False),
        (95, 687, "line", False),
        (95, 593, "line", False),
    ],
    [
        (422, 307, "qcurve", True),
        (422, 241, None, False),
        (360, 160, None, False),
        (294, 160, "qcurve", True),
        (228, 160, None, False),
        (166, 241, None, False),
        (166, 307, "qcurve", True),
        (166, 374, None, False),
        (228, 454, None, False),
        (294, 454, "qcurve", True),
        (360, 454, None, False),
        (422, 374, None, False),
    ],
    [
        (228, 307, "qcurve", True),
        (228, 262, None, False),
        (260, 211, None, False),
        (294, 211, "qcurve", True),
        (329, 211, None, False),
        (360, 262, None, False),
        (360, 307, "qcurve", True),
        (360, 352, None, False),
        (329, 403, None, False),
        (294, 403, "qcurve", True),
        (260, 403, None, False),
        (228, 352, None, False),
    ],
    [
        (248, -187, "line", False),
        (248, -134, "line", False),
        (380, -134, "line", False),
        (380, -187, "line", False),
    ],
    [
        (248, 687, "line", False),
        (248, 741, "line", False),
        (380, 741, "line", False),
        (380, 687, "line", False),
    ],
    [
        (439, -187, "line", False),
        (439, -134, "line", False),
        (572, -134, "line", False),
        (572, -187, "line", False),
    ],
    [
        (439, 687, "line", False),
        (439, 741, "line", False),
        (572, 741, "line", False),
        (572, 687, "line", False),
    ],
    [
        (463, 450, "line", False),
        (547, 450, "line", True),
        (600, 450, None, False),
        (655, 418, None, False),
        (655, 377, "qcurve", True),
        (655, 353, None, False),
        (632, 321, None, False),
        (611, 317, "qcurve", False),
        (611, 313, "line", False),
        (633, 309, None, False),
        (663, 281, None, False),
        (663, 247, "qcurve", True),
        (663, 208, None, False),
        (610, 164, None, False),
        (564, 164, "qcurve", True),
        (463, 164, "line", False),
    ],
    [
        (523, 289, "line", False),
        (523, 214, "line", False),
        (559, 214, "line", True),
        (583, 214, None, False),
        (601, 235, None, False),
        (601, 253, "qcurve", True),
        (601, 269, None, False),
        (583, 289, None, False),
        (557, 289, "qcurve", True),
    ],
    [
        (523, 337, "line", False),
        (555, 337, "line", True),
        (578, 337, None, False),
        (595, 353, None, False),
        (595, 369, "qcurve", True),
        (595, 400, None, False),
        (552, 400, "qcurve", True),
        (523, 400, "line", False),
    ],
    [
        (630, -187, "line", False),
        (630, -134, "line", False),
        (763, -134, "line", False),
        (763, -187, "line", False),
    ],
    [
        (630, 687, "line", False),
        (630, 741, "line", False),
        (763, 741, "line", False),
        (763, 687, "line", False),
    ],
    [
        (728, 161, "qcurve", True),
        (704, 161, None, False),
        (689, 166, "qcurve", False),
        (689, 216, "line", False),
        (697, 215, None, False),
        (712, 212, None, False),
        (722, 212, "qcurve", True),
        (740, 212, None, False),
        (764, 229, None, False),
        (764, 254, "qcurve", True),
        (764, 450, "line", False),
        (825, 450, "line", False),
        (825, 256, "line", True),
        (825, 207, None, False),
        (771, 161, None, False),
    ],
    [
        (821, -187, "line", False),
        (821, -134, "line", False),
        (916, -134, "line", False),
        (916, -39, "line", False),
        (969, -39, "line", False),
        (969, -187, "line", False),
    ],
    [
        (821, 687, "line", False),
        (821, 741, "line", False),
        (969, 741, "line", False),
        (969, 593, "line", False),
        (916, 593, "line", False),
        (916, 687, "line", False),
    ],
    [
        (969, 19, "line", False),
        (916, 19, "line", False),
        (916, 151, "line", False),
        (969, 151, "line", False),
    ],
    [
        (969, 210, "line", False),
        (916, 210, "line", False),
        (916, 343, "line", False),
        (969, 343, "line", False),
    ],
    [
        (969, 402, "line", False),
        (916, 402, "line", False),
        (916, 534, "line", False),
        (969, 534, "line", False),
    ],
]

EXPECTED_glyph_graphemejoinercomb = [
    [
        (-357, 0, "line", False),
        (-357, 157, "line", False),
        (-303, 157, "line", False),
        (-303, 54, "line", False),
        (-201, 54, "line", False),
        (-201, 0, "line", False),
    ],
    [
        (-357, 279, "line", False),
        (-357, 436, "line", False),
        (-303, 436, "line", False),
        (-303, 279, "line", False),
    ],
    [
        (-357, 558, "line", False),
        (-357, 714, "line", False),
        (-201, 714, "line", False),
        (-201, 660, "line", False),
        (-303, 660, "line", False),
        (-303, 558, "line", False),
    ],
    [
        (-218, 330, "qcurve", True),
        (-245, 330, None, False),
        (-245, 357, "qcurve", True),
        (-245, 384, None, False),
        (-218, 384, "qcurve", True),
        (-191, 384, None, False),
        (-191, 357, "qcurve", True),
        (-191, 330, None, False),
    ],
    [
        (-200, 244, "qcurve", True),
        (-227, 244, None, False),
        (-227, 271, "qcurve", True),
        (-227, 298, None, False),
        (-200, 298, "qcurve", True),
        (-173, 298, None, False),
        (-173, 271, "qcurve", True),
        (-173, 244, None, False),
    ],
    [
        (-200, 416, "qcurve", True),
        (-227, 416, None, False),
        (-227, 443, "qcurve", True),
        (-227, 470, None, False),
        (-200, 470, "qcurve", True),
        (-173, 470, None, False),
        (-173, 443, "qcurve", True),
        (-173, 416, None, False),
    ],
    [
        (-157, 174, "qcurve", True),
        (-184, 174, None, False),
        (-184, 201, "qcurve", True),
        (-184, 228, None, False),
        (-157, 228, "qcurve", True),
        (-130, 228, None, False),
        (-130, 201, "qcurve", True),
        (-130, 174, None, False),
    ],
    [
        (-157, 486, "qcurve", True),
        (-184, 486, None, False),
        (-184, 513, "qcurve", True),
        (-184, 540, None, False),
        (-157, 540, "qcurve", True),
        (-130, 540, None, False),
        (-130, 513, "qcurve", True),
        (-130, 486, None, False),
    ],
    [
        (-86, 128, "qcurve", True),
        (-113, 128, None, False),
        (-113, 155, "qcurve", True),
        (-113, 182, None, False),
        (-86, 182, "qcurve", True),
        (-59, 182, None, False),
        (-59, 155, "qcurve", True),
        (-59, 128, None, False),
    ],
    [
        (-86, 532, "qcurve", True),
        (-113, 532, None, False),
        (-113, 559, "qcurve", True),
        (-113, 586, None, False),
        (-86, 586, "qcurve", True),
        (-59, 586, None, False),
        (-59, 559, "qcurve", True),
        (-59, 532, None, False),
    ],
    [
        (-79, 0, "line", False),
        (-79, 54, "line", False),
        (79, 54, "line", False),
        (79, 0, "line", False),
    ],
    [
        (-79, 660, "line", False),
        (-79, 714, "line", False),
        (79, 714, "line", False),
        (79, 660, "line", False),
    ],
    [
        (0, 112, "qcurve", True),
        (-27, 112, None, False),
        (-27, 139, "qcurve", True),
        (-27, 166, None, False),
        (0, 166, "qcurve", True),
        (27, 166, None, False),
        (27, 139, "qcurve", True),
        (27, 112, None, False),
    ],
    [
        (0, 548, "qcurve", True),
        (-27, 548, None, False),
        (-27, 575, "qcurve", True),
        (-27, 602, None, False),
        (0, 602, "qcurve", True),
        (27, 602, None, False),
        (27, 575, "qcurve", True),
        (27, 548, None, False),
    ],
    [
        (86, 128, "qcurve", True),
        (59, 128, None, False),
        (59, 155, "qcurve", True),
        (59, 182, None, False),
        (86, 182, "qcurve", True),
        (113, 182, None, False),
        (113, 155, "qcurve", True),
        (113, 128, None, False),
    ],
    [
        (86, 532, "qcurve", True),
        (59, 532, None, False),
        (59, 559, "qcurve", True),
        (59, 586, None, False),
        (86, 586, "qcurve", True),
        (113, 586, None, False),
        (113, 559, "qcurve", True),
        (113, 532, None, False),
    ],
    [
        (157, 174, "qcurve", True),
        (130, 174, None, False),
        (130, 201, "qcurve", True),
        (130, 228, None, False),
        (157, 228, "qcurve", True),
        (184, 228, None, False),
        (184, 201, "qcurve", True),
        (184, 174, None, False),
    ],
    [
        (157, 486, "qcurve", True),
        (130, 486, None, False),
        (130, 513, "qcurve", True),
        (130, 540, None, False),
        (157, 540, "qcurve", True),
        (184, 540, None, False),
        (184, 513, "qcurve", True),
        (184, 486, None, False),
    ],
    [
        (204, 244, "qcurve", True),
        (177, 244, None, False),
        (177, 271, "qcurve", True),
        (177, 298, None, False),
        (204, 298, "qcurve", True),
        (231, 298, None, False),
        (231, 271, "qcurve", True),
        (231, 244, None, False),
    ],
    [
        (204, 416, "qcurve", True),
        (177, 416, None, False),
        (177, 443, "qcurve", True),
        (177, 470, None, False),
        (204, 470, "qcurve", True),
        (231, 470, None, False),
        (231, 443, "qcurve", True),
        (231, 416, None, False),
    ],
    [
        (223, 330, "qcurve", True),
        (196, 330, None, False),
        (196, 357, "qcurve", True),
        (196, 384, None, False),
        (223, 384, "qcurve", True),
        (250, 384, None, False),
        (250, 357, "qcurve", True),
        (250, 330, None, False),
    ],
    [
        (201, 0, "line", False),
        (201, 54, "line", False),
        (304, 54, "line", False),
        (304, 157, "line", False),
        (357, 157, "line", False),
        (357, 0, "line", False),
    ],
    [
        (304, 558, "line", False),
        (304, 660, "line", False),
        (201, 660, "line", False),
        (201, 714, "line", False),
        (357, 714, "line", False),
        (357, 558, "line", False),
    ],
    [
        (304, 279, "line", False),
        (304, 436, "line", False),
        (357, 436, "line", False),
        (357, 279, "line", False),
    ],
]
