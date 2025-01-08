import logging

import fontTools.feaLib.ast as fea_ast
import pytest
from fontTools import unicodedata
from syrupy.extensions.amber import AmberSnapshotExtension
from syrupy.location import PyTestLocation
from syrupy.types import SnapshotIndex

from ufo2ft.constants import UNICODE_SCRIPT_ALIASES
from ufo2ft.featureCompiler import FeatureCompiler, parseLayoutFeatures
from ufo2ft.featureWriters.kernFeatureWriter2 import KernFeatureWriter
from ufo2ft.util import DFLT_SCRIPTS, unicodeScriptExtensions

from . import FeatureWriterTest


class KernFeatureWriterTest(FeatureWriterTest):
    FeatureWriter = KernFeatureWriter


class SameUfoLibResultsExtension(AmberSnapshotExtension):
    """Make tests use the same snapshots when parameterized.

    Instead of having the snapshots of "test_something[defcon]" and
    "test_something[ufoLib2]" be duplicates, use the same snapshots for both,
    because the UFO library shouldn't make a difference.
    """

    @classmethod
    def get_snapshot_name(
        cls, *, test_location: "PyTestLocation", index: "SnapshotIndex"
    ) -> str:
        index_suffix = ""
        if isinstance(index, (str,)):
            index_suffix = f"[{index}]"
        elif index:
            index_suffix = f".{index}"
        return f"{test_location.methodname}{index_suffix}"


@pytest.fixture
def snapshot(snapshot):
    return snapshot.use_extension(SameUfoLibResultsExtension)


def makeUFO(cls, glyphMap, groups=None, kerning=None, features=None):
    ufo = cls()
    for name, uni in glyphMap.items():
        glyph = ufo.newGlyph(name)
        if isinstance(uni, (list, tuple)):
            glyph.unicodes = uni
        elif uni is not None:
            glyph.unicode = uni
    if groups is not None:
        ufo.groups.update(groups)
    if kerning is not None:
        ufo.kerning.update(kerning)
    if features is not None:
        ufo.features.text = features
    return ufo


def getClassDefs(feaFile):
    return [
        s for s in feaFile.statements if isinstance(s, fea_ast.GlyphClassDefinition)
    ]


def getGlyphs(classDef):
    return [str(g) for g in classDef.glyphs.glyphSet()]


def getLookups(feaFile):
    return [s for s in feaFile.statements if isinstance(s, fea_ast.LookupBlock)]


def getPairPosRules(lookup):
    return [s for s in lookup.statements if isinstance(s, fea_ast.PairPosStatement)]


def test_cleanup_missing_glyphs(FontClass):
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
    assert classDefs[0].name == "kern1.dflt.A"
    assert classDefs[1].name == "kern2.dflt.B"
    assert getGlyphs(classDefs[0]) == ["A", "Aacute", "Acircumflex"]
    assert getGlyphs(classDefs[1]) == ["B", "E", "F"]

    lookups = getLookups(feaFile)
    assert len(lookups) == 1
    kern_lookup = lookups[0]
    # We have no codepoints defined for these, so they're considered common
    assert kern_lookup.name == "kern_dflt"
    rules = getPairPosRules(kern_lookup)
    assert len(rules) == 1
    assert str(rules[0]) == "pos @kern1.dflt.A @kern2.dflt.B 10;"


def test_ignoreMarks(snapshot, FontClass):
    font = FontClass()
    for name in ("one", "four", "six"):
        font.newGlyph(name)
    font.kerning.update({("four", "six"): -55.0, ("one", "six"): -30.0})
    # default is ignoreMarks=True
    writer = KernFeatureWriter()
    feaFile = fea_ast.FeatureFile()
    assert writer.write(font, feaFile)

    assert feaFile.asFea() == snapshot

    writer = KernFeatureWriter(ignoreMarks=False)
    feaFile = fea_ast.FeatureFile()
    assert writer.write(font, feaFile)

    assert feaFile.asFea() == snapshot


def test_mark_to_base_kern(snapshot, FontClass):
    font = FontClass()
    for name in ("A", "B", "C"):
        font.newGlyph(name).unicode = ord(name)
    font.newGlyph("acutecomb").unicode = 0x0301
    font.kerning.update({("A", "acutecomb"): -55.0, ("B", "C"): -30.0})

    font.features.text = """\
        @Bases = [A B C];
        @Marks = [acutecomb];
        table GDEF {
            GlyphClassDef @Bases, [], @Marks, ;
        } GDEF;
        """

    # default is ignoreMarks=True
    feaFile = KernFeatureWriterTest.writeFeatures(font)
    assert feaFile.asFea() == snapshot

    feaFile = KernFeatureWriterTest.writeFeatures(font, ignoreMarks=False)
    assert feaFile.asFea() == snapshot


def test_mark_to_base_only(snapshot, FontClass):
    font = FontClass()
    for name in ("A", "B", "C"):
        font.newGlyph(name)
    font.newGlyph("acutecomb").unicode = 0x0301
    font.kerning.update({("A", "acutecomb"): -55.0})

    font.features.text = """\
        @Bases = [A B C];
        @Marks = [acutecomb];
        table GDEF {
            GlyphClassDef @Bases, [], @Marks, ;
        } GDEF;
        """

    # default is ignoreMarks=True
    feaFile = KernFeatureWriterTest.writeFeatures(font)
    assert feaFile.asFea() == snapshot


def test_mode(snapshot, FontClass):
    ufo = FontClass()
    for name in ("one", "four", "six", "seven"):
        ufo.newGlyph(name)
    existing = """\
        feature kern {
            pos one four' -50 six;
        } kern;
        """
    ufo.features.text = existing
    ufo.kerning.update({("seven", "six"): 25.0})

    writer = KernFeatureWriter()  # default mode="skip"
    feaFile = parseLayoutFeatures(ufo)
    assert not writer.write(ufo, feaFile)

    assert str(feaFile) == snapshot(name="existing")

    # pass optional "append" mode
    writer = KernFeatureWriter(mode="append")
    feaFile = parseLayoutFeatures(ufo)
    assert writer.write(ufo, feaFile)

    assert feaFile.asFea() == snapshot

    # pass "skip" mode explicitly
    writer = KernFeatureWriter(mode="skip")
    feaFile = parseLayoutFeatures(ufo)
    assert not writer.write(ufo, feaFile)

    assert feaFile.asFea() == snapshot(name="existing")


def test_insert_comment_before(snapshot, FontClass):
    ufo = FontClass()
    for name in ("one", "four", "six", "seven"):
        ufo.newGlyph(name)
    existing = """\
        feature kern {
            #
            # Automatic Code
            #
            pos one four' -50 six;
        } kern;
        """
    ufo.features.text = existing
    ufo.kerning.update({("seven", "six"): 25.0})

    writer = KernFeatureWriter()
    feaFile = parseLayoutFeatures(ufo)
    assert writer.write(ufo, feaFile)

    assert feaFile.asFea() == snapshot

    # test append mode ignores insert marker
    generated = KernFeatureWriterTest.writeFeatures(ufo, mode="append")
    assert generated.asFea() == snapshot


def test_comment_wrong_case_or_missing(snapshot, FontClass, caplog):
    ufo = FontClass()
    for name in ("a", "b"):
        ufo.newGlyph(name)
    ufo.kerning.update({("a", "b"): 25.0})
    ufo.features.text = (
        """
        feature kern {
            # Automatic code
        } kern;
        """
    ).strip()

    with caplog.at_level(logging.WARNING):
        compiler = FeatureCompiler(ufo, featureWriters=[KernFeatureWriter])
        font = compiler.compile()

    # We mis-cased the insertion marker above, so it's ignored and we end up
    # with an empty `kern` block overriding the other kerning in the font
    # source and therefore no `GPOS` table.
    assert "miscased" in caplog.text
    assert "Dropping the former" in caplog.text
    assert "GPOS" not in font

    # Append mode ignores insertion markers and so should not log warnings
    # and have kerning in the final font.
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        compiler = FeatureCompiler(
            ufo, featureWriters=[KernFeatureWriter(mode="append")]
        )
        font = compiler.compile()

    assert not caplog.text
    assert "GPOS" in font


def test_insert_comment_before_extended(snapshot, FontClass):
    ufo = FontClass()
    for name in ("one", "four", "six", "seven"):
        ufo.newGlyph(name)
    existing = """\
        feature kern {
            #
            # Automatic Code End
            #
            pos one four' -50 six;
        } kern;
        """
    ufo.features.text = existing
    ufo.kerning.update({("seven", "six"): 25.0})

    writer = KernFeatureWriter()
    feaFile = parseLayoutFeatures(ufo)
    assert writer.write(ufo, feaFile)

    assert feaFile.asFea() == snapshot


def test_insert_comment_after(snapshot, FontClass):
    ufo = FontClass()
    for name in ("one", "four", "six", "seven"):
        ufo.newGlyph(name)
    existing = """\
        feature kern {
            pos one four' -50 six;
            #
            # Automatic Code
            #
        } kern;
        """
    ufo.features.text = existing
    ufo.kerning.update({("seven", "six"): 25.0})

    writer = KernFeatureWriter()
    feaFile = parseLayoutFeatures(ufo)
    assert writer.write(ufo, feaFile)

    assert feaFile.asFea() == snapshot

    # test append mode ignores insert marker
    generated = KernFeatureWriterTest.writeFeatures(ufo, mode="append")
    assert generated.asFea() == snapshot


def test_insert_comment_middle(snapshot, FontClass):
    ufo = FontClass()
    for name in ("one", "four", "six", "seven"):
        ufo.newGlyph(name)
    existing = """\
        feature kern {
            pos one four' -50 six;
            #
            # Automatic Code
            #
            pos one six' -50 six;
        } kern;
        """
    ufo.features.text = existing
    ufo.kerning.update({("seven", "six"): 25.0})

    writer = KernFeatureWriter()
    feaFile = parseLayoutFeatures(ufo)

    writer.write(ufo, feaFile)
    assert str(feaFile) == snapshot

    # test append mode ignores insert marker
    generated = KernFeatureWriterTest.writeFeatures(ufo, mode="append")
    assert generated.asFea() == snapshot


def test_arabic_numerals(snapshot, FontClass):
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

    generated = KernFeatureWriterTest.writeFeatures(ufo)

    assert generated.asFea() == snapshot

    ufo.newGlyph("alef-ar").unicode = 0x627
    generated = KernFeatureWriterTest.writeFeatures(ufo)

    assert generated.asFea() == snapshot

    ufo.features.text = """
        languagesystem DFLT dflt;
        languagesystem Thaa dflt;
    """
    generated = KernFeatureWriterTest.writeFeatures(ufo)

    assert generated.asFea() == snapshot

    del ufo["alef-ar"]
    generated = KernFeatureWriterTest.writeFeatures(ufo)

    assert generated.asFea() == snapshot


def test_skip_zero_class_kerns(snapshot, FontClass):
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

    ufo = makeUFO(FontClass, glyphs, groups, kerning)
    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert newFeatures.asFea() == snapshot


def test_kern_uniqueness(snapshot, FontClass):
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

    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    # The final kerning value for questiondown, y is 35 and all variants
    # must be present. Ensures the uniqueness filter doesn't filter things
    # out.
    assert newFeatures.asFea() == snapshot


def test_kern_LTR_and_RTL(snapshot, FontClass):
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
    features = """\
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

    ufo = makeUFO(FontClass, glyphs, groups, kerning, features)

    newFeatures = KernFeatureWriterTest.writeFeatures(ufo, ignoreMarks=False)

    assert newFeatures.asFea() == snapshot


def test_kern_LTR_and_RTL_with_marks(snapshot, FontClass):
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
    features = """\
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

    ufo = makeUFO(FontClass, glyphs, groups, kerning, features)

    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert newFeatures.asFea() == snapshot


def test_kern_RTL_with_marks(snapshot, FontClass):
    glyphs = {
        ".notdef": None,
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
        "public.kern1.reh": ["reh-ar", "zain-ar", "reh-ar.fina"],
        "public.kern2.alef": ["alef-ar", "alef-ar.isol"],
    }
    kerning = {
        ("reh-ar.fina", "lam-ar.init"): -80,
        ("public.kern1.reh", "public.kern2.alef"): -100,
        ("reh-ar", "fatha-ar"): 80,
    }
    features = """\
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

    ufo = makeUFO(FontClass, glyphs, groups, kerning, features)

    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)
    assert newFeatures.asFea() == snapshot


def test_kern_independent_of_languagesystem(snapshot, FontClass):
    glyphs = {"A": 0x41, "V": 0x56, "reh-ar": 0x631, "alef-ar": 0x627}
    kerning = {("A", "V"): -40, ("reh-ar", "alef-ar"): -100}
    # No languagesystems declared.
    ufo = makeUFO(FontClass, glyphs, kerning=kerning)
    generated = KernFeatureWriterTest.writeFeatures(ufo)

    assert generated.asFea() == snapshot(name="same")

    features = "languagesystem arab dflt;"
    ufo = makeUFO(FontClass, glyphs, kerning=kerning, features=features)
    generated = KernFeatureWriterTest.writeFeatures(ufo)

    assert generated.asFea() == snapshot(name="same")


def test_dist_LTR(snapshot, FontClass):
    glyphs = {"aaMatra_kannada": 0x0CBE, "ailength_kannada": 0xCD6}
    groups = {
        "public.kern1.KND_aaMatra_R": ["aaMatra_kannada"],
        "public.kern2.KND_ailength_L": ["aaMatra_kannada"],
    }
    kerning = {("public.kern1.KND_aaMatra_R", "public.kern2.KND_ailength_L"): 34}
    features = """\
        languagesystem DFLT dflt;
        languagesystem latn dflt;
        languagesystem knda dflt;
        languagesystem knd2 dflt;
        """

    ufo = makeUFO(FontClass, glyphs, groups, kerning, features)
    generated = KernFeatureWriterTest.writeFeatures(ufo)

    assert generated.asFea() == snapshot


def test_dist_RTL(snapshot, FontClass):
    glyphs = {"u10A06": 0x10A06, "u10A1E": 0x10A1E}
    kerning = {("u10A1E", "u10A06"): 117}
    features = """\
        languagesystem DFLT dflt;
        languagesystem arab dflt;
        languagesystem khar dflt;
        """

    ufo = makeUFO(FontClass, glyphs, kerning=kerning, features=features)
    generated = KernFeatureWriterTest.writeFeatures(ufo)

    assert generated.asFea() == snapshot


def test_dist_LTR_and_RTL(snapshot, FontClass):
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
    features = """\
            languagesystem DFLT dflt;
            languagesystem knda dflt;
            languagesystem knd2 dflt;
            languagesystem khar dflt;
            """

    ufo = makeUFO(FontClass, glyphs, groups, kerning, features)
    generated = KernFeatureWriterTest.writeFeatures(ufo)

    assert generated.asFea() == snapshot


def test_ambiguous_direction_pair(snapshot, FontClass, caplog):
    """Test that glyphs with ambiguous BiDi classes get split correctly."""

    glyphs = {
        "A": 0x0041,
        "one": 0x0031,
        "yod-hb": 0x05D9,
        "reh-ar": 0x0631,
        "one-ar": 0x0661,
        "bar": [0x0073, 0x0627],
    }
    kerning = {
        ("bar", "bar"): 1,
        ("bar", "A"): 2,
        ("reh-ar", "A"): 3,
        ("reh-ar", "one-ar"): 4,
        ("yod-hb", "one"): 5,
    }
    features = """\
        languagesystem DFLT dflt;
        languagesystem latn dflt;
        languagesystem arab dflt;
        """
    ufo = makeUFO(FontClass, glyphs, kerning=kerning, features=features)

    with caplog.at_level(logging.INFO):
        generated = KernFeatureWriterTest.writeFeatures(ufo)

    assert generated.asFea() == snapshot
    assert caplog.messages == [
        "Skipping part of a kerning pair <bar bar 1> with mixed direction (LeftToRight, RightToLeft)",  # noqa: B950
        "Skipping part of a kerning pair <bar bar 1> with mixed direction (RightToLeft, LeftToRight)",  # noqa: B950
        "Skipping part of a kerning pair <bar A 2> with conflicting BiDi classes",  # noqa: B950
        "Skipping part of a kerning pair <bar A 2> with mixed direction (RightToLeft, LeftToRight)",  # noqa: B950
        "Skipping part of a kerning pair <reh-ar A 3> with mixed direction (RightToLeft, LeftToRight)",  # noqa: B950
        "Skipping part of a kerning pair <reh-ar one-ar 4> with conflicting BiDi classes",  # noqa: B950
        "Skipping part of a kerning pair <yod-hb one 5> with conflicting BiDi classes",  # noqa: B950
    ]


def test_kern_RTL_and_DFLT_numbers(snapshot, FontClass):
    glyphs = {"four": 0x34, "seven": 0x37, "bet-hb": 0x5D1, "yod-hb": 0x5D9}
    kerning = {("seven", "four"): -25, ("yod-hb", "bet-hb"): -100}
    features = """\
        languagesystem DFLT dflt;
        languagesystem hebr dflt;
        """

    ufo = makeUFO(FontClass, glyphs, kerning=kerning, features=features)
    generated = KernFeatureWriterTest.writeFeatures(ufo)

    assert generated.asFea() == snapshot


def test_quantize(snapshot, FontClass):
    font = FontClass()
    for name in ("one", "four", "six"):
        font.newGlyph(name)
    font.kerning.update({("four", "six"): -57.0, ("one", "six"): -24.0})
    writer = KernFeatureWriter(quantization=5)
    feaFile = fea_ast.FeatureFile()
    writer.write(font, feaFile)

    assert feaFile.asFea() == snapshot


def test_skip_spacing_marks(snapshot, data_dir, FontClass):
    fontPath = data_dir / "SpacingCombiningTest-Regular.ufo"
    testufo = FontClass(fontPath)
    generated = KernFeatureWriterTest.writeFeatures(testufo)

    assert generated.asFea() == snapshot


def test_kern_split_multi_glyph_class(snapshot, FontClass):
    """Test that kern pair types are correctly split across directions."""

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
        # Glyph-to-glyph
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

    ufo = makeUFO(FontClass, glyphs, groups, kerning)
    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert newFeatures.asFea() == snapshot(name="same")

    # Making a common glyph implicitly have an explicit script assigned (GSUB
    # closure) will still keep it in the common section.
    features = """
        feature ss01 {
            sub a by period; # Make period be both Latn and Zyyy.
        } ss01;
        """

    ufo = makeUFO(FontClass, glyphs, groups, kerning, features)
    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert newFeatures.asFea() == snapshot(name="same")


def test_kern_split_and_drop(snapshot, FontClass, caplog):
    """Test that mixed directions pairs are pruned and only the compatible parts
    are kept."""

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

    assert newFeatures.asFea() == snapshot
    assert caplog.messages == [
        "Skipping part of a kerning pair <('a', 'a-orya', 'alpha') ('alef-ar',) 20> with mixed direction (LeftToRight, RightToLeft)",  # noqa: B950
        "Skipping part of a kerning pair <('alef-ar',) ('a', 'a-orya', 'alpha') 20> with mixed direction (RightToLeft, LeftToRight)",  # noqa: B950
    ]


def test_kern_split_and_drop_mixed(snapshot, caplog, FontClass):
    """Test that mixed directions pairs are dropped.

    And that scripts with no remaining lookups don't crash.
    """

    glyphs = {"V": ord("V"), "W": ord("W"), "gba-nko": 0x07DC}
    groups = {"public.kern1.foo": ["V", "W"], "public.kern2.foo": ["gba-nko", "W"]}
    kerning = {("public.kern1.foo", "public.kern2.foo"): -20}
    ufo = makeUFO(FontClass, glyphs, groups, kerning)
    with caplog.at_level(logging.INFO):
        newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert newFeatures.asFea() == snapshot
    assert (
        "<('V', 'W') ('gba-nko',) -20> with mixed direction (LeftToRight, RightToLeft)"
        in caplog.text
    )


def test_kern_mixed_bidis(snapshot, caplog, FontClass):
    """Test that BiDi types for pairs are respected."""

    # TODO: Add Adlam numbers (rtl)
    glyphs = {
        "a": ord("a"),
        "comma": ord(","),
        "alef-ar": 0x0627,
        "comma-ar": 0x060C,
        "one-ar": 0x0661,
        "one-adlam": 0x1E951,
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
        ("one-adlam", "one-adlam"): 10,
        ("one-adlam", "comma-ar"): 11,
        ("comma-ar", "one-adlam"): 12,
        # Mixed: should be dropped
        ("alef-ar", "one-ar"): 7,
        ("one-ar", "alef-ar"): 8,
        ("one-ar", "one-adlam"): 13,
        # LTR despite being an RTL script
        ("one-ar", "one-ar"): 9,
    }
    ufo = makeUFO(FontClass, glyphs, None, kerning)
    with caplog.at_level(logging.INFO):
        newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert newFeatures.asFea() == snapshot
    assert "<alef-ar one-ar 7> with conflicting BiDi classes" in caplog.text
    assert "<one-ar alef-ar 8> with conflicting BiDi classes" in caplog.text
    assert "<one-ar one-adlam 13> with conflicting BiDi classes" in caplog.text


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


def test_kern_zyyy_zinh(snapshot, FontClass):
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

    assert newFeatures.asFea() == snapshot


def test_kern_hira_kana_hrkt(snapshot, FontClass):
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

    assert newFeatures.asFea() == snapshot


# TODO: Keep? Then modify comments.
def test_defining_classdefs(snapshot, FontClass):
    """Check that we aren't redefining class definitions with different
    content."""

    glyphs = {
        "halant-telugu": 0xC4D,  # Telu
        "ka-telugu.below": None,  # Telu by substitution
        "ka-telugu": 0xC15,  # Telu
        "rVocalicMatra-telugu": 0xC43,  # Telu
        "sha-telugu.below": None,  # Default
        "ss-telugu.alt": None,  # Default
        "ssa-telugu.alt": None,  # Telu by substitution
        "ssa-telugu": 0xC37,  # Telu
    }
    groups = {
        "public.kern1.sha-telugu.below": ["sha-telugu.below"],
        # The following group is a mix of Telu and Default through its gylphs. The
        # kerning for bases below will create a Telu and Default split group.
        # Important for the NOTE below.
        "public.kern1.ssa-telugu.alt": ["ssa-telugu.alt", "ss-telugu.alt"],
        "public.kern2.ka-telugu.below": ["ka-telugu.below"],
        "public.kern2.rVocalicMatra-telugu": ["rVocalicMatra-telugu"],
    }
    kerning = {
        # The follwoing three pairs are base-to-base pairs:
        ("public.kern1.sha-telugu.below", "public.kern2.ka-telugu.below"): 20,
        ("public.kern1.ssa-telugu.alt", "public.kern2.ka-telugu.below"): 60,
        ("public.kern1.ssa-telugu.alt", "sha-telugu.below"): 150,
        # NOTE: This last pair kerns bases against marks, triggering an extra
        # pass to make a mark lookup that will create new classDefs. This extra
        # pass will work on just this one pair, and kern splitting won't split
        # off a Default group from `public.kern1.ssa-telugu.alt`, you get just a
        # Telu pair. Unless the writer keeps track of which classDefs it already
        # generated, this will overwrite the previous `@kern1.Telu.ssatelugu.alt
        # = [ssa-telugu.alt]` with `@kern1.Telu.ssatelugu.alt =
        # [ss-telugu.alt]`, losing kerning.
        ("public.kern1.ssa-telugu.alt", "public.kern2.rVocalicMatra-telugu"): 180,
    }
    features = """
        feature blwf {
            script tel2;
            sub halant-telugu ka-telugu by ka-telugu.below;
        } blwf;

        feature psts {
            script tel2;
            sub ssa-telugu' [rVocalicMatra-telugu sha-telugu.below ka-telugu.below] by ssa-telugu.alt;
        } psts;
    """  # noqa: B950
    ufo = makeUFO(FontClass, glyphs, groups, kerning, features)
    ufo.lib["public.openTypeCategories"] = {
        "halant-telugu": "mark",
        "ka-telugu": "base",
        "rVocalicMatra-telugu": "mark",
        "ss-telugu.alt": "base",
        "ssa-telugu.alt": "base",
        "ssa-telugu": "base",
    }

    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert newFeatures.asFea() == snapshot


def test_mark_base_kerning(snapshot, FontClass):
    """Check that kerning of bases against marks is correctly split into
    base-only and mixed-mark-and-base lookups, to preserve the semantics of
    kerning exceptions (pairs modifying the effect of other pairs)."""

    glyphs = {
        "aa-tamil": 0x0B86,
        "va-tamil": 0x0BB5,
        "aulengthmark-tamil": 0x0BD7,
    }
    groups = {
        # Each group is a mix of mark and base glyph.
        "public.kern1.e-tamil": ["aulengthmark-tamil", "va-tamil"],
        "public.kern2.e-tamil": ["aulengthmark-tamil", "va-tamil"],
    }
    kerning = {
        ("aa-tamil", "va-tamil"): -20,
        ("aa-tamil", "public.kern2.e-tamil"): -35,
        ("va-tamil", "aa-tamil"): -20,
        ("public.kern1.e-tamil", "aa-tamil"): -35,
        ("aulengthmark-tamil", "aulengthmark-tamil"): -200,
        ("public.kern1.e-tamil", "public.kern2.e-tamil"): -100,
    }
    ufo = makeUFO(FontClass, glyphs, groups, kerning)
    ufo.lib["public.openTypeCategories"] = {
        "aulengthmark-tamil": "mark",
    }

    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert newFeatures.asFea() == snapshot


def test_hyphenated_duplicates(snapshot, FontClass):
    """Check that kerning group names are kept separate even if their sanitized
    names are the same."""

    glyphs = {"comma": ord(","), "period": ord(".")}
    groups = {
        "public.kern1.hy-phen": ["comma"],
        "public.kern1.hyp-hen": ["period"],
    }
    kerning = {
        ("public.kern1.hy-phen", "comma"): 1,
        ("public.kern1.hyp-hen", "period"): 2,
    }
    ufo = makeUFO(FontClass, glyphs, groups, kerning)

    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert newFeatures.asFea() == snapshot


def test_dflt_language(snapshot, FontClass):
    """Check that languages defined for the special DFLT script are registered
    as well."""

    glyphs = {"a": ord("a"), "comma": ord(",")}
    groups = {}
    kerning = {("a", "a"): 1, ("comma", "comma"): 2}
    features = """
        languagesystem DFLT dflt;
        languagesystem DFLT ZND;
        languagesystem latn dflt;
        languagesystem latn ANG;
    """
    ufo = makeUFO(FontClass, glyphs, groups, kerning, features)

    newFeatures = KernFeatureWriterTest.writeFeatures(ufo)

    assert newFeatures.asFea() == snapshot
