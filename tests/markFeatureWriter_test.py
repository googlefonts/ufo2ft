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

    def test_only_one_lookup_for_mkmk(self):
        # We want only one lookup with several subtables for mkmk to fix
        # thai mark positioning issues in InDesign.
        ufo = Font()
        mark = ufo.newGlyph('mark')
        mark.appendAnchor({'name': '_topB', 'x': 0, 'y': 100})
        mark.appendAnchor({'name': 'topA', 'x': 0, 'y': 200})
        mark.appendAnchor({'name': 'topB', 'x': 0, 'y': 250})
        otherMark = ufo.newGlyph('otherMark')
        otherMark.appendAnchor({'name': '_topA', 'x': 0, 'y': 100})
        otherMark.appendAnchor({'name': 'topA', 'x': 0, 'y': 200})
        otherMark.appendAnchor({'name': 'topB', 'x': 0, 'y': 250})

        writer = MarkFeatureWriter()
        fea = writer.write(ufo)

        self.assertNotIn("feature mark", fea)
        self.assertIn("feature mkmk", fea)

        self.assertEqual(1, fea.count("lookup "))


if __name__ == '__main__':
    unittest.main()
