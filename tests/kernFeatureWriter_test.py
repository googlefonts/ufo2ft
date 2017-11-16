from __future__ import print_function, division, absolute_import, unicode_literals

import unittest
from defcon import Font

from ufo2ft.featureWriters import KernFeatureWriter


class KernFeatureWriterTest(unittest.TestCase):
    def test_collect_fea_classes(self):
        text = '@MMK_L_v = [v w y];'
        expected = {'@MMK_L_v': ['v', 'w', 'y']}

        ufo = Font()
        ufo.features.text = text
        writer = KernFeatureWriter()
        writer.set_context(ufo)
        writer._collectFeaClasses()
        self.assertEquals(writer.context.leftFeaClasses, expected)

    def test__cleanupMissingGlyphs(self):
        groups = {
            "public.kern1.A": ["A", "Aacute", "Abreve", "Acircumflex"],
            "public.kern2.B": ["B", "D", "E", "F"],
        }
        ufo = Font()
        for glyphs in groups.values():
            for glyph in glyphs:
                ufo.newGlyph(glyph)
        ufo.groups.update(groups)
        del ufo["Abreve"]
        del ufo["D"]

        writer = KernFeatureWriter()
        writer.set_context(ufo)
        self.assertEquals(writer.context.groups, groups)

        writer._cleanupMissingGlyphs()
        self.assertEquals(writer.context.groups, {
            "public.kern1.A": ["A", "Aacute", "Acircumflex"],
            "public.kern2.B": ["B", "E", "F"]})


if __name__ == "__main__":
    import sys
    sys.exit(unittest.main())
