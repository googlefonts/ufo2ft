from fontTools.pens.pointPen import PointToSegmentPen
from fontTools.pens.recordingPen import RecordingPen, RecordingPointPen

from ufo2ft.constants import EXPLICIT_CLOSING_LINE_KEY
from ufo2ft.filters.explicitClosingLine import ExplicitClosingLineIFilter


def _make_font(FontClass, glyph_name, contours):
    font = FontClass()
    glyph = font.newGlyph(glyph_name)
    glyph.width = 500
    pen = glyph.getPointPen()
    for contour in contours:
        pen.beginPath()
        for point in contour:
            if isinstance(point[0], tuple):
                point, segment_type = point
            else:
                segment_type = "line"
            pen.addPoint(point, segment_type)
        pen.endPath()
    return font


def _line_count(glyph, outputImpliedClosingLine=False):
    return _operator_count(glyph, "lineTo", outputImpliedClosingLine)


def _curve_count(glyph, outputImpliedClosingLine=False):
    return _operator_count(glyph, "curveTo", outputImpliedClosingLine)


def _operator_count(glyph, operator_name, outputImpliedClosingLine=False):
    pen = RecordingPen()
    glyph.drawPoints(
        PointToSegmentPen(pen, outputImpliedClosingLine=outputImpliedClosingLine)
    )
    return sum(operator == operator_name for operator, _ in pen.value)


def _point_count(glyph):
    pen = RecordingPointPen()
    glyph.drawPoints(pen)
    return sum(operator == "addPoint" for operator, _, _ in pen.value)


def test_mismatched_explicit_closing_line_gets_duplicate_point(FontClass):
    font1 = _make_font(
        FontClass,
        "o",
        [
            [
                (256, 320),
                (288, 288),
                (288, 160),
                (192, 128),
                (224, 288),
                (256, 320),
            ]
        ],
    )
    font2 = _make_font(
        FontClass,
        "o",
        [
            [
                (512, 320),
                (544, 288),
                (544, 160),
                (320, 128),
                (352, 288),
                (384, 320),
            ]
        ],
    )

    modified = ExplicitClosingLineIFilter()([font1, font2])

    assert modified == {"o"}
    assert font1["o"].lib[EXPLICIT_CLOSING_LINE_KEY] is True
    assert font2["o"].lib[EXPLICIT_CLOSING_LINE_KEY] is True
    assert _point_count(font1["o"]) == _point_count(font2["o"]) == 6
    assert _line_count(font1["o"]) != _line_count(font2["o"])
    assert (
        _line_count(font1["o"], outputImpliedClosingLine=True)
        == _line_count(font2["o"], outputImpliedClosingLine=True)
        == 6
    )


def test_mismatched_explicit_closing_line_with_curves_gets_marker(FontClass):
    font1 = _make_font(
        FontClass,
        "o",
        [
            [
                ((256, 320), "line"),
                ((288, 288), None),
                ((288, 160), None),
                ((192, 128), "curve"),
                ((224, 288), "line"),
                ((256, 320), "line"),
            ]
        ],
    )
    font2 = _make_font(
        FontClass,
        "o",
        [
            [
                ((512, 320), "line"),
                ((544, 288), None),
                ((544, 160), None),
                ((320, 128), "curve"),
                ((352, 288), "line"),
                ((384, 320), "line"),
            ]
        ],
    )

    modified = ExplicitClosingLineIFilter()([font1, font2])

    assert modified == {"o"}
    assert font1["o"].lib[EXPLICIT_CLOSING_LINE_KEY] is True
    assert font2["o"].lib[EXPLICIT_CLOSING_LINE_KEY] is True
    assert _point_count(font1["o"]) == _point_count(font2["o"]) == 6
    assert _line_count(font1["o"]) != _line_count(font2["o"])
    assert _curve_count(font1["o"]) == _curve_count(font2["o"]) == 1
    assert (
        _line_count(font1["o"], outputImpliedClosingLine=True)
        == _line_count(font2["o"], outputImpliedClosingLine=True)
        == 3
    )
    assert (
        _curve_count(font1["o"], outputImpliedClosingLine=True)
        == _curve_count(font2["o"], outputImpliedClosingLine=True)
        == 1
    )


def test_matching_implied_closing_lines_are_unchanged(FontClass):
    font1 = _make_font(FontClass, "a", [[(0, 0), (100, 0), (100, 100)]])
    font2 = _make_font(FontClass, "a", [[(0, 0), (200, 0), (200, 100)]])

    modified = ExplicitClosingLineIFilter()([font1, font2])

    assert modified == set()
    assert EXPLICIT_CLOSING_LINE_KEY not in font1["a"].lib
    assert EXPLICIT_CLOSING_LINE_KEY not in font2["a"].lib
    assert _point_count(font1["a"]) == 3
    assert _point_count(font2["a"]) == 3


def test_matching_explicit_closing_lines_are_unchanged(FontClass):
    font1 = _make_font(FontClass, "a", [[(0, 0), (100, 0), (0, 0)]])
    font2 = _make_font(FontClass, "a", [[(10, 0), (200, 0), (10, 0)]])

    modified = ExplicitClosingLineIFilter()([font1, font2])

    assert modified == set()
    assert EXPLICIT_CLOSING_LINE_KEY not in font1["a"].lib
    assert EXPLICIT_CLOSING_LINE_KEY not in font2["a"].lib
    assert _point_count(font1["a"]) == 3
    assert _point_count(font2["a"]) == 3
