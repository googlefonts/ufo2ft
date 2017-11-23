from __future__ import print_function, division, absolute_import, unicode_literals

from textwrap import dedent

import unittest
from defcon import Font

from ufo2ft.featureCompiler import FeatureCompiler
from ufo2ft.featureWriters import KernFeatureWriter

from fontTools.misc.py23 import SimpleNamespace


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

    def test_ignoreMarks(self):
        font = Font()
        for name in ("one", "four", "six"):
            font.newGlyph(name)
        font.kerning.update({
            ('four', 'six'): -55.0,
            ('one', 'six'): -30.0,
        })
        # default is ignoreMarks=True
        writer = KernFeatureWriter()
        kern = writer.write(font)

        assert kern == dedent("""
            lookup kern_ltr {
                lookupflag IgnoreMarks;
                pos four six -55;
                pos one six -30;
            } kern_ltr;

            feature kern {
                lookup kern_ltr;
            } kern;""")

        writer = KernFeatureWriter(ignoreMarks=False)
        kern = writer.write(font)

        assert kern == dedent("""
            lookup kern_ltr {
                pos four six -55;
                pos one six -30;
            } kern_ltr;

            feature kern {
                lookup kern_ltr;
            } kern;""")

    def test_mode(self):

        class MockTTFont:
            def getReverseGlyphMap(self):
                return {"one": 0, "four": 1, "six": 2, "seven": 3}

        outline = MockTTFont()

        ufo = Font()
        for name in ("one", "four", "six", "seven"):
            ufo.newGlyph(name)
        existing = dedent("""
            feature kern {
                pos one four' -50 six;
            } kern;
            """)
        ufo.features.text = existing
        ufo.kerning.update({
            ('seven', 'six'): 25.0,
        })

        writer = KernFeatureWriter()  # default mode="skip"
        compiler = FeatureCompiler(ufo, outline, featureWriters=[writer])
        compiler.setupFile_features()

        assert compiler.features == existing

        writer = KernFeatureWriter(mode="append")
        compiler = FeatureCompiler(ufo, outline, featureWriters=[writer])
        compiler.setupFile_features()

        assert compiler.features == existing + dedent("""


            lookup kern_ltr {
                lookupflag IgnoreMarks;
                pos seven six 25;
            } kern_ltr;

            feature kern {
                lookup kern_ltr;
            } kern;""")


if __name__ == "__main__":
    import sys
    sys.exit(unittest.main())
