from __future__ import annotations

from typing import TYPE_CHECKING

from fontTools.pens.recordingPen import RecordingPointPen

from ufo2ft.constants import EXPLICIT_CLOSING_LINE_KEY
from ufo2ft.filters import BaseIFilter

if TYPE_CHECKING:
    from ufoLib2.objects import Glyph


class ExplicitClosingLineIFilter(BaseIFilter):
    """Mark CFF glyphs that need compatible explicit closing lines."""

    _pre = True

    def filter(self, glyphName: str, glyphs: list[Glyph]) -> bool:
        if len(glyphs) < 2:
            return False

        needs_explicit_closing = _needs_explicit_closing_lines(glyphs)
        modified = False
        for glyph in glyphs:
            if needs_explicit_closing:
                if glyph.lib.get(EXPLICIT_CLOSING_LINE_KEY) is not True:
                    glyph.lib[EXPLICIT_CLOSING_LINE_KEY] = True
                    modified = True
            elif glyph.lib.pop(EXPLICIT_CLOSING_LINE_KEY, None) is not None:
                modified = True
        return modified


def _needs_explicit_closing_lines(glyphs) -> bool:
    contours = [_get_contours(glyph) for glyph in glyphs]
    if not contours:
        return False

    num_contours = len(contours[0])
    if not num_contours or any(
        len(glyph_contours) != num_contours for glyph_contours in contours
    ):
        return False

    for contour_index in range(num_contours):
        contour_group = [glyph_contours[contour_index] for glyph_contours in contours]
        point_types = [
            tuple(point_type for _, point_type in contour) for contour in contour_group
        ]
        if any(types != point_types[0] for types in point_types):
            continue

        explicit_closing = [
            _has_explicit_closing_line(contour) for contour in contour_group
        ]
        if any(explicit_closing) and not all(explicit_closing):
            return True

    return False


def _get_contours(glyph):
    pen = RecordingPointPen()
    glyph.drawPoints(pen)

    contours = []
    current_contour = None
    for operator, args, _kwargs in pen.value:
        if operator == "beginPath":
            current_contour = []
        elif operator == "addPoint":
            if current_contour is None:
                continue
            pt, segment_type = args[:2]
            current_contour.append((pt, segment_type))
        elif operator == "endPath":
            if current_contour is not None:
                contours.append(current_contour)
                current_contour = None

    return contours


def _first_oncurve_index(contour):
    for i, (_, segment_type) in enumerate(contour):
        if segment_type is not None:
            return i
    return None


def _has_explicit_closing_line(contour) -> bool:
    if not contour or contour[0][1] == "move":
        return False

    first_oncurve = _first_oncurve_index(contour)
    if first_oncurve is None:
        return False

    first_point, first_type = contour[first_oncurve]
    if first_type != "line":
        return False

    previous_point, _ = contour[first_oncurve - 1]
    return first_point == previous_point
