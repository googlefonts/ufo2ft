from __future__ import print_function, division, absolute_import, unicode_literals

from textwrap import dedent

from defcon import Font

from ufo2ft.featureCompiler import FeatureCompiler
from ufo2ft.featureWriters import KernFeatureWriter

from fontTools.misc.py23 import SimpleNamespace

import pytest


class KernFeatureWriterTest(object):

    def test__collectFeaClasses(self):
        text = '@MMK_L_v = [v w y];'
        expected = {'@MMK_L_v': ['v', 'w', 'y']}

        ufo = Font()
        ufo.features.text = text
        writer = KernFeatureWriter()
        writer.set_context(ufo)
        writer._collectFeaClasses()
        assert writer.context.leftFeaClasses == expected

    def test__cleanupMissingGlyphs(self):
        groups = {
            "public.kern1.A": ["A", "Aacute", "Abreve", "Acircumflex"],
            "public.kern2.B": ["B", "D", "E", "F"],
            "public.kern1.C": ["foobar"],
        }
        kerning = {
            ("public.kern1.A", "public.kern2.B"): 10,
            ("public.kern1.A", "baz"): -25,
            ("baz", "public.kern2.B"): -20,
            ("public.kern1.C", "public.kern2.B"): 20,
        }
        ufo = Font()
        exclude = {"Abreve", "D", "foobar"}
        for glyphs in groups.values():
            for glyph in glyphs:
                if glyph in exclude:
                    continue
                ufo.newGlyph(glyph)
        ufo.groups.update(groups)
        ufo.kerning.update(kerning)

        writer = KernFeatureWriter()
        writer.set_context(ufo)
        assert writer.context.groups == groups
        assert writer.context.kerning == kerning

        writer._cleanupMissingGlyphs()
        assert writer.context.groups == {
            "public.kern1.A": ["A", "Aacute", "Acircumflex"],
            "public.kern2.B": ["B", "E", "F"]}
        assert writer.context.kerning == {
            ("public.kern1.A", "public.kern2.B"): 10}

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

        writer = KernFeatureWriter(mode="prepend")
        compiler = FeatureCompiler(ufo, outline, featureWriters=[writer])
        compiler.setupFile_features()

        assert compiler.features == dedent("""
            lookup kern_ltr {
                lookupflag IgnoreMarks;
                pos seven six 25;
            } kern_ltr;

            feature kern {
                lookup kern_ltr;
            } kern;

            """) + existing

    # https://github.com/googlei18n/ufo2ft/issues/198
    @pytest.mark.xfail
    def test_arabic_numerals(self):
        ufo = Font()
        for name, code in [("four-ar", 0x664), ("seven-ar", 0x667)]:
            glyph = ufo.newGlyph(name)
            glyph.unicode = code
        ufo.kerning.update({
            ('four-ar', 'seven-ar'): -30,
        })
        ufo.features.text = dedent("""
            languagesystem DFLT dflt;
            languagesystem arab dflt;
        """)

        writer = KernFeatureWriter()
        kern = writer.write(ufo)

        assert kern == dedent("""
            lookup kern_ltr {
                lookupflag IgnoreMarks;
                pos four-ar seven-ar -30;
            } kern_ltr;

            feature kern {
                lookup kern_ltr;
            } kern;""")

    def test_set_context(self):
        font = Font()
        font.features.text = dedent("""
            languagesystem DFLT dflt;
            languagesystem latn dflt;
            languagesystem latn TRK;
            languagesystem arab dflt;
            languagesystem arab URD;
        """)

        writer = KernFeatureWriter()
        writer.set_context(font)

        assert list(writer.context.ltrScripts.items()) == [
            ("latn", ["dflt", "TRK"])]
        assert list(writer.context.rtlScripts.items()) == [
            ("arab", ["dflt", "URD"])]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main(sys.argv))
