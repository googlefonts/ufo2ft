import unittest
import sys
import logging

import defcon
from ufo2ft.customFilter import TransformationsFilter, BaseFilter

logger = logging.getLogger(__name__)

class CustomFilterTest(unittest.TestCase):

    def setUp(self):
        self.inputData = {
            'name': 'Transformations',
            'args': [],
            'kwargs': {
                'LSB': 23,
                'RSB': -22,
                'SlantCorrection': True,
                'OffsetX': 10,
                'OffsetY': 5,
                'Origin': 0,
            },
            'exclude': ['uni0334', 'uni0335', 'uni0336'],
        }
        self.filter = TransformationsFilter(self.inputData['args'], self.inputData['kwargs'])
        self.chainedFilters = BaseFilter()
        self.chainedFilters.add(TransformationsFilter(self.inputData['args'], self.inputData['kwargs']))
        self.chainedFilters.add(TransformationsFilter(self.inputData['args'], self.inputData['kwargs']))

    def test_TransformationsFilter(self):
        inputGlyph = defcon.Glyph()
        pen = inputGlyph.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((1,1))
        pen.curveTo((1,2))
        pen.endPath()

        expectedGlyph = defcon.Glyph()
        pen = expectedGlyph.getPen()
        pen.moveTo((10, 5))
        pen.lineTo((11,6))
        pen.curveTo((11,7))
        pen.endPath()

        result = self.filter(inputGlyph)

        self.assertTrue(glyphShapeEqual(result, expectedGlyph))

    def test_chained_filters(self):
        inputGlyph = defcon.Glyph()
        pen = inputGlyph.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((1,1))
        pen.curveTo((1,2))
        pen.endPath()

        expectedGlyph = defcon.Glyph()
        pen = expectedGlyph.getPen()
        pen.moveTo((20, 10))
        pen.lineTo((21,11))
        pen.curveTo((21,12))
        pen.endPath()

        result = self.chainedFilters(inputGlyph)

        self.assertTrue(glyphShapeEqual(result, expectedGlyph))        

    # FIXME? add more test cases. Error inputdata, empty inputdata, multiple
    # different filters, etc.

def glyphShapeEqual(a, b):
    '''Compare two glyphs. The glyphs can not contain component.'''
    if len(a) != len(b):
        return False

    if a.components or b.components:
        logger.error('Can not compare composite glyphs.')
        return False
    for i in range(0, len(a)):
        # For each contour a[i]
        if len(a[i]) != len(b[i]):
            return False
        for j in range(0, len(a[i])):
        # For each point a[i][j]
            p1 = a[i][j]
            p2 = b[i][j]
            if (p1.x, p1.y) != (p2.x, p2.y) or p1.segmentType != p2.segmentType or p1.smooth != p2.smooth:
                return False
    return True


if __name__ == "__main__":
    sys.exit(unittest.main())
