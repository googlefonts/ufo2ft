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
        ufo.newGlyph('grave').appendAnchor(
            {'name': '_top', 'x': 100, 'y': 200})
        ufo.newGlyph('cedilla').appendAnchor(
            {'name': '_bottom', 'x': 100, 'y': 0})
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
        ufo.newGlyph('a').appendAnchor(
            {'name': 'top', 'x': 100, 'y': 200})
        ufo.newGlyph('acutecomb').appendAnchor(
            {'name': '_top', 'x': 100, 'y': 200})

        writer = MarkFeatureWriter()
        fea = writer.write(ufo)

        self.assertIn("feature mark", fea)
        self.assertNotIn("feature mkmk", fea)

    def test_only_write_one(self):
        ufo = Font()
        ufo.newGlyph('a').appendAnchor({'name': 'top', 'x': 100, 'y': 200})
        ufo.newGlyph('acutecomb').appendAnchor(
            {'name': '_top', 'x': 100, 'y': 200})
        glyph = ufo.newGlyph('tildecomb')
        glyph.appendAnchor({'name': '_top', 'x': 100, 'y': 200})
        glyph.appendAnchor({'name': 'top', 'x': 100, 'y': 300})

        writer = MarkFeatureWriter()  # by default both mark + mkmk are built
        fea = writer.write(ufo)

        self.assertIn("feature mark", fea)
        self.assertIn("feature mkmk", fea)

        writer = MarkFeatureWriter(features=["mkmk"])  # only builds "mkmk"
        fea = writer.write(ufo)

        self.assertNotIn("feature mark", fea)
        self.assertIn("feature mkmk", fea)


if __name__ == '__main__':
    unittest.main()
