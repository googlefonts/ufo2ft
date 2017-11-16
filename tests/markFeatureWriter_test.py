from __future__ import print_function, division, absolute_import, unicode_literals

import unittest
from defcon import Font

from ufo2ft.featureWriters import MarkFeatureWriter


class PrebuiltMarkFeatureWriter(MarkFeatureWriter):

    def setupAnchorPairs(self):
        self.context.anchorList = (('bottom', '_bottom'),)
        self.context.mkmkAnchorList = ()
        self.context.ligaAnchorList = ((('top_1', 'top_2'), '_top'),)


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
        writer = PrebuiltMarkFeatureWriter()
        writer.set_context(ufo)
        writer._addClasses(lines, doMark=True, doMkmk=True)
        self.assertEqual(
            '\n'.join(lines).strip(),
            'markClass cedilla <anchor 100 0> @MC_bottom;\n\n'
            'markClass grave <anchor 100 200> @MC_top;')

    def test_skip_empty_feature(self):
        ufo = Font()
        glyph = ufo.newGlyph('a')
        glyph.appendAnchor(glyph.anchorClass(
            anchorDict={'name': 'top', 'x': 100, 'y': 200}))
        glyph = ufo.newGlyph('acutecomb')
        glyph.appendAnchor(glyph.anchorClass(
            anchorDict={'name': '_top', 'x': 100, 'y': 200}))

        writer = MarkFeatureWriter()
        fea = writer.write(ufo)

        self.assertIn("feature mark", fea)
        self.assertNotIn("feature mkmk", fea)


if __name__ == '__main__':
    unittest.main()
