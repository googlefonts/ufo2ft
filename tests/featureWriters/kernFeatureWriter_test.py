import logging
from textwrap import dedent

import pytest

from ufo2ft.errors import InvalidFeaturesData
from ufo2ft.featureCompiler import parseLayoutFeatures
from ufo2ft.featureWriters import KernFeatureWriter, ast
from ufo2ft.featureWriters.kernFeatureWriter import KerningPair

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

    def test_split_pair(self, caplog):
        caplog.set_level(logging.INFO)
        glyphScripts = {
            "V": {"Latn"},
            "W": {"Latn"},
            "gba-nko": {"Nkoo"},
            "period": {"Zyyy"},
            "comma-ar": {"Arab", "Nkoo", "Syrc", "Thaa", "Rohg", "Yezi"},
            "lam-ar": {"Arab"},
        }

        # Mixed script pairs don't go anywhere
        pair = KerningPair(["V", "W"], ["gba-nko", "W"], -20)
        split = dict(pair.partitionByScript(glyphScripts))
        assert len(split) == 1
        assert str(split["Latn"]) == "<KerningPair [V W] W -20 {'Latn'}>"
        assert (
            "Mixed script kerning pair <KerningPair [V W] gba-nko -20> ignored"
            in caplog.text
        )

        # Everyone gets common-script glyphs, but they get it per-script
        pair = KerningPair(["V", "gba-nko", "W"], "period", -20)
        split = dict(pair.partitionByScript(glyphScripts))
        assert len(split) == 2
        assert "Latn" in split and "Nkoo" in split
        assert str(split["Latn"]) == "<KerningPair [V W] period -20 {'Latn'}>"
        assert str(split["Nkoo"]) == "<KerningPair gba-nko period -20 {'Nkoo'}>"

        # But if both sides are common then the output is common
        pair = KerningPair("period", "period", -20)
        split = dict(pair.partitionByScript(glyphScripts))
        assert len(split) == 1
        assert "Zyyy" in split

        # Glyphs with more than one script get associated with all of the
        # relevant scripts in the pair
        pair = KerningPair(["lam-ar", "gba-nko"], ["comma-ar"], -20)
        split = dict(pair.partitionByScript(glyphScripts))
        assert len(split) == 2
        assert "Arab" in split and "Nkoo" in split
        assert str(split["Arab"]) == "<KerningPair lam-ar comma-ar -20 {'Arab'}>"
        assert str(split["Nkoo"]) == "<KerningPair gba-nko comma-ar -20 {'Nkoo'}>"

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
        assert classDefs[0].name == "kern1.A"
        assert classDefs[1].name == "kern2.B"
        assert getGlyphs(classDefs[0]) == ["A", "Aacute", "Acircumflex"]
        assert getGlyphs(classDefs[1]) == ["B", "E", "F"]

        lookups = getLookups(feaFile)
        assert len(lookups) == 1
        kern_lookup = lookups[0]
        # We have no codepoints defined for these, so they're considered common
        assert kern_lookup.name == "kern_Common"
        rules = getPairPosRules(kern_lookup)
        assert len(rules) == 1
        assert str(rules[0]) == "pos @kern1.A @kern2.B 10;"

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
            lookup kern_Common {
                lookupflag IgnoreMarks;
                pos four six -55;
                pos one six -30;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;
            } kern;
            """
        )

        writer = KernFeatureWriter(ignoreMarks=False)
        feaFile = ast.FeatureFile()
        assert writer.write(font, feaFile)

        assert str(feaFile) == dedent(
            """\
            lookup kern_Common {
                pos four six -55;
                pos one six -30;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;
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
        # Zyyy because no languagesystems defined
        assert str(feaFile) == dedent(
            """
            lookup kern_Common {
                lookupflag IgnoreMarks;
                pos B C -30;
            } kern_Common;

            lookup kern_Common_marks {
                pos A acutecomb -55;
            } kern_Common_marks;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;
                lookup kern_Common_marks;
            } kern;
            """
        )

        feaFile = self.writeFeatures(font, ignoreMarks=False)
        assert str(feaFile) == dedent(
            """
            lookup kern_Common {
                pos A acutecomb -55;
                pos B C -30;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;
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
            lookup kern_Common_marks {
                pos A acutecomb -55;
            } kern_Common_marks;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common_marks;
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

            lookup kern_Common {
                lookupflag IgnoreMarks;
                pos seven six 25;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;
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
            lookup kern_Common {
                lookupflag IgnoreMarks;
                pos seven six 25;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;
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
            lookup kern_Common {
                lookupflag IgnoreMarks;
                pos seven six 25;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;
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
            lookup kern_Common {
                lookupflag IgnoreMarks;
                pos seven six 25;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;
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


            lookup kern_Common {
                lookupflag IgnoreMarks;
                pos seven six 25;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;
            } kern;
            """
        )

        assert str(feaFile) == expected

        # test append mode ignores insert marker
        generated = self.writeFeatures(ufo, mode="append")
        assert str(generated) == dedent(
            """
            lookup kern_Common {
                lookupflag IgnoreMarks;
                pos seven six 25;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;
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
            lookup kern_Common {
                lookupflag IgnoreMarks;
                pos seven six 25;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;
            } kern;
            """
        )

    def test_arabic_numerals(self, FontClass):
        """Test that arabic numerals (with bidi type AN) are kerned LTR.
        https://github.com/googlei18n/ufo2ft/issues/198
        https://github.com/googlei18n/ufo2ft/pull/200
        """
        ufo = FontClass()
        for name, code in [("four-ar", 0x664), ("seven-ar", 0x667)]:
            glyph = ufo.newGlyph(name)
            glyph.unicode = code
        ufo.kerning.update({("four-ar", "seven-ar"): -30})
        ufo.features.text = dedent(
            """
            languagesystem DFLT dflt;
            languagesystem arab dflt;
            """
        )

        generated = self.writeFeatures(ufo)

        assert dedent(str(generated)) == dedent(
            """
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

    def test__groupScriptsByTagAndDirection(self, FontClass):
        font = FontClass()
        font.features.text = dedent(
            """
            languagesystem DFLT dflt;
            languagesystem latn dflt;
            languagesystem latn TRK;
            languagesystem arab dflt;
            languagesystem arab URD;
            languagesystem deva dflt;
            languagesystem dev2 dflt;
            languagesystem math dflt;
            """
        )

        feaFile = parseLayoutFeatures(font)
        scripts = ast.getScriptLanguageSystems(feaFile)
        scriptGroups = KernFeatureWriter._groupScriptsByTagAndDirection(scripts)

        assert "kern" in scriptGroups
        assert list(scriptGroups["kern"]["LTR"]) == [
            ("latn", ["dflt", "TRK "]),
            ("math", ["dflt"]),
        ]
        assert list(scriptGroups["kern"]["RTL"]) == [("arab", ["dflt", "URD "])]

        assert "dist" in scriptGroups
        assert list(scriptGroups["dist"]["LTR"]) == [
            ("deva", ["dflt"]),
            ("dev2", ["dflt"]),
        ]

    def test_getKerningClasses(self, FontClass):
        font = FontClass()
        for i in range(65, 65 + 6):  # A..F
            font.newGlyph(chr(i))
        font.groups.update({"public.kern1.A": ["A", "B"], "public.kern2.C": ["C", "D"]})
        # simulate a name clash between pre-existing class definitions in
        # feature file, and those generated by the feature writer
        font.features.text = "@kern1.A = [E F];"

        feaFile = parseLayoutFeatures(font)
        side1Classes, side2Classes = KernFeatureWriter.getKerningClasses(font, feaFile)

        assert "public.kern1.A" in side1Classes
        # the new class gets a unique name
        assert side1Classes["public.kern1.A"].name == "kern1.A_1"
        assert getGlyphs(side1Classes["public.kern1.A"]) == ["A", "B"]

        assert "public.kern2.C" in side2Classes
        assert side2Classes["public.kern2.C"].name == "kern2.C"
        assert getGlyphs(side2Classes["public.kern2.C"]) == ["C", "D"]

    def test_correct_invalid_class_names(self, FontClass):
        font = FontClass()
        for i in range(65, 65 + 12):  # A..L
            font.newGlyph(chr(i))
        font.groups.update(
            {
                "public.kern1.foo$": ["A", "B", "C"],
                "public.kern1.foo@": ["D", "E", "F"],
                "@public.kern2.bar": ["G", "H", "I"],
                "public.kern2.bar&": ["J", "K", "L"],
            }
        )
        font.kerning.update(
            {
                ("public.kern1.foo$", "@public.kern2.bar"): 10,
                ("public.kern1.foo@", "public.kern2.bar&"): -10,
            }
        )

        side1Classes, side2Classes = KernFeatureWriter.getKerningClasses(font)

        assert side1Classes["public.kern1.foo$"].name == "kern1.foo"
        assert side1Classes["public.kern1.foo@"].name == "kern1.foo_1"
        # no valid 'public.kern{1,2}.' prefix, skipped
        assert "@public.kern2.bar" not in side2Classes
        assert side2Classes["public.kern2.bar&"].name == "kern2.bar"

    def test_getKerningPairs(self, FontClass):
        font = FontClass()
        for i in range(65, 65 + 8):  # A..H
            font.newGlyph(chr(i))
        font.groups.update(
            {
                "public.kern1.foo": ["A", "B"],
                "public.kern2.bar": ["C", "D"],
                "public.kern1.baz": ["E", "F"],
                "public.kern2.nul": ["G", "H"],
            }
        )
        font.kerning.update(
            {
                ("public.kern1.foo", "public.kern2.bar"): 10,
                ("public.kern1.baz", "public.kern2.bar"): -10,
                ("public.kern1.foo", "D"): 15,
                ("A", "public.kern2.bar"): 5,
                ("G", "H"): -5,
                # class-class zero-value pairs are skipped
                ("public.kern1.foo", "public.kern2.nul"): 0,
            }
        )

        s1c, s2c = KernFeatureWriter.getKerningClasses(font)
        pairs = KernFeatureWriter.getKerningPairs(font, s1c, s2c)
        assert len(pairs) == 5

        assert "G H -5" in repr(pairs[0])
        assert (pairs[0].firstIsClass, pairs[0].secondIsClass) == (False, False)
        assert pairs[0].glyphs == {"G", "H"}

        assert "A @kern2.bar 5" in repr(pairs[1])
        assert (pairs[1].firstIsClass, pairs[1].secondIsClass) == (False, True)
        assert pairs[1].glyphs == {"A", "C", "D"}

        assert "@kern1.foo D 15" in repr(pairs[2])
        assert (pairs[2].firstIsClass, pairs[2].secondIsClass) == (True, False)
        assert pairs[2].glyphs == {"A", "B", "D"}

        assert "@kern1.baz @kern2.bar -10" in repr(pairs[3])
        assert (pairs[3].firstIsClass, pairs[3].secondIsClass) == (True, True)
        assert pairs[3].glyphs == {"C", "D", "E", "F"}

        assert "@kern1.foo @kern2.bar 10" in repr(pairs[4])
        assert (pairs[4].firstIsClass, pairs[4].secondIsClass) == (True, True)
        assert pairs[4].glyphs == {"A", "B", "C", "D"}

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
            @kern1.A = [A Aacute];
            @kern1.reh = [reh-ar zain-ar reh-ar.fina];
            @kern2.alef = [alef-ar alef-ar.isol];

            lookup kern_Arab {
                pos four-ar seven-ar -30;
                pos reh-ar.fina lam-ar.init <-80 0 -80 0>;
                pos @kern1.reh @kern2.alef <-100 0 -100 0>;
            } kern_Arab;

            lookup kern_Latn {
                enum pos @kern1.A V -40;
            } kern_Latn;

            lookup kern_Common {
                pos seven four -25;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;

                script arab;
                language dflt;
                lookup kern_Common;
                lookup kern_Arab;
                language URD;

                script latn;
                language dflt;
                lookup kern_Common;
                lookup kern_Latn;
                language TRK;
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

        assert dedent(str(newFeatures)) == dedent(
            """\
            @kern1.A = [A Aacute];
            @kern1.reh = [reh-ar zain-ar reh-ar.fina];
            @kern2.alef = [alef-ar alef-ar.isol];

            lookup kern_Arab {
                lookupflag IgnoreMarks;
                pos four-ar seven-ar -30;
                pos reh-ar.fina lam-ar.init <-80 0 -80 0>;
                pos @kern1.reh @kern2.alef <-100 0 -100 0>;
            } kern_Arab;

            lookup kern_Arab_marks {
                pos reh-ar fatha-ar <80 0 80 0>;
            } kern_Arab_marks;

            lookup kern_Latn {
                lookupflag IgnoreMarks;
                enum pos @kern1.A V -40;
            } kern_Latn;

            lookup kern_Latn_marks {
                pos V acutecomb 70;
            } kern_Latn_marks;

            lookup kern_Common {
                lookupflag IgnoreMarks;
                pos seven four -25;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;

                script arab;
                language dflt;
                lookup kern_Common;
                lookup kern_Arab;
                lookup kern_Arab_marks;
                language URD;

                script latn;
                language dflt;
                lookup kern_Common;
                lookup kern_Latn;
                lookup kern_Latn_marks;
                language TRK;
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

        assert dedent(str(newFeatures)) == dedent(
            """\
            @kern1.reh = [reh-ar zain-ar reh-ar.fina];
            @kern2.alef = [alef-ar alef-ar.isol];

            lookup kern_Arab {
                lookupflag IgnoreMarks;
                pos reh-ar.fina lam-ar.init <-80 0 -80 0>;
                pos @kern1.reh @kern2.alef <-100 0 -100 0>;
            } kern_Arab;

            lookup kern_Arab_marks {
                pos reh-ar fatha-ar <80 0 80 0>;
            } kern_Arab_marks;

            feature kern {
                script arab;
                language dflt;
                lookup kern_Arab;
                lookup kern_Arab_marks;
                language ARA;
            } kern;
            """
        )

    def test_kern_LTR_and_RTL_one_uses_DFLT(self, FontClass):
        glyphs = {"A": 0x41, "V": 0x56, "reh-ar": 0x631, "alef-ar": 0x627}
        kerning = {("A", "V"): -40, ("reh-ar", "alef-ar"): -100}
        features = "languagesystem latn dflt;"
        ufo = makeUFO(FontClass, glyphs, kerning=kerning, features=features)
        generated = self.writeFeatures(ufo)

        assert dedent(str(generated)) == dedent(
            """
            lookup kern_Latn {
                lookupflag IgnoreMarks;
                pos A V -40;
            } kern_Latn;

            lookup kern_Common {
                lookupflag IgnoreMarks;
                pos reh-ar alef-ar <-100 0 -100 0>;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;

                script latn;
                language dflt;
                lookup kern_Common;
                lookup kern_Latn;
            } kern;
            """
        )

        features = dedent("languagesystem arab dflt;")
        ufo = makeUFO(FontClass, glyphs, kerning=kerning, features=features)
        generated = self.writeFeatures(ufo)

        assert dedent(str(generated)) == dedent(
            """
            lookup kern_Arab {
                lookupflag IgnoreMarks;
                pos reh-ar alef-ar <-100 0 -100 0>;
            } kern_Arab;

            lookup kern_Common {
                lookupflag IgnoreMarks;
                pos A V -40;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;

                script arab;
                language dflt;
                lookup kern_Common;
                lookup kern_Arab;
            } kern;
            """
        )

    def test_kern_LTR_and_RTL_no_DFLT(self, FontClass):
        glyphs = {"A": 0x41, "V": 0x56, "reh-ar": 0x631, "alef-ar": 0x627}
        kerning = {("A", "V"): -40, ("reh-ar", "alef-ar"): -100}
        ufo = makeUFO(FontClass, glyphs, kerning=kerning)
        generated = self.writeFeatures(ufo)
        assert "\n" + str(generated) == dedent(
            """
            lookup kern_Common {
                lookupflag IgnoreMarks;
                pos A V -40;
                pos reh-ar alef-ar <-100 0 -100 0>;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;
            } kern;
            """
        )

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
            @kern1.KND_aaMatra_R = [aaMatra_kannada];
            @kern2.KND_ailength_L = [aaMatra_kannada];

            lookup kern_Knda {
                lookupflag IgnoreMarks;
                pos @kern1.KND_aaMatra_R @kern2.KND_ailength_L 34;
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

        assert dedent(str(generated)) == dedent(
            """\
            @kern1.KND_aaMatra_R = [aaMatra_kannada];
            @kern2.KND_ailength_L = [aaMatra_kannada];

            lookup kern_Khar {
                lookupflag IgnoreMarks;
                pos u10A1E u10A06 <117 0 117 0>;
            } kern_Khar;

            lookup kern_Knda {
                lookupflag IgnoreMarks;
                pos @kern1.KND_aaMatra_R @kern2.KND_ailength_L 34;
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

        logger = "ufo2ft.featureWriters.kernFeatureWriter.KernFeatureWriter"
        with caplog.at_level(logging.WARNING, logger=logger):
            generated = self.writeFeatures(ufo)

        assert dedent(str(generated)) == dedent(
            """
            lookup kern_Arab {
                lookupflag IgnoreMarks;
                pos bar bar 1;
                pos reh-ar one-ar 4;
            } kern_Arab;

            lookup kern_Latn {
                lookupflag IgnoreMarks;
                pos bar A 2;
                pos bar bar 1;
            } kern_Latn;

            lookup kern_Common {
                lookupflag IgnoreMarks;
                pos yod-hb one 5;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;

                script arab;
                language dflt;
                lookup kern_Common;
                lookup kern_Arab;

                script latn;
                language dflt;
                lookup kern_Common;
                lookup kern_Latn;
            } kern;
        """
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

            lookup kern_Common {
                lookupflag IgnoreMarks;
                pos seven four -25;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;

                script hebr;
                language dflt;
                lookup kern_Common;
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
            lookup kern_Common {
                lookupflag IgnoreMarks;
                pos four six -55;
                pos one six -25;
            } kern_Common;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Common;
            } kern;
            """
        )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main(sys.argv))
