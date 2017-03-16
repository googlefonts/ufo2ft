from __future__ import print_function, division, absolute_import, unicode_literals

import unittest
from defcon import Font

from ufo2ft.markFeatureWriter import MarkFeatureWriter


class PrebuiltMarkFeatureWriter(MarkFeatureWriter):

    def setupAnchorPairs(self):
        self.anchorList = (('bottom', '_bottom'),)
        self.mkmkAnchorList = ()
        self.ligaAnchorList = ((('top_1', 'top_2'), '_top'),)


class MarkFeatureWriterTest(unittest.TestCase):
    def test_add_classes(self):
        ufo = Font()
        glyph = ufo.newGlyph('grave')
        glyph.appendAnchor(glyph.anchorClass(
            anchorDict={'name': '_top', 'x': 100, 'y': 200}))
        glyph = ufo.newGlyph('cedilla')
        glyph.appendAnchor(glyph.anchorClass(
            anchorDict={'name': '_bottom', 'x': 100, 'y': 0}))
        lines = []
        writer = PrebuiltMarkFeatureWriter(ufo)
        writer._addClasses(lines, doMark=True, doMkmk=True)
        self.assertEqual(
            '\n'.join(lines).strip(),
            'markClass cedilla <anchor 100 0> @MC_bottom;\n\n'
            'markClass grave <anchor 100 200> @MC_top;')


if __name__ == '__main__':
    unittest.main()
