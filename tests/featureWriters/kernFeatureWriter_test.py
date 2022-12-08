import logging
from textwrap import dedent

import pytest
from fontTools import unicodedata

from ufo2ft.constants import UNICODE_SCRIPT_ALIASES
from ufo2ft.errors import InvalidFeaturesData
from ufo2ft.featureCompiler import parseLayoutFeatures
from ufo2ft.featureWriters import KernFeatureWriter, ast
from ufo2ft.util import DFLT_SCRIPTS, unicodeScriptExtensions

from . import FeatureWriterTest


def makeUFO(cls, glyphMap, groups=None, kerning=None, features=None):
    ufo = cls()
    for name, uni in glyphMap.items():
        glyph = ufo.newGlyph(name)
        if uni is not None:
            glyph.unicode = uni
    if groups is not None:
        ufo.groups.update(groups)
    if kerning is not None:
        ufo.kerning.update(kerning)
    if features is not None:
        ufo.features.text = features
    return ufo


def getClassDefs(feaFile):
    return [s for s in feaFile.statements if isinstance(s, ast.GlyphClassDefinition)]


def getGlyphs(classDef):
    return [str(g) for g in classDef.glyphs.glyphSet()]


def getLookups(feaFile):
    return [s for s in feaFile.statements if isinstance(s, ast.LookupBlock)]


def getPairPosRules(lookup):
    return [s for s in lookup.statements if isinstance(s, ast.PairPosStatement)]


class KernFeatureWriterTest(FeatureWriterTest):

    FeatureWriter = KernFeatureWriter

    def test_cleanup_missing_glyphs(self, FontClass):
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
        ufo = FontClass()
        exclude = {"Abreve", "D", "foobar"}
        for glyphs in groups.values():
            for glyph in glyphs:
                if glyph in exclude:
                    continue
                ufo.newGlyph(glyph)
        ufo.groups.update(groups)
        ufo.kerning.update(kerning)

        writer = KernFeatureWriter()
        feaFile = parseLayoutFeatures(ufo)
        writer.write(ufo, feaFile)

        classDefs = getClassDefs(feaFile)
        assert len(classDefs) == 2
        assert classDefs[0].name == "kern1.Default.A"
        assert classDefs[1].name == "kern2.Default.B"
        assert getGlyphs(classDefs[0]) == ["A", "Aacute", "Acircumflex"]
        assert getGlyphs(classDefs[1]) == ["B", "E", "F"]

        lookups = getLookups(feaFile)
        assert len(lookups) == 1
        kern_lookup = lookups[0]
        # We have no codepoints defined for these, so they're considered common
        assert kern_lookup.name == "kern_Default"
        rules = getPairPosRules(kern_lookup)
        assert len(rules) == 1
        assert str(rules[0]) == "pos @kern1.Default.A @kern2.Default.B 10;"

    def test_ignoreMarks(self, FontClass):
        font = FontClass()
        for name in ("one", "four", "six"):
            font.newGlyph(name)
        font.kerning.update({("four", "six"): -55.0, ("one", "six"): -30.0})
        # default is ignoreMarks=True
        writer = KernFeatureWriter()
        feaFile = ast.FeatureFile()
        assert writer.write(font, feaFile)

        assert str(feaFile) == dedent(
            """\
            lookup kern_Default {
                lookupflag IgnoreMarks;
                pos four six -55;
                pos one six -30;
            } kern_Default;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Default;
            } kern;
            """
        )

        writer = KernFeatureWriter(ignoreMarks=False)
        feaFile = ast.FeatureFile()
        assert writer.write(font, feaFile)

        assert str(feaFile) == dedent(
            """\
            lookup kern_Default {
                pos four six -55;
                pos one six -30;
            } kern_Default;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Default;
            } kern;
            """
        )

    def test_mark_to_base_kern(self, FontClass):
        font = FontClass()
        for name in ("A", "B", "C"):
            font.newGlyph(name).unicode = ord(name)
        font.newGlyph("acutecomb").unicode = 0x0301
        font.kerning.update({("A", "acutecomb"): -55.0, ("B", "C"): -30.0})

        font.features.text = dedent(
            """\
            @Bases = [A B C];
            @Marks = [acutecomb];
            table GDEF {
                GlyphClassDef @Bases, [], @Marks, ;
            } GDEF;
            """
        )

        # default is ignoreMarks=True
        feaFile = self.writeFeatures(font)
        assert str(feaFile) == dedent(
            """
            lookup kern_Latn {
                lookupflag IgnoreMarks;
                pos B C -30;
            } kern_Latn;

            lookup kern_Latn_marks {
                pos A acutecomb -55;
            } kern_Latn_marks;

            feature kern {
                script latn;
                language dflt;
                lookup kern_Latn;
                lookup kern_Latn_marks;
            } kern;
            """
        )

        feaFile = self.writeFeatures(font, ignoreMarks=False)
        assert str(feaFile) == dedent(
            """
            lookup kern_Latn {
                pos A acutecomb -55;
                pos B C -30;
            } kern_Latn;

            feature kern {
                script latn;
                language dflt;
                lookup kern_Latn;
            } kern;
            """
        )

    def test_mark_to_base_only(self, FontClass):
        font = FontClass()
        for name in ("A", "B", "C"):
            font.newGlyph(name)
        font.newGlyph("acutecomb").unicode = 0x0301
        font.kerning.update({("A", "acutecomb"): -55.0})

        font.features.text = dedent(
            """\
            @Bases = [A B C];
            @Marks = [acutecomb];
            table GDEF {
                GlyphClassDef @Bases, [], @Marks, ;
            } GDEF;
            """
        )

        # default is ignoreMarks=True
        feaFile = self.writeFeatures(font)
        assert str(feaFile) == dedent(
            """
            lookup kern_Default_marks {
                pos A acutecomb -55;
            } kern_Default_marks;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Default_marks;
            } kern;
            """
        )

    def test_mode(self, FontClass):
        ufo = FontClass()
        for name in ("one", "four", "six", "seven"):
            ufo.newGlyph(name)
        existing = dedent(
            """\
            feature kern {
                pos one four' -50 six;
            } kern;
            """
        )
        ufo.features.text = existing
        ufo.kerning.update({("seven", "six"): 25.0})

        writer = KernFeatureWriter()  # default mode="skip"
        feaFile = parseLayoutFeatures(ufo)
        assert not writer.write(ufo, feaFile)

        assert str(feaFile) == existing

        # pass optional "append" mode
        writer = KernFeatureWriter(mode="append")
        feaFile = parseLayoutFeatures(ufo)
        assert writer.write(ufo, feaFile)

        expected = existing + dedent(
            """

            lookup kern_Default {
                lookupflag IgnoreMarks;
                pos seven six 25;
            } kern_Default;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Default;
            } kern;
            """
        )
        assert str(feaFile) == expected

        # pass "skip" mode explicitly
        writer = KernFeatureWriter(mode="skip")
        feaFile = parseLayoutFeatures(ufo)
        assert not writer.write(ufo, feaFile)

        assert str(feaFile) == existing

    def test_insert_comment_before(self, FontClass):
        ufo = FontClass()
        for name in ("one", "four", "six", "seven"):
            ufo.newGlyph(name)
        existing = dedent(
            """\
            feature kern {
                #
                # Automatic Code
                #
                pos one four' -50 six;
            } kern;
            """
        )
        ufo.features.text = existing
        ufo.kerning.update({("seven", "six"): 25.0})

        writer = KernFeatureWriter()
        feaFile = parseLayoutFeatures(ufo)
        assert writer.write(ufo, feaFile)

        expected = dedent(
            """\
            lookup kern_Default {
                lookupflag IgnoreMarks;
                pos seven six 25;
            } kern_Default;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Default;
            } kern;

            feature kern {
                #
                #
                pos one four' -50 six;
            } kern;
            """
        )

        assert str(feaFile).strip() == expected.strip()

        # test append mode ignores insert marker
        generated = self.writeFeatures(ufo, mode="append")
        assert str(generated) == dedent(
            """
            lookup kern_Default {
                lookupflag IgnoreMarks;
                pos seven six 25;
            } kern_Default;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Default;
            } kern;
            """
        )

    def test_insert_comment_before_extended(self, FontClass):
        ufo = FontClass()
        for name in ("one", "four", "six", "seven"):
            ufo.newGlyph(name)
        existing = dedent(
            """\
            feature kern {
                #
                # Automatic Code End
                #
                pos one four' -50 six;
            } kern;
            """
        )
        ufo.features.text = existing
        ufo.kerning.update({("seven", "six"): 25.0})

        writer = KernFeatureWriter()
        feaFile = parseLayoutFeatures(ufo)
        assert writer.write(ufo, feaFile)

        expected = dedent(
            """\
            lookup kern_Default {
                lookupflag IgnoreMarks;
                pos seven six 25;
            } kern_Default;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Default;
            } kern;

            feature kern {
                #
                #
                pos one four' -50 six;
            } kern;
            """
        )

        assert str(feaFile).strip() == expected.strip()

    def test_insert_comment_after(self, FontClass):
        ufo = FontClass()
        for name in ("one", "four", "six", "seven"):
            ufo.newGlyph(name)
        existing = dedent(
            """\
            feature kern {
                pos one four' -50 six;
                #
                # Automatic Code
                #
            } kern;
            """
        )
        ufo.features.text = existing
        ufo.kerning.update({("seven", "six"): 25.0})

        writer = KernFeatureWriter()
        feaFile = parseLayoutFeatures(ufo)
        assert writer.write(ufo, feaFile)

        expected = dedent(
            """\
            feature kern {
                pos one four' -50 six;
                #
                #
            } kern;


            lookup kern_Default {
                lookupflag IgnoreMarks;
                pos seven six 25;
            } kern_Default;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Default;
            } kern;
            """
        )

        assert str(feaFile) == expected

        # test append mode ignores insert marker
        generated = self.writeFeatures(ufo, mode="append")
        assert str(generated) == dedent(
            """
            lookup kern_Default {
                lookupflag IgnoreMarks;
                pos seven six 25;
            } kern_Default;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Default;
            } kern;
            """
        )

    def test_insert_comment_middle(self, FontClass):
        ufo = FontClass()
        for name in ("one", "four", "six", "seven"):
            ufo.newGlyph(name)
        existing = dedent(
            """\
            feature kern {
                pos one four' -50 six;
                #
                # Automatic Code
                #
                pos one six' -50 six;
            } kern;
            """
        )
        ufo.features.text = existing
        ufo.kerning.update({("seven", "six"): 25.0})

        writer = KernFeatureWriter()
        feaFile = parseLayoutFeatures(ufo)

        with pytest.raises(
            InvalidFeaturesData,
            match="Insert marker has rules before and after, feature kern "
            "cannot be inserted.",
        ):
            writer.write(ufo, feaFile)

        # test append mode ignores insert marker
        generated = self.writeFeatures(ufo, mode="append")
        assert str(generated) == dedent(
            """
            lookup kern_Default {
                lookupflag IgnoreMarks;
                pos seven six 25;
            } kern_Default;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Default;
            } kern;
            """
        )

    def test_arabic_numerals(self, FontClass):
        """Test that arabic numerals (with bidi type AN) are kerned LTR.

        See:

        * https://github.com/googlei18n/ufo2ft/issues/198
        * https://github.com/googlei18n/ufo2ft/pull/200

        Additionally, some Arabic numerals are used in more than one script. One
        approach is to look at other glyphs with distinct script associations
        and consider the font to be supporting those.
        """
        ufo = FontClass()
        for name, code in [("four-ar", 0x664), ("seven-ar", 0x667)]:
            glyph = ufo.newGlyph(name)
            glyph.unicode = code
        ufo.kerning.update({("four-ar", "seven-ar"): -30})

        generated = self.writeFeatures(ufo)

        assert (
            dedent(str(generated))
            == dedent(
                """
            lookup kern_Default {
                lookupflag IgnoreMarks;
                pos four-ar seven-ar -30;
            } kern_Default;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Default;
            } kern;
            """
            ).lstrip("\n")
        )

        ufo.newGlyph("alef-ar").unicode = 0x627
        generated = self.writeFeatures(ufo)

        assert dedent(str(generated)) == dedent(
            """\
            lookup kern_Arab {
                lookupflag IgnoreMarks;
                pos four-ar seven-ar -30;
            } kern_Arab;

            feature kern {
                script arab;
                language dflt;
                lookup kern_Arab;
            } kern;
            """
        )

        ufo.features.text = """
            languagesystem DFLT dflt;
            languagesystem Thaa dflt;
        """
        generated = self.writeFeatures(ufo)

        assert dedent(str(generated)) == dedent(
            """
            lookup kern_Arab {
                lookupflag IgnoreMarks;
                pos four-ar seven-ar -30;
            } kern_Arab;

            lookup kern_Thaa {
                lookupflag IgnoreMarks;
                pos four-ar seven-ar -30;
            } kern_Thaa;

            feature kern {
                script arab;
                language dflt;
                lookup kern_Arab;

                script thaa;
                language dflt;
                lookup kern_Thaa;
            } kern;
            """
        )

        del ufo["alef-ar"]
        generated = self.writeFeatures(ufo)

        assert dedent(str(generated)) == dedent(
            """
            lookup kern_Thaa {
                lookupflag IgnoreMarks;
                pos four-ar seven-ar -30;
            } kern_Thaa;

            feature kern {
                script thaa;
                language dflt;
                lookup kern_Thaa;
            } kern;
            """
        )

    def test_skip_zero_class_kerns(self, FontClass):
        glyphs = {
            "A": ord("A"),
            "B": ord("B"),
            "C": ord("C"),
            "D": ord("D"),
            "E": ord("E"),
            "F": ord("F"),
            "G": ord("G"),
            "H": ord("H"),
        }
        groups = {
            "public.kern1.foo": ["A", "B"],
            "public.kern2.bar": ["C", "D"],
            "public.kern1.baz": ["E", "F"],
            "public.kern2.nul": ["G", "H"],
        }
        kerning = {
            ("public.kern1.foo", "public.kern2.bar"): 10,
            ("public.kern1.baz", "public.kern2.bar"): -10,
            ("public.kern1.foo", "D"): 15,
            ("A", "public.kern2.bar"): 5,
            ("G", "H"): -5,
            # class-class zero-value pairs are skipped
            ("public.kern1.foo", "public.kern2.nul"): 0,
        }
        expectation = dedent(
            """\
            @kern1.Latn.baz = [E F];
            @kern1.Latn.foo = [A B];
            @kern2.Latn.bar = [C D];

            lookup kern_Latn {
                lookupflag IgnoreMarks;
                pos G H -5;
                enum pos A @kern2.Latn.bar 5;
                enum pos @kern1.Latn.foo D 15;
                pos @kern1.Latn.foo @kern2.Latn.bar 10;
                pos @kern1.Latn.baz @kern2.Latn.bar -10;
            } kern_Latn;

            feature kern {
                script latn;
                language dflt;
                lookup kern_Latn;
            } kern;
            """
        )

        ufo = makeUFO(FontClass, glyphs, groups, kerning)
        newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

        assert dedent(str(newFeatures)).lstrip("\n") == expectation

    def test_kern_uniqueness(self, FontClass):
        glyphs = {
            ".notdef": None,
            "questiondown": 0xBF,
            "y": 0x79,
        }
        groups = {
            "public.kern1.questiondown": ["questiondown"],
            "public.kern2.y": ["y"],
        }
        kerning = {
            ("public.kern1.questiondown", "public.kern2.y"): 15,
            ("public.kern1.questiondown", "y"): 35,
            ("questiondown", "public.kern2.y"): -35,
            ("questiondown", "y"): 35,
        }
        ufo = makeUFO(FontClass, glyphs, groups, kerning)

        newFeatures = self.writeFeatures(ufo)

        # The final kerning value for questiondown, y is 35 and all variants
        # must be present. Ensures the uniqueness filter doesn't filter things
        # out.
        assert dedent(str(newFeatures)) == dedent(
            """\
            @kern1.Latn.questiondown = [questiondown];
            @kern2.Latn.y = [y];

            lookup kern_Latn {
                lookupflag IgnoreMarks;
                pos questiondown y 35;
                enum pos questiondown @kern2.Latn.y -35;
                enum pos @kern1.Latn.questiondown y 35;
                pos @kern1.Latn.questiondown @kern2.Latn.y 15;
            } kern_Latn;

            feature kern {
                script latn;
                language dflt;
                lookup kern_Latn;
            } kern;
            """
        )

    def test_kern_LTR_and_RTL(self, FontClass):
        glyphs = {
            ".notdef": None,
            "four": 0x34,
            "seven": 0x37,
            "A": 0x41,
            "V": 0x56,
            "Aacute": 0xC1,
            "alef-ar": 0x627,
            "reh-ar": 0x631,
            "zain-ar": 0x632,
            "lam-ar": 0x644,
            "four-ar": 0x664,
            "seven-ar": 0x667,
            # # we also add glyphs without unicode codepoint, but linked to
            # # an encoded 'character' glyph by some GSUB rule
            "alef-ar.isol": None,
            "lam-ar.init": None,
            "reh-ar.fina": None,
        }
        groups = {
            "public.kern1.A": ["A", "Aacute"],
            "public.kern1.reh": ["reh-ar", "zain-ar", "reh-ar.fina"],
            "public.kern2.alef": ["alef-ar", "alef-ar.isol"],
        }
        kerning = {
            ("public.kern1.A", "V"): -40,
            ("seven", "four"): -25,
            ("reh-ar.fina", "lam-ar.init"): -80,
            ("public.kern1.reh", "public.kern2.alef"): -100,
            ("four-ar", "seven-ar"): -30,
        }
        features = dedent(
            """\
            languagesystem DFLT dflt;
            languagesystem latn dflt;
            languagesystem latn TRK;
            languagesystem arab dflt;
            languagesystem arab URD;

            feature init {
                script arab;
                sub lam-ar by lam-ar.init;
                language URD;
            } init;

            feature fina {
                script arab;
                sub reh-ar by reh-ar.fina;
                language URD;
            } fina;

            feature isol {
                script arab;
                sub alef-ar by alef-ar.isol;
            } isol;
            """
        )

        ufo = makeUFO(FontClass, glyphs, groups, kerning, features)

        newFeatures = self.writeFeatures(ufo, ignoreMarks=False)

        assert dedent(str(newFeatures)) == dedent(
            """\
            @kern1.Arab.reh = [reh-ar reh-ar.fina zain-ar];
            @kern1.Latn.A = [A Aacute];
            @kern2.Arab.alef = [alef-ar alef-ar.isol];

            lookup kern_Arab {
                pos four-ar seven-ar -30;
                pos reh-ar.fina lam-ar.init <-80 0 -80 0>;
                pos @kern1.Arab.reh @kern2.Arab.alef <-100 0 -100 0>;
            } kern_Arab;

            lookup kern_Latn {
                enum pos @kern1.Latn.A V -40;
            } kern_Latn;

            lookup kern_Default {
                pos seven four -25;
            } kern_Default;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Default;

                script arab;
                language dflt;
                lookup kern_Default;
                lookup kern_Arab;

                script latn;
                language dflt;
                lookup kern_Default;
                lookup kern_Latn;
            } kern;
            """
        )

    def test_kern_LTR_and_RTL_with_marks(self, FontClass):
        glyphs = {
            ".notdef": None,
            "four": 0x34,
            "seven": 0x37,
            "A": 0x41,
            "V": 0x56,
            "Aacute": 0xC1,
            "acutecomb": 0x301,
            "alef-ar": 0x627,
            "reh-ar": 0x631,
            "zain-ar": 0x632,
            "lam-ar": 0x644,
            "four-ar": 0x664,
            "seven-ar": 0x667,
            "fatha-ar": 0x64E,
            # we also add glyphs without unicode codepoint, but linked to
            # an encoded 'character' glyph by some GSUB rule
            "alef-ar.isol": None,
            "lam-ar.init": None,
            "reh-ar.fina": None,
        }
        groups = {
            "public.kern1.A": ["A", "Aacute"],
            "public.kern1.reh": ["reh-ar", "zain-ar", "reh-ar.fina"],
            "public.kern2.alef": ["alef-ar", "alef-ar.isol"],
        }
        kerning = {
            ("public.kern1.A", "V"): -40,
            ("seven", "four"): -25,
            ("reh-ar.fina", "lam-ar.init"): -80,
            ("public.kern1.reh", "public.kern2.alef"): -100,
            ("four-ar", "seven-ar"): -30,
            ("V", "acutecomb"): 70,
            ("reh-ar", "fatha-ar"): 80,
        }
        features = dedent(
            """\
            languagesystem DFLT dflt;
            languagesystem latn dflt;
            languagesystem latn TRK;
            languagesystem arab dflt;
            languagesystem arab URD;

            feature init {
                script arab;
                sub lam-ar by lam-ar.init;
                language URD;
            } init;

            feature fina {
                script arab;
                sub reh-ar by reh-ar.fina;
                language URD;
            } fina;

            feature isol {
                script arab;
                sub alef-ar by alef-ar.isol;
            } isol;

            @Bases = [A V Aacute alef-ar reh-ar zain-ar lam-ar
                      alef-ar.isol lam-ar.init reh-ar.fina];
            @Marks = [acutecomb fatha-ar];
            table GDEF {
                GlyphClassDef @Bases, [], @Marks, ;
            } GDEF;
            """
        )

        ufo = makeUFO(FontClass, glyphs, groups, kerning, features)

        newFeatures = self.writeFeatures(ufo)

        assert dedent(str(newFeatures)).lstrip("\n") == dedent(
            """\
            @kern1.Arab.reh = [reh-ar reh-ar.fina zain-ar];
            @kern1.Latn.A = [A Aacute];
            @kern2.Arab.alef = [alef-ar alef-ar.isol];

            lookup kern_Arab {
                lookupflag IgnoreMarks;
                pos four-ar seven-ar -30;
                pos reh-ar.fina lam-ar.init <-80 0 -80 0>;
                pos @kern1.Arab.reh @kern2.Arab.alef <-100 0 -100 0>;
            } kern_Arab;

            lookup kern_Arab_marks {
                pos reh-ar fatha-ar <80 0 80 0>;
            } kern_Arab_marks;

            lookup kern_Latn {
                lookupflag IgnoreMarks;
                enum pos @kern1.Latn.A V -40;
            } kern_Latn;

            lookup kern_Latn_marks {
                pos V acutecomb 70;
            } kern_Latn_marks;

            lookup kern_Default {
                lookupflag IgnoreMarks;
                pos seven four -25;
            } kern_Default;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Default;

                script arab;
                language dflt;
                lookup kern_Default;
                lookup kern_Arab;
                lookup kern_Arab_marks;

                script latn;
                language dflt;
                lookup kern_Default;
                lookup kern_Latn;
                lookup kern_Latn_marks;
            } kern;
            """
        )

    def test_kern_RTL_with_marks(self, FontClass):
        glyphs = {
            ".notdef": None,
            "alef-ar": 0x627,
            "reh-ar": 0x631,
            "zain-ar": 0x632,
            "lam-ar": 0x644,
            "four-ar": 0x664,
            "seven-ar": 0x667,
            "fatha-ar": 0x64E,
            # # we also add glyphs without unicode codepoint, but linked to
            # # an encoded 'character' glyph by some GSUB rule
            "alef-ar.isol": None,
            "lam-ar.init": None,
            "reh-ar.fina": None,
        }
        groups = {
            "public.kern1.reh": ["reh-ar", "zain-ar", "reh-ar.fina"],
            "public.kern2.alef": ["alef-ar", "alef-ar.isol"],
        }
        kerning = {
            ("reh-ar.fina", "lam-ar.init"): -80,
            ("public.kern1.reh", "public.kern2.alef"): -100,
            ("reh-ar", "fatha-ar"): 80,
        }
        features = dedent(
            """\
            languagesystem arab dflt;
            languagesystem arab ARA;

            feature init {
                script arab;
                sub lam-ar by lam-ar.init;
            } init;

            feature fina {
                script arab;
                sub reh-ar by reh-ar.fina;
            } fina;

            feature isol {
                script arab;
                sub alef-ar by alef-ar.isol;
            } isol;

            @Bases = [alef-ar reh-ar zain-ar lam-ar alef-ar.isol lam-ar.init reh-ar.fina];
            @Marks = [fatha-ar];
            table GDEF {
                GlyphClassDef @Bases, [], @Marks, ;
            } GDEF;
            """
        )

        ufo = makeUFO(FontClass, glyphs, groups, kerning, features)

        newFeatures = self.writeFeatures(ufo)

        assert dedent(str(newFeatures)).lstrip("\n") == dedent(
            """\
            @kern1.Arab.reh = [reh-ar reh-ar.fina zain-ar];
            @kern2.Arab.alef = [alef-ar alef-ar.isol];

            lookup kern_Arab {
                lookupflag IgnoreMarks;
                pos reh-ar.fina lam-ar.init <-80 0 -80 0>;
                pos @kern1.Arab.reh @kern2.Arab.alef <-100 0 -100 0>;
            } kern_Arab;

            lookup kern_Arab_marks {
                pos reh-ar fatha-ar <80 0 80 0>;
            } kern_Arab_marks;

            feature kern {
                script arab;
                language dflt;
                lookup kern_Arab;
                lookup kern_Arab_marks;
            } kern;
            """
        )

    def test_kern_independent_of_languagesystem(self, FontClass):
        glyphs = {"A": 0x41, "V": 0x56, "reh-ar": 0x631, "alef-ar": 0x627}
        kerning = {("A", "V"): -40, ("reh-ar", "alef-ar"): -100}
        # No languagesystems decalred.
        ufo = makeUFO(FontClass, glyphs, kerning=kerning)
        generated = self.writeFeatures(ufo)

        expectation = dedent(
            """\
            lookup kern_Arab {
                lookupflag IgnoreMarks;
                pos reh-ar alef-ar <-100 0 -100 0>;
            } kern_Arab;

            lookup kern_Latn {
                lookupflag IgnoreMarks;
                pos A V -40;
            } kern_Latn;

            feature kern {
                script arab;
                language dflt;
                lookup kern_Arab;

                script latn;
                language dflt;
                lookup kern_Latn;
            } kern;
            """
        )
        assert dedent(str(generated)) == expectation

        features = dedent("languagesystem arab dflt;")
        ufo = makeUFO(FontClass, glyphs, kerning=kerning, features=features)
        generated = self.writeFeatures(ufo)

        assert dedent(str(generated)).lstrip("\n") == expectation

    def test_dist_LTR(self, FontClass):
        glyphs = {"aaMatra_kannada": 0x0CBE, "ailength_kannada": 0xCD6}
        groups = {
            "public.kern1.KND_aaMatra_R": ["aaMatra_kannada"],
            "public.kern2.KND_ailength_L": ["aaMatra_kannada"],
        }
        kerning = {("public.kern1.KND_aaMatra_R", "public.kern2.KND_ailength_L"): 34}
        features = dedent(
            """\
            languagesystem DFLT dflt;
            languagesystem latn dflt;
            languagesystem knda dflt;
            languagesystem knd2 dflt;
            """
        )

        ufo = makeUFO(FontClass, glyphs, groups, kerning, features)
        generated = self.writeFeatures(ufo)

        assert dedent(str(generated)) == dedent(
            """\
            @kern1.Knda.KND_aaMatra_R = [aaMatra_kannada];
            @kern2.Knda.KND_ailength_L = [aaMatra_kannada];

            lookup kern_Knda {
                lookupflag IgnoreMarks;
                pos @kern1.Knda.KND_aaMatra_R @kern2.Knda.KND_ailength_L 34;
            } kern_Knda;

            feature dist {
                script knd2;
                language dflt;
                lookup kern_Knda;

                script knda;
                language dflt;
                lookup kern_Knda;
            } dist;
            """
        )

    def test_dist_RTL(self, FontClass):
        glyphs = {"u10A06": 0x10A06, "u10A1E": 0x10A1E}
        kerning = {("u10A1E", "u10A06"): 117}
        features = dedent(
            """\
            languagesystem DFLT dflt;
            languagesystem arab dflt;
            languagesystem khar dflt;
            """
        )
        ufo = makeUFO(FontClass, glyphs, kerning=kerning, features=features)
        generated = self.writeFeatures(ufo)

        assert str(generated) == dedent(
            """
            lookup kern_Khar {
                lookupflag IgnoreMarks;
                pos u10A1E u10A06 <117 0 117 0>;
            } kern_Khar;

            feature dist {
                script khar;
                language dflt;
                lookup kern_Khar;
            } dist;
            """
        )

    def test_dist_LTR_and_RTL(self, FontClass):
        glyphs = {
            "aaMatra_kannada": 0x0CBE,
            "ailength_kannada": 0xCD6,
            "u10A06": 0x10A06,
            "u10A1E": 0x10A1E,
        }
        groups = {
            "public.kern1.KND_aaMatra_R": ["aaMatra_kannada"],
            "public.kern2.KND_ailength_L": ["aaMatra_kannada"],
        }
        kerning = {
            ("public.kern1.KND_aaMatra_R", "public.kern2.KND_ailength_L"): 34,
            ("u10A1E", "u10A06"): 117,
        }
        features = dedent(
            """\
            languagesystem DFLT dflt;
            languagesystem knda dflt;
            languagesystem knd2 dflt;
            languagesystem khar dflt;
            """
        )

        ufo = makeUFO(FontClass, glyphs, groups, kerning, features)
        generated = self.writeFeatures(ufo)

        assert dedent(str(generated)).lstrip("\n") == dedent(
            """\
            @kern1.Knda.KND_aaMatra_R = [aaMatra_kannada];
            @kern2.Knda.KND_ailength_L = [aaMatra_kannada];

            lookup kern_Khar {
                lookupflag IgnoreMarks;
                pos u10A1E u10A06 <117 0 117 0>;
            } kern_Khar;

            lookup kern_Knda {
                lookupflag IgnoreMarks;
                pos @kern1.Knda.KND_aaMatra_R @kern2.Knda.KND_ailength_L 34;
            } kern_Knda;

            feature dist {
                script khar;
                language dflt;
                lookup kern_Khar;

                script knd2;
                language dflt;
                lookup kern_Knda;

                script knda;
                language dflt;
                lookup kern_Knda;
            } dist;
            """
        )

    def test_ambiguous_direction_pair(self, FontClass, caplog):
        ufo = FontClass()
        ufo.newGlyph("A").unicode = 0x41
        ufo.newGlyph("one").unicode = 0x31
        ufo.newGlyph("yod-hb").unicode = 0x5D9
        ufo.newGlyph("reh-ar").unicode = 0x631
        ufo.newGlyph("one-ar").unicode = 0x661
        ufo.newGlyph("bar").unicodes = [0x73, 0x627]
        ufo.kerning.update(
            {
                ("bar", "bar"): 1,
                ("bar", "A"): 2,
                ("reh-ar", "A"): 3,
                ("reh-ar", "one-ar"): 4,
                ("yod-hb", "one"): 5,
            }
        )
        ufo.features.text = dedent(
            """\
            languagesystem DFLT dflt;
            languagesystem latn dflt;
            languagesystem arab dflt;
            """
        )

        with caplog.at_level(logging.INFO):
            generated = self.writeFeatures(ufo)

        assert not generated
        assert (
            len([r for r in caplog.records if "with ambiguous direction" in r.message])
            == 5
        )

    def test_kern_RTL_and_DFLT_numbers(self, FontClass):
        glyphs = {"four": 0x34, "seven": 0x37, "bet-hb": 0x5D1, "yod-hb": 0x5D9}
        kerning = {("seven", "four"): -25, ("yod-hb", "bet-hb"): -100}
        features = dedent(
            """\
            languagesystem DFLT dflt;
            languagesystem hebr dflt;
            """
        )

        ufo = makeUFO(FontClass, glyphs, kerning=kerning, features=features)
        generated = self.writeFeatures(ufo)

        assert dedent(str(generated)) == dedent(
            """
            lookup kern_Hebr {
                lookupflag IgnoreMarks;
                pos yod-hb bet-hb <-100 0 -100 0>;
            } kern_Hebr;

            lookup kern_Default {
                lookupflag IgnoreMarks;
                pos seven four -25;
            } kern_Default;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Default;

                script hebr;
                language dflt;
                lookup kern_Default;
                lookup kern_Hebr;
            } kern;
            """
        )

    def test_quantize(self, FontClass):
        font = FontClass()
        for name in ("one", "four", "six"):
            font.newGlyph(name)
        font.kerning.update({("four", "six"): -57.0, ("one", "six"): -24.0})
        writer = KernFeatureWriter(quantization=5)
        feaFile = ast.FeatureFile()
        assert writer.write(font, feaFile)

        assert str(feaFile) == dedent(
            """\
            lookup kern_Default {
                lookupflag IgnoreMarks;
                pos four six -55;
                pos one six -25;
            } kern_Default;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Default;
            } kern;
            """
        )


def test_kern_split_multi_glyph_class(FontClass):
    glyphs = {
        "a": ord("a"),
        "b": ord("b"),
        "period": ord("."),
    }
    groups = {
        "public.kern1.foo": ["a", "period"],
        "public.kern2.foo": ["b", "period"],
    }
    kerning = {
        ("a", "a"): 1,
        ("a", "b"): 2,
        ("a", "period"): 3,
        ("b", "a"): 4,
        ("b", "b"): 5,
        ("b", "period"): 6,
        ("period", "a"): 7,
        ("period", "b"): 8,
        ("period", "period"): 9,
        # Class-to-glyph
        ("public.kern1.foo", "b"): 10,
        ("public.kern1.foo", "period"): 11,
        # Glyph-to-class
        ("a", "public.kern2.foo"): 12,
        ("period", "public.kern2.foo"): 13,
        # Class-to-class
        ("public.kern1.foo", "public.kern2.foo"): 14,
    }
    expectation = dedent(
        """\
        @kern1.Default.foo = [period];
        @kern1.Latn.foo = [a];
        @kern2.Default.foo = [period];
        @kern2.Latn.foo = [b];

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            pos a a 1;
            pos a b 2;
            pos a period 3;
            pos b a 4;
            pos b b 5;
            pos b period 6;
            pos period a 7;
            pos period b 8;
            enum pos a @kern2.Latn.foo 12;
            enum pos a @kern2.Default.foo 12;
            enum pos period @kern2.Latn.foo 13;
            enum pos @kern1.Latn.foo b 10;
            enum pos @kern1.Latn.foo period 11;
            enum pos @kern1.Default.foo b 10;
            pos @kern1.Latn.foo @kern2.Latn.foo 14;
            pos @kern1.Latn.foo @kern2.Default.foo 14;
            pos @kern1.Default.foo @kern2.Latn.foo 14;
        } kern_Latn;

        lookup kern_Default {
            lookupflag IgnoreMarks;
            pos period period 9;
            enum pos period @kern2.Default.foo 13;
            enum pos @kern1.Default.foo period 11;
            pos @kern1.Default.foo @kern2.Default.foo 14;
        } kern_Default;

        feature kern {
            script DFLT;
            language dflt;
            lookup kern_Default;

            script latn;
            language dflt;
            lookup kern_Default;
            lookup kern_Latn;
        } kern;
        """
    )

    ufo = makeUFO(FontClass, glyphs, groups, kerning)
    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert dedent(str(newFeatures)).lstrip("\n") == expectation

    # Making a common glyph implicitly have an explicit script assigned (GSUB
    # closure) will still keep it in the common section.
    features = dedent(
        """
        feature ss01 {
            sub a by period; # Make period be both Latn and Zyyy.
        } ss01;
        """
    )
    ufo = makeUFO(FontClass, glyphs, groups, kerning, features)
    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert dedent(str(newFeatures)).lstrip("\n") == expectation


def test_kern_split_and_drop(FontClass, caplog):
    glyphs = {
        "a": ord("a"),
        "alpha": ord("α"),
        "a-orya": 0x0B05,
        "a-cy": 0x0430,
        "alef-ar": 0x627,
        "period": ord("."),
    }
    groups = {
        "public.kern1.foo": ["a", "alpha", "a-orya"],
        "public.kern2.foo": ["a", "alpha", "a-orya"],
        "public.kern1.bar": ["a-cy", "alef-ar", "period"],
        "public.kern2.bar": ["a-cy", "alef-ar", "period"],
    }
    kerning = {
        ("public.kern1.foo", "public.kern2.bar"): 20,
        ("public.kern1.bar", "public.kern2.foo"): 20,
    }

    ufo = makeUFO(FontClass, glyphs, groups, kerning)
    with caplog.at_level(logging.INFO):
        newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert dedent(str(newFeatures)) == dedent(
        """\
        @kern1.Grek.bar = [period];
        @kern1.Grek.foo = [alpha];
        @kern1.Latn.foo = [a];
        @kern1.Orya.foo = [a-orya];
        @kern2.Grek.bar = [period];
        @kern2.Grek.foo = [alpha];
        @kern2.Latn.foo = [a];
        @kern2.Orya.foo = [a-orya];

        lookup kern_Grek {
            lookupflag IgnoreMarks;
            pos @kern1.Grek.foo @kern2.Grek.bar 20;
            pos @kern1.Grek.bar @kern2.Grek.foo 20;
        } kern_Grek;

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            pos @kern1.Latn.foo @kern2.Grek.bar 20;
            pos @kern1.Grek.bar @kern2.Latn.foo 20;
        } kern_Latn;

        lookup kern_Orya {
            lookupflag IgnoreMarks;
            pos @kern1.Orya.foo @kern2.Grek.bar 20;
            pos @kern1.Grek.bar @kern2.Orya.foo 20;
        } kern_Orya;

        feature kern {
            script grek;
            language dflt;
            lookup kern_Grek;

            script latn;
            language dflt;
            lookup kern_Latn;
        } kern;

        feature dist {
            script ory2;
            language dflt;
            lookup kern_Orya;

            script orya;
            language dflt;
            lookup kern_Orya;
        } dist;
        """
    )

    msgs = sorted(msg[-30:] for msg in caplog.messages)
    assert msgs == [
        "with mixed script (Arab, Grek)",
        "with mixed script (Arab, Latn)",
        "with mixed script (Arab, Orya)",
        "with mixed script (Cyrl, Grek)",
        "with mixed script (Cyrl, Latn)",
        "with mixed script (Cyrl, Orya)",
        "with mixed script (Grek, Arab)",
        "with mixed script (Grek, Cyrl)",
        "with mixed script (Latn, Arab)",
        "with mixed script (Latn, Cyrl)",
        "with mixed script (Orya, Arab)",
        "with mixed script (Orya, Cyrl)",
    ]


def test_kern_split_and_drop_mixed(caplog, FontClass):
    """Test that mixed script pairs don't go anywhere."""
    glyphs = {"V": ord("V"), "W": ord("W"), "gba-nko": 0x07DC}
    groups = {"public.kern1.foo": ["V", "W"], "public.kern2.foo": ["gba-nko", "W"]}
    kerning = {("public.kern1.foo", "public.kern2.foo"): -20}
    ufo = makeUFO(FontClass, glyphs, groups, kerning)
    with caplog.at_level(logging.INFO):
        newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert dedent(str(newFeatures)) == dedent(
        """\
        @kern1.Latn.foo = [V W];
        @kern2.Latn.foo = [W];

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            pos @kern1.Latn.foo @kern2.Latn.foo -20;
        } kern_Latn;

        feature kern {
            script latn;
            language dflt;
            lookup kern_Latn;
        } kern;
        """
    )
    assert (
        "Skipping kerning pair <('V', 'W') ('W', 'gba-nko') -20> with mixed script (Latn, Nkoo)"
        in caplog.text
    )


def test_kern_split_and_mix_common(FontClass):
    """Test that that everyone gets common-script glyphs, but they get it
    per-script."""
    glyphs = {"V": ord("V"), "W": ord("W"), "gba-nko": 0x07DC, "period": ord(".")}
    groups = {"public.kern1.foo": ["V", "gba-nko", "W"]}
    kerning = {("public.kern1.foo", "period"): -20}
    ufo = makeUFO(FontClass, glyphs, groups, kerning)
    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert dedent(str(newFeatures)) == dedent(
        """\
        @kern1.Latn.foo = [V W];
        @kern1.Nkoo.foo = [gba-nko];

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            enum pos @kern1.Latn.foo period -20;
        } kern_Latn;

        lookup kern_Nkoo {
            lookupflag IgnoreMarks;
            enum pos @kern1.Nkoo.foo period <-20 0 -20 0>;
        } kern_Nkoo;

        feature kern {
            script latn;
            language dflt;
            lookup kern_Latn;

            script nko;
            language dflt;
            lookup kern_Nkoo;
        } kern;
        """
    )


def test_kern_keep_common(FontClass):
    """Test that if both sides are common, the output is common."""
    glyphs = {"period": ord(".")}
    kerning = {("period", "period"): -20}
    ufo = makeUFO(FontClass, glyphs, None, kerning)
    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert dedent(str(newFeatures)) == dedent(
        """\
        lookup kern_Default {
            lookupflag IgnoreMarks;
            pos period period -20;
        } kern_Default;

        feature kern {
            script DFLT;
            language dflt;
            lookup kern_Default;
        } kern;
        """
    )


def test_kern_multi_script(FontClass):
    """Test that glyphs with more than one script get associated with all of the
    relevant scripts in the pair."""
    glyphs = {"gba-nko": 0x07DC, "comma-ar": 0x060C, "lam-ar": 0x0644}
    groups = {
        "public.kern1.foo": ["lam-ar", "gba-nko"],
        "public.kern2.foo": ["comma-ar"],
    }
    kerning = {("public.kern1.foo", "public.kern2.foo"): -20}
    ufo = makeUFO(FontClass, glyphs, groups, kerning)
    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert dedent(str(newFeatures)) == dedent(
        """\
        @kern1.Arab.foo = [lam-ar];
        @kern1.Nkoo.foo = [gba-nko];
        @kern2.Arab.foo = [comma-ar];

        lookup kern_Arab {
            lookupflag IgnoreMarks;
            pos @kern1.Arab.foo @kern2.Arab.foo <-20 0 -20 0>;
        } kern_Arab;

        lookup kern_Nkoo {
            lookupflag IgnoreMarks;
            pos @kern1.Nkoo.foo @kern2.Arab.foo <-20 0 -20 0>;
        } kern_Nkoo;

        feature kern {
            script arab;
            language dflt;
            lookup kern_Arab;

            script nko;
            language dflt;
            lookup kern_Nkoo;
        } kern;
        """
    )


def test_kern_mixed_bidis(caplog, FontClass):
    """Test that BiDi types for pairs are respected."""
    glyphs = {
        "a": ord("a"),
        "comma": ord(","),
        "alef-ar": 0x0627,
        "comma-ar": 0x060C,
        "one-ar": 0x0661,
    }
    kerning = {
        # Undetermined: LTR
        ("comma", "comma"): -1,
        # LTR
        ("a", "a"): 1,
        ("a", "comma"): 2,
        ("comma", "a"): 3,
        # RTL
        ("alef-ar", "alef-ar"): 4,
        ("alef-ar", "comma-ar"): 5,
        ("comma-ar", "alef-ar"): 6,
        # Mixed: should be dropped
        ("alef-ar", "one-ar"): 7,
        ("one-ar", "alef-ar"): 8,
        # LTR despite being an RTL script
        ("one-ar", "one-ar"): 9,
    }
    ufo = makeUFO(FontClass, glyphs, None, kerning)
    with caplog.at_level(logging.INFO):
        newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert dedent(str(newFeatures)) == dedent(
        """\
        lookup kern_Arab {
            lookupflag IgnoreMarks;
            pos alef-ar alef-ar <4 0 4 0>;
            pos alef-ar comma-ar <5 0 5 0>;
            pos comma-ar alef-ar <6 0 6 0>;
            pos one-ar one-ar 9;
        } kern_Arab;

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            pos a a 1;
            pos a comma 2;
            pos comma a 3;
        } kern_Latn;

        lookup kern_Default {
            lookupflag IgnoreMarks;
            pos comma comma -1;
        } kern_Default;

        feature kern {
            script DFLT;
            language dflt;
            lookup kern_Default;

            script arab;
            language dflt;
            lookup kern_Default;
            lookup kern_Arab;

            script latn;
            language dflt;
            lookup kern_Default;
            lookup kern_Latn;
        } kern;
        """
    )
    assert "<alef-ar one-ar 7> with ambiguous direction" in caplog.text
    assert "<one-ar alef-ar 8> with ambiguous direction" in caplog.text


def unicodeScript(codepoint: int) -> str:
    """Returns the Unicode script for a codepoint, combining some
    scripts into the same bucket.

    This allows lookups to contain more than one script. The most prominent case
    is being able to kern Hiragana and Katakana against each other, Unicode
    defines "Hrkt" as an alias for both scripts.

    Note: Keep in sync with unicodeScriptExtensions!
    """
    script = unicodedata.script(chr(codepoint))
    return UNICODE_SCRIPT_ALIASES.get(script, script)


def test_kern_zyyy_zinh(FontClass):
    """Test that a sampling of glyphs with a common or inherited script, but a
    disjoint set of explicit script extensions end up in the correct lookups."""
    glyphs = {}
    for i in range(0, 0x110000, 0x10):
        script = unicodeScript(i)
        script_extension = unicodeScriptExtensions(i)
        if script not in script_extension:
            assert script in DFLT_SCRIPTS
            name = f"uni{i:04X}"
            glyphs[name] = i
    kerning = {(glyph, glyph): i for i, glyph in enumerate(glyphs)}
    ufo = makeUFO(FontClass, glyphs, None, kerning)
    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert dedent(str(newFeatures)) == dedent(
        """\
        lookup kern_Deva {
            lookupflag IgnoreMarks;
            pos uni1CD0 uni1CD0 3;
            pos uni1CE0 uni1CE0 4;
            pos uni1CF0 uni1CF0 5;
            pos uni20F0 uni20F0 7;
            pos uniA830 uniA830 28;
        } kern_Deva;

        lookup kern_Dupl {
            lookupflag IgnoreMarks;
            pos uni1BCA0 uni1BCA0 36;
        } kern_Dupl;

        lookup kern_Grek {
            lookupflag IgnoreMarks;
            pos uni1DC0 uni1DC0 6;
        } kern_Grek;

        lookup kern_Hani {
            lookupflag IgnoreMarks;
            pos uni1D360 uni1D360 37;
            pos uni1D370 uni1D370 38;
            pos uni1F250 uni1F250 39;
            pos uni3010 uni3010 8;
            pos uni3030 uni3030 9;
            pos uni3190 uni3190 11;
            pos uni31C0 uni31C0 12;
            pos uni31D0 uni31D0 13;
            pos uni31E0 uni31E0 14;
            pos uni3220 uni3220 15;
            pos uni3230 uni3230 16;
            pos uni3240 uni3240 17;
            pos uni3280 uni3280 18;
            pos uni3290 uni3290 19;
            pos uni32A0 uni32A0 20;
            pos uni32B0 uni32B0 21;
            pos uni32C0 uni32C0 22;
            pos uni3360 uni3360 23;
            pos uni3370 uni3370 24;
            pos uni33E0 uni33E0 25;
            pos uni33F0 uni33F0 26;
            pos uniA700 uniA700 27;
        } kern_Hani;

        lookup kern_Hrkt {
            lookupflag IgnoreMarks;
            pos uni3010 uni3010 8;
            pos uni3030 uni3030 9;
            pos uni30A0 uni30A0 10;
            pos uniFF70 uniFF70 29;
        } kern_Hrkt;

        lookup kern_Default {
            lookupflag IgnoreMarks;
            pos uni0640 uni0640 0;
            pos uni0650 uni0650 1;
            pos uni0670 uni0670 2;
            pos uni10100 uni10100 30;
            pos uni10110 uni10110 31;
            pos uni10120 uni10120 32;
            pos uni10130 uni10130 33;
            pos uni102E0 uni102E0 34;
            pos uni102F0 uni102F0 35;
        } kern_Default;

        feature kern {
            script DFLT;
            language dflt;
            lookup kern_Default;

            script grek;
            language dflt;
            lookup kern_Default;
            lookup kern_Grek;

            script hani;
            language dflt;
            lookup kern_Default;
            lookup kern_Hani;

            script kana;
            language dflt;
            lookup kern_Default;
            lookup kern_Hrkt;
        } kern;

        feature dist {
            script dev2;
            language dflt;
            lookup kern_Default;
            lookup kern_Deva;

            script deva;
            language dflt;
            lookup kern_Default;
            lookup kern_Deva;

            script dupl;
            language dflt;
            lookup kern_Default;
            lookup kern_Dupl;
        } dist;
        """
    )


def test_kern_hira_kana_hrkt(FontClass):
    """Test that Hiragana and Katakana lands in the same lookup and can be
    kerned against each other and common glyphs are kerned just once."""
    glyphs = {"a-hira": 0x3042, "a-kana": 0x30A2, "period": ord(".")}
    kerning = {
        ("a-hira", "a-hira"): 1,
        ("a-hira", "a-kana"): 2,
        ("a-kana", "a-hira"): 3,
        ("a-kana", "a-kana"): 4,
        ("period", "period"): 5,
        ("a-hira", "period"): 6,
        ("period", "a-hira"): 7,
        ("a-kana", "period"): 8,
        ("period", "a-kana"): 9,
    }
    ufo = makeUFO(FontClass, glyphs, None, kerning)
    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert dedent(str(newFeatures)) == dedent(
        """\
        lookup kern_Hrkt {
            lookupflag IgnoreMarks;
            pos a-hira a-hira 1;
            pos a-hira a-kana 2;
            pos a-hira period 6;
            pos a-kana a-hira 3;
            pos a-kana a-kana 4;
            pos a-kana period 8;
            pos period a-hira 7;
            pos period a-kana 9;
        } kern_Hrkt;

        lookup kern_Default {
            lookupflag IgnoreMarks;
            pos period period 5;
        } kern_Default;

        feature kern {
            script DFLT;
            language dflt;
            lookup kern_Default;

            script kana;
            language dflt;
            lookup kern_Default;
            lookup kern_Hrkt;
        } kern;
        """
    )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main(sys.argv))
