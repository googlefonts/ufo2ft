import logging
from textwrap import dedent

import pytest
from fontTools import unicodedata

from ufo2ft.errors import InvalidFeaturesData
from ufo2ft.featureCompiler import parseLayoutFeatures
from ufo2ft.featureWriters import KernFeatureWriter, ast
from ufo2ft.util import DFLT_SCRIPTS

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


def test_kern_zyyy_zinh(FontClass):
    """Test that glyphs with a common or inherited script, but a disjoint set of
    explicit script extensions end up in the correct lookups."""
    glyphs = {}
    for i in range(0x110000):
        script = unicodedata.script(chr(i))
        script_extension = unicodedata.script_extension(chr(i))
        if script not in script_extension:
            assert script in DFLT_SCRIPTS
            name = f"uni{i:04X}"
            glyphs[name] = i
    kerning = {(glyph, glyph): i for i, glyph in enumerate(glyphs)}
    ufo = makeUFO(FontClass, glyphs, None, kerning)
    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert dedent(str(newFeatures)) == dedent(
        """\
        lookup kern_Beng {
            lookupflag IgnoreMarks;
            pos uni0951 uni0951 33;
            pos uni0952 uni0952 34;
            pos uni0964 uni0964 35;
            pos uni0965 uni0965 36;
            pos uni1CD0 uni1CD0 43;
            pos uni1CD2 uni1CD2 45;
            pos uni1CD5 uni1CD5 48;
            pos uni1CD6 uni1CD6 49;
            pos uni1CD8 uni1CD8 51;
            pos uni1CE1 uni1CE1 60;
            pos uni1CEA uni1CEA 69;
            pos uni1CED uni1CED 72;
            pos uni1CF2 uni1CF2 77;
            pos uni1CF5 uni1CF5 80;
            pos uni1CF6 uni1CF6 81;
            pos uni1CF7 uni1CF7 82;
        } kern_Beng;

        lookup kern_Deva {
            lookupflag IgnoreMarks;
            pos uni0951 uni0951 33;
            pos uni0952 uni0952 34;
            pos uni0964 uni0964 35;
            pos uni0965 uni0965 36;
            pos uni1CD0 uni1CD0 43;
            pos uni1CD1 uni1CD1 44;
            pos uni1CD2 uni1CD2 45;
            pos uni1CD3 uni1CD3 46;
            pos uni1CD4 uni1CD4 47;
            pos uni1CD5 uni1CD5 48;
            pos uni1CD6 uni1CD6 49;
            pos uni1CD7 uni1CD7 50;
            pos uni1CD8 uni1CD8 51;
            pos uni1CD9 uni1CD9 52;
            pos uni1CDA uni1CDA 53;
            pos uni1CDB uni1CDB 54;
            pos uni1CDC uni1CDC 55;
            pos uni1CDD uni1CDD 56;
            pos uni1CDE uni1CDE 57;
            pos uni1CDF uni1CDF 58;
            pos uni1CE0 uni1CE0 59;
            pos uni1CE1 uni1CE1 60;
            pos uni1CE2 uni1CE2 61;
            pos uni1CE3 uni1CE3 62;
            pos uni1CE4 uni1CE4 63;
            pos uni1CE5 uni1CE5 64;
            pos uni1CE6 uni1CE6 65;
            pos uni1CE7 uni1CE7 66;
            pos uni1CE8 uni1CE8 67;
            pos uni1CE9 uni1CE9 68;
            pos uni1CEA uni1CEA 69;
            pos uni1CEB uni1CEB 70;
            pos uni1CEC uni1CEC 71;
            pos uni1CED uni1CED 72;
            pos uni1CEE uni1CEE 73;
            pos uni1CEF uni1CEF 74;
            pos uni1CF0 uni1CF0 75;
            pos uni1CF1 uni1CF1 76;
            pos uni1CF2 uni1CF2 77;
            pos uni1CF3 uni1CF3 78;
            pos uni1CF4 uni1CF4 79;
            pos uni1CF5 uni1CF5 80;
            pos uni1CF6 uni1CF6 81;
            pos uni1CF8 uni1CF8 83;
            pos uni1CF9 uni1CF9 84;
            pos uni20F0 uni20F0 91;
            pos uniA830 uniA830 365;
            pos uniA831 uniA831 366;
            pos uniA832 uniA832 367;
            pos uniA833 uniA833 368;
            pos uniA834 uniA834 369;
            pos uniA835 uniA835 370;
            pos uniA836 uniA836 371;
            pos uniA837 uniA837 372;
            pos uniA838 uniA838 373;
            pos uniA839 uniA839 374;
        } kern_Deva;

        lookup kern_Dupl {
            lookupflag IgnoreMarks;
            pos uni1BCA0 uni1BCA0 475;
            pos uni1BCA1 uni1BCA1 476;
            pos uni1BCA2 uni1BCA2 477;
            pos uni1BCA3 uni1BCA3 478;
        } kern_Dupl;

        lookup kern_Grek {
            lookupflag IgnoreMarks;
            pos uni0342 uni0342 0;
            pos uni0345 uni0345 1;
            pos uni1DC0 uni1DC0 86;
            pos uni1DC1 uni1DC1 87;
        } kern_Grek;

        lookup kern_Hani {
            lookupflag IgnoreMarks;
            pos uni1D360 uni1D360 479;
            pos uni1D361 uni1D361 480;
            pos uni1D362 uni1D362 481;
            pos uni1D363 uni1D363 482;
            pos uni1D364 uni1D364 483;
            pos uni1D365 uni1D365 484;
            pos uni1D366 uni1D366 485;
            pos uni1D367 uni1D367 486;
            pos uni1D368 uni1D368 487;
            pos uni1D369 uni1D369 488;
            pos uni1D36A uni1D36A 489;
            pos uni1D36B uni1D36B 490;
            pos uni1D36C uni1D36C 491;
            pos uni1D36D uni1D36D 492;
            pos uni1D36E uni1D36E 493;
            pos uni1D36F uni1D36F 494;
            pos uni1D370 uni1D370 495;
            pos uni1D371 uni1D371 496;
            pos uni1F250 uni1F250 497;
            pos uni1F251 uni1F251 498;
            pos uni3001 uni3001 93;
            pos uni3002 uni3002 94;
            pos uni3003 uni3003 95;
            pos uni3006 uni3006 96;
            pos uni3008 uni3008 97;
            pos uni3009 uni3009 98;
            pos uni300A uni300A 99;
            pos uni300B uni300B 100;
            pos uni300C uni300C 101;
            pos uni300D uni300D 102;
            pos uni300E uni300E 103;
            pos uni300F uni300F 104;
            pos uni3010 uni3010 105;
            pos uni3011 uni3011 106;
            pos uni3013 uni3013 107;
            pos uni3014 uni3014 108;
            pos uni3015 uni3015 109;
            pos uni3016 uni3016 110;
            pos uni3017 uni3017 111;
            pos uni3018 uni3018 112;
            pos uni3019 uni3019 113;
            pos uni301A uni301A 114;
            pos uni301B uni301B 115;
            pos uni301C uni301C 116;
            pos uni301D uni301D 117;
            pos uni301E uni301E 118;
            pos uni301F uni301F 119;
            pos uni302A uni302A 120;
            pos uni302B uni302B 121;
            pos uni302C uni302C 122;
            pos uni302D uni302D 123;
            pos uni3030 uni3030 124;
            pos uni3037 uni3037 130;
            pos uni303C uni303C 131;
            pos uni303D uni303D 132;
            pos uni303E uni303E 133;
            pos uni303F uni303F 134;
            pos uni30FB uni30FB 140;
            pos uni3190 uni3190 142;
            pos uni3191 uni3191 143;
            pos uni3192 uni3192 144;
            pos uni3193 uni3193 145;
            pos uni3194 uni3194 146;
            pos uni3195 uni3195 147;
            pos uni3196 uni3196 148;
            pos uni3197 uni3197 149;
            pos uni3198 uni3198 150;
            pos uni3199 uni3199 151;
            pos uni319A uni319A 152;
            pos uni319B uni319B 153;
            pos uni319C uni319C 154;
            pos uni319D uni319D 155;
            pos uni319E uni319E 156;
            pos uni319F uni319F 157;
            pos uni31C0 uni31C0 158;
            pos uni31C1 uni31C1 159;
            pos uni31C2 uni31C2 160;
            pos uni31C3 uni31C3 161;
            pos uni31C4 uni31C4 162;
            pos uni31C5 uni31C5 163;
            pos uni31C6 uni31C6 164;
            pos uni31C7 uni31C7 165;
            pos uni31C8 uni31C8 166;
            pos uni31C9 uni31C9 167;
            pos uni31CA uni31CA 168;
            pos uni31CB uni31CB 169;
            pos uni31CC uni31CC 170;
            pos uni31CD uni31CD 171;
            pos uni31CE uni31CE 172;
            pos uni31CF uni31CF 173;
            pos uni31D0 uni31D0 174;
            pos uni31D1 uni31D1 175;
            pos uni31D2 uni31D2 176;
            pos uni31D3 uni31D3 177;
            pos uni31D4 uni31D4 178;
            pos uni31D5 uni31D5 179;
            pos uni31D6 uni31D6 180;
            pos uni31D7 uni31D7 181;
            pos uni31D8 uni31D8 182;
            pos uni31D9 uni31D9 183;
            pos uni31DA uni31DA 184;
            pos uni31DB uni31DB 185;
            pos uni31DC uni31DC 186;
            pos uni31DD uni31DD 187;
            pos uni31DE uni31DE 188;
            pos uni31DF uni31DF 189;
            pos uni31E0 uni31E0 190;
            pos uni31E1 uni31E1 191;
            pos uni31E2 uni31E2 192;
            pos uni31E3 uni31E3 193;
            pos uni3220 uni3220 194;
            pos uni3221 uni3221 195;
            pos uni3222 uni3222 196;
            pos uni3223 uni3223 197;
            pos uni3224 uni3224 198;
            pos uni3225 uni3225 199;
            pos uni3226 uni3226 200;
            pos uni3227 uni3227 201;
            pos uni3228 uni3228 202;
            pos uni3229 uni3229 203;
            pos uni322A uni322A 204;
            pos uni322B uni322B 205;
            pos uni322C uni322C 206;
            pos uni322D uni322D 207;
            pos uni322E uni322E 208;
            pos uni322F uni322F 209;
            pos uni3230 uni3230 210;
            pos uni3231 uni3231 211;
            pos uni3232 uni3232 212;
            pos uni3233 uni3233 213;
            pos uni3234 uni3234 214;
            pos uni3235 uni3235 215;
            pos uni3236 uni3236 216;
            pos uni3237 uni3237 217;
            pos uni3238 uni3238 218;
            pos uni3239 uni3239 219;
            pos uni323A uni323A 220;
            pos uni323B uni323B 221;
            pos uni323C uni323C 222;
            pos uni323D uni323D 223;
            pos uni323E uni323E 224;
            pos uni323F uni323F 225;
            pos uni3240 uni3240 226;
            pos uni3241 uni3241 227;
            pos uni3242 uni3242 228;
            pos uni3243 uni3243 229;
            pos uni3244 uni3244 230;
            pos uni3245 uni3245 231;
            pos uni3246 uni3246 232;
            pos uni3247 uni3247 233;
            pos uni3280 uni3280 234;
            pos uni3281 uni3281 235;
            pos uni3282 uni3282 236;
            pos uni3283 uni3283 237;
            pos uni3284 uni3284 238;
            pos uni3285 uni3285 239;
            pos uni3286 uni3286 240;
            pos uni3287 uni3287 241;
            pos uni3288 uni3288 242;
            pos uni3289 uni3289 243;
            pos uni328A uni328A 244;
            pos uni328B uni328B 245;
            pos uni328C uni328C 246;
            pos uni328D uni328D 247;
            pos uni328E uni328E 248;
            pos uni328F uni328F 249;
            pos uni3290 uni3290 250;
            pos uni3291 uni3291 251;
            pos uni3292 uni3292 252;
            pos uni3293 uni3293 253;
            pos uni3294 uni3294 254;
            pos uni3295 uni3295 255;
            pos uni3296 uni3296 256;
            pos uni3297 uni3297 257;
            pos uni3298 uni3298 258;
            pos uni3299 uni3299 259;
            pos uni329A uni329A 260;
            pos uni329B uni329B 261;
            pos uni329C uni329C 262;
            pos uni329D uni329D 263;
            pos uni329E uni329E 264;
            pos uni329F uni329F 265;
            pos uni32A0 uni32A0 266;
            pos uni32A1 uni32A1 267;
            pos uni32A2 uni32A2 268;
            pos uni32A3 uni32A3 269;
            pos uni32A4 uni32A4 270;
            pos uni32A5 uni32A5 271;
            pos uni32A6 uni32A6 272;
            pos uni32A7 uni32A7 273;
            pos uni32A8 uni32A8 274;
            pos uni32A9 uni32A9 275;
            pos uni32AA uni32AA 276;
            pos uni32AB uni32AB 277;
            pos uni32AC uni32AC 278;
            pos uni32AD uni32AD 279;
            pos uni32AE uni32AE 280;
            pos uni32AF uni32AF 281;
            pos uni32B0 uni32B0 282;
            pos uni32C0 uni32C0 283;
            pos uni32C1 uni32C1 284;
            pos uni32C2 uni32C2 285;
            pos uni32C3 uni32C3 286;
            pos uni32C4 uni32C4 287;
            pos uni32C5 uni32C5 288;
            pos uni32C6 uni32C6 289;
            pos uni32C7 uni32C7 290;
            pos uni32C8 uni32C8 291;
            pos uni32C9 uni32C9 292;
            pos uni32CA uni32CA 293;
            pos uni32CB uni32CB 294;
            pos uni32FF uni32FF 295;
            pos uni3358 uni3358 296;
            pos uni3359 uni3359 297;
            pos uni335A uni335A 298;
            pos uni335B uni335B 299;
            pos uni335C uni335C 300;
            pos uni335D uni335D 301;
            pos uni335E uni335E 302;
            pos uni335F uni335F 303;
            pos uni3360 uni3360 304;
            pos uni3361 uni3361 305;
            pos uni3362 uni3362 306;
            pos uni3363 uni3363 307;
            pos uni3364 uni3364 308;
            pos uni3365 uni3365 309;
            pos uni3366 uni3366 310;
            pos uni3367 uni3367 311;
            pos uni3368 uni3368 312;
            pos uni3369 uni3369 313;
            pos uni336A uni336A 314;
            pos uni336B uni336B 315;
            pos uni336C uni336C 316;
            pos uni336D uni336D 317;
            pos uni336E uni336E 318;
            pos uni336F uni336F 319;
            pos uni3370 uni3370 320;
            pos uni337B uni337B 321;
            pos uni337C uni337C 322;
            pos uni337D uni337D 323;
            pos uni337E uni337E 324;
            pos uni337F uni337F 325;
            pos uni33E0 uni33E0 326;
            pos uni33E1 uni33E1 327;
            pos uni33E2 uni33E2 328;
            pos uni33E3 uni33E3 329;
            pos uni33E4 uni33E4 330;
            pos uni33E5 uni33E5 331;
            pos uni33E6 uni33E6 332;
            pos uni33E7 uni33E7 333;
            pos uni33E8 uni33E8 334;
            pos uni33E9 uni33E9 335;
            pos uni33EA uni33EA 336;
            pos uni33EB uni33EB 337;
            pos uni33EC uni33EC 338;
            pos uni33ED uni33ED 339;
            pos uni33EE uni33EE 340;
            pos uni33EF uni33EF 341;
            pos uni33F0 uni33F0 342;
            pos uni33F1 uni33F1 343;
            pos uni33F2 uni33F2 344;
            pos uni33F3 uni33F3 345;
            pos uni33F4 uni33F4 346;
            pos uni33F5 uni33F5 347;
            pos uni33F6 uni33F6 348;
            pos uni33F7 uni33F7 349;
            pos uni33F8 uni33F8 350;
            pos uni33F9 uni33F9 351;
            pos uni33FA uni33FA 352;
            pos uni33FB uni33FB 353;
            pos uni33FC uni33FC 354;
            pos uni33FD uni33FD 355;
            pos uni33FE uni33FE 356;
            pos uniA700 uniA700 357;
            pos uniA701 uniA701 358;
            pos uniA702 uniA702 359;
            pos uniA703 uniA703 360;
            pos uniA704 uniA704 361;
            pos uniA705 uniA705 362;
            pos uniA706 uniA706 363;
            pos uniA707 uniA707 364;
            pos uniFE45 uniFE45 379;
            pos uniFE46 uniFE46 380;
            pos uniFF61 uniFF61 381;
            pos uniFF62 uniFF62 382;
            pos uniFF63 uniFF63 383;
            pos uniFF64 uniFF64 384;
            pos uniFF65 uniFF65 385;
        } kern_Hani;

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            pos uni0363 uni0363 2;
            pos uni0364 uni0364 3;
            pos uni0365 uni0365 4;
            pos uni0366 uni0366 5;
            pos uni0367 uni0367 6;
            pos uni0368 uni0368 7;
            pos uni0369 uni0369 8;
            pos uni036A uni036A 9;
            pos uni036B uni036B 10;
            pos uni036C uni036C 11;
            pos uni036D uni036D 12;
            pos uni036E uni036E 13;
            pos uni036F uni036F 14;
            pos uni0485 uni0485 15;
            pos uni0486 uni0486 16;
            pos uni0951 uni0951 33;
            pos uni0952 uni0952 34;
            pos uni10FB uni10FB 37;
            pos uni202F uni202F 90;
            pos uni20F0 uni20F0 91;
            pos uniA700 uniA700 357;
            pos uniA701 uniA701 358;
            pos uniA702 uniA702 359;
            pos uniA703 uniA703 360;
            pos uniA704 uniA704 361;
            pos uniA705 uniA705 362;
            pos uniA706 uniA706 363;
            pos uniA707 uniA707 364;
            pos uniA92E uniA92E 375;
        } kern_Latn;

        lookup kern_Nand {
            lookupflag IgnoreMarks;
            pos uni0964 uni0964 35;
            pos uni0965 uni0965 36;
            pos uni1CE9 uni1CE9 68;
            pos uni1CF2 uni1CF2 77;
            pos uni1CFA uni1CFA 85;
            pos uniA830 uniA830 365;
            pos uniA831 uniA831 366;
            pos uniA832 uniA832 367;
            pos uniA833 uniA833 368;
            pos uniA834 uniA834 369;
            pos uniA835 uniA835 370;
        } kern_Nand;

        lookup kern_Syrc {
            lookupflag IgnoreMarks;
            pos uni060C uni060C <17 0 17 0>;
            pos uni061B uni061B <18 0 18 0>;
            pos uni061F uni061F <19 0 19 0>;
            pos uni0640 uni0640 <20 0 20 0>;
            pos uni064B uni064B <21 0 21 0>;
            pos uni064C uni064C <22 0 22 0>;
            pos uni064D uni064D <23 0 23 0>;
            pos uni064E uni064E <24 0 24 0>;
            pos uni064F uni064F <25 0 25 0>;
            pos uni0650 uni0650 <26 0 26 0>;
            pos uni0651 uni0651 <27 0 27 0>;
            pos uni0652 uni0652 <28 0 28 0>;
            pos uni0653 uni0653 <29 0 29 0>;
            pos uni0654 uni0654 <30 0 30 0>;
            pos uni0655 uni0655 <31 0 31 0>;
            pos uni0670 uni0670 <32 0 32 0>;
            pos uni1DF8 uni1DF8 <88 0 88 0>;
            pos uni1DFA uni1DFA <89 0 89 0>;
        } kern_Syrc;

        lookup kern_Default {
            lookupflag IgnoreMarks;
            pos uni10100 uni10100 389;
            pos uni10101 uni10101 390;
            pos uni10102 uni10102 391;
            pos uni10107 uni10107 392;
            pos uni10108 uni10108 393;
            pos uni10109 uni10109 394;
            pos uni1010A uni1010A 395;
            pos uni1010B uni1010B 396;
            pos uni1010C uni1010C 397;
            pos uni1010D uni1010D 398;
            pos uni1010E uni1010E 399;
            pos uni1010F uni1010F 400;
            pos uni10110 uni10110 401;
            pos uni10111 uni10111 402;
            pos uni10112 uni10112 403;
            pos uni10113 uni10113 404;
            pos uni10114 uni10114 405;
            pos uni10115 uni10115 406;
            pos uni10116 uni10116 407;
            pos uni10117 uni10117 408;
            pos uni10118 uni10118 409;
            pos uni10119 uni10119 410;
            pos uni1011A uni1011A 411;
            pos uni1011B uni1011B 412;
            pos uni1011C uni1011C 413;
            pos uni1011D uni1011D 414;
            pos uni1011E uni1011E 415;
            pos uni1011F uni1011F 416;
            pos uni10120 uni10120 417;
            pos uni10121 uni10121 418;
            pos uni10122 uni10122 419;
            pos uni10123 uni10123 420;
            pos uni10124 uni10124 421;
            pos uni10125 uni10125 422;
            pos uni10126 uni10126 423;
            pos uni10127 uni10127 424;
            pos uni10128 uni10128 425;
            pos uni10129 uni10129 426;
            pos uni1012A uni1012A 427;
            pos uni1012B uni1012B 428;
            pos uni1012C uni1012C 429;
            pos uni1012D uni1012D 430;
            pos uni1012E uni1012E 431;
            pos uni1012F uni1012F 432;
            pos uni10130 uni10130 433;
            pos uni10131 uni10131 434;
            pos uni10132 uni10132 435;
            pos uni10133 uni10133 436;
            pos uni10137 uni10137 437;
            pos uni10138 uni10138 438;
            pos uni10139 uni10139 439;
            pos uni1013A uni1013A 440;
            pos uni1013B uni1013B 441;
            pos uni1013C uni1013C 442;
            pos uni1013D uni1013D 443;
            pos uni1013E uni1013E 444;
            pos uni1013F uni1013F 445;
            pos uni102E0 uni102E0 446;
            pos uni102E1 uni102E1 447;
            pos uni102E2 uni102E2 448;
            pos uni102E3 uni102E3 449;
            pos uni102E4 uni102E4 450;
            pos uni102E5 uni102E5 451;
            pos uni102E6 uni102E6 452;
            pos uni102E7 uni102E7 453;
            pos uni102E8 uni102E8 454;
            pos uni102E9 uni102E9 455;
            pos uni102EA uni102EA 456;
            pos uni102EB uni102EB 457;
            pos uni102EC uni102EC 458;
            pos uni102ED uni102ED 459;
            pos uni102EE uni102EE 460;
            pos uni102EF uni102EF 461;
            pos uni102F0 uni102F0 462;
            pos uni102F1 uni102F1 463;
            pos uni102F2 uni102F2 464;
            pos uni102F3 uni102F3 465;
            pos uni102F4 uni102F4 466;
            pos uni102F5 uni102F5 467;
            pos uni102F6 uni102F6 468;
            pos uni102F7 uni102F7 469;
            pos uni102F8 uni102F8 470;
            pos uni102F9 uni102F9 471;
            pos uni102FA uni102FA 472;
            pos uni102FB uni102FB 473;
            pos uni1133B uni1133B 474;
            pos uni1735 uni1735 38;
            pos uni1736 uni1736 39;
            pos uni1802 uni1802 40;
            pos uni1803 uni1803 41;
            pos uni1805 uni1805 42;
            pos uni2E43 uni2E43 92;
            pos uni3031 uni3031 125;
            pos uni3032 uni3032 126;
            pos uni3033 uni3033 127;
            pos uni3034 uni3034 128;
            pos uni3035 uni3035 129;
            pos uni3099 uni3099 135;
            pos uni309A uni309A 136;
            pos uni309B uni309B 137;
            pos uni309C uni309C 138;
            pos uni30A0 uni30A0 139;
            pos uni30FC uni30FC 141;
            pos uniA9CF uniA9CF 376;
            pos uniFD3E uniFD3E 377;
            pos uniFD3F uniFD3F 378;
            pos uniFF70 uniFF70 386;
            pos uniFF9E uniFF9E 387;
            pos uniFF9F uniFF9F 388;
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

            script latn;
            language dflt;
            lookup kern_Default;
            lookup kern_Latn;

            script syrc;
            language dflt;
            lookup kern_Default;
            lookup kern_Syrc;
        } kern;

        feature dist {
            script bng2;
            language dflt;
            lookup kern_Default;
            lookup kern_Beng;

            script beng;
            language dflt;
            lookup kern_Default;
            lookup kern_Beng;

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

            script nand;
            language dflt;
            lookup kern_Default;
            lookup kern_Nand;
        } dist;
        """
    )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main(sys.argv))
