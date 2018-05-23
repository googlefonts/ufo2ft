# -*- coding: utf-8 -*-
from __future__ import (
    print_function,
    absolute_import,
    division,
    unicode_literals,
)
from fontTools.ttLib import TTFont
from fontTools.misc.py23 import basestring, unichr, byteord
from ufo2ft.outlineCompiler import OutlineTTFCompiler, OutlineOTFCompiler
from ufo2ft.fontInfoData import intListToNum
from fontTools.ttLib.tables._g_l_y_f import USE_MY_METRICS
from ufo2ft import compileTTF
import os
import pytest


def getpath(filename):
    dirname = os.path.dirname(__file__)
    return os.path.join(dirname, "data", filename)


@pytest.fixture
def testufo(FontClass):
    return FontClass(getpath("TestFont.ufo"))


@pytest.fixture
def use_my_metrics_ufo(FontClass):
    return FontClass(getpath("UseMyMetrics.ufo"))


@pytest.fixture
def emptyufo(FontClass):
    font = FontClass()
    font.info.unitsPerEm = 1000
    font.info.familyName = "Test Font"
    font.info.styleName = "Regular"
    font.info.ascender = 750
    font.info.descender = -250
    font.info.xHeight = 500
    font.info.capHeight = 750
    return font


class OutlineTTFCompilerTest(object):

    def test_setupTable_gasp(self, testufo):
        compiler = OutlineTTFCompiler(testufo)
        compiler.otf = TTFont()
        compiler.setupTable_gasp()
        assert "gasp" in compiler.otf
        assert compiler.otf["gasp"].gaspRange == {7: 10, 65535: 15}

    def test_compile_with_gasp(self, testufo):
        compiler = OutlineTTFCompiler(testufo)
        compiler.compile()
        assert "gasp" in compiler.otf
        assert compiler.otf["gasp"].gaspRange == {7: 10, 65535: 15}

    def test_compile_without_gasp(self, testufo):
        testufo.info.openTypeGaspRangeRecords = None
        compiler = OutlineTTFCompiler(testufo)
        compiler.compile()
        assert "gasp" not in compiler.otf

    def test_compile_empty_gasp(self, testufo):
        # ignore empty gasp
        testufo.info.openTypeGaspRangeRecords = []
        compiler = OutlineTTFCompiler(testufo)
        compiler.compile()
        assert "gasp" not in compiler.otf

    def test_makeGlyphsBoundingBoxes(self, testufo):
        # the call to 'makeGlyphsBoundingBoxes' happen in the __init__ method
        compiler = OutlineTTFCompiler(testufo)
        assert compiler.glyphBoundingBoxes[".notdef"] == (50, 0, 450, 750)
        # no outline data
        assert compiler.glyphBoundingBoxes["space"] is None
        # float coordinates are rounded, so is the bbox
        assert compiler.glyphBoundingBoxes["d"] == (90, 77, 211, 197)

    def test_autoUseMyMetrics(self, use_my_metrics_ufo):
        compiler = OutlineTTFCompiler(use_my_metrics_ufo)
        ttf = compiler.compile()
        # the first component in the 'Iacute' composite glyph ('acute')
        # does _not_ have the USE_MY_METRICS flag
        assert not (ttf["glyf"]["Iacute"].components[0].flags & USE_MY_METRICS)
        # the second component in the 'Iacute' composite glyph ('I')
        # has the USE_MY_METRICS flag set
        assert ttf["glyf"]["Iacute"].components[1].flags & USE_MY_METRICS
        # none of the 'I' components of the 'romanthree' glyph has
        # the USE_MY_METRICS flag set, because the composite glyph has a
        # different width
        for component in ttf["glyf"]["romanthree"].components:
            assert not (component.flags & USE_MY_METRICS)

    def test_autoUseMyMetrics_None(self, use_my_metrics_ufo):
        compiler = OutlineTTFCompiler(use_my_metrics_ufo)
        # setting 'autoUseMyMetrics' attribute to None disables the feature
        compiler.autoUseMyMetrics = None
        ttf = compiler.compile()
        assert not (ttf["glyf"]["Iacute"].components[1].flags & USE_MY_METRICS)

    def test_importTTX(self, testufo):
        compiler = OutlineTTFCompiler(testufo)
        otf = compiler.otf = TTFont()
        compiler.importTTX()
        assert "CUST" in otf
        assert otf["CUST"].data == b"\x00\x01\xbe\xef"
        assert otf.sfntVersion == "\x00\x01\x00\x00"

    def test_no_contour_glyphs(self, testufo):
        for glyph in testufo:
            glyph.clearContours()
        compiler = OutlineTTFCompiler(testufo)
        compiler.compile()
        assert compiler.otf["hhea"].advanceWidthMax == 600
        assert compiler.otf["hhea"].minLeftSideBearing == 0
        assert compiler.otf["hhea"].minRightSideBearing == 0
        assert compiler.otf["hhea"].xMaxExtent == 0

    def test_os2_no_widths(self, testufo):
        for glyph in testufo:
            glyph.width = 0
        compiler = OutlineTTFCompiler(testufo)
        compiler.compile()
        assert compiler.otf["OS/2"].xAvgCharWidth == 0


class OutlineOTFCompilerTest(object):

    def test_setupTable_CFF_all_blues_defined(self, testufo):
        testufo.info.postscriptBlueFuzz = 2
        testufo.info.postscriptBlueShift = 8
        testufo.info.postscriptBlueScale = 0.049736
        testufo.info.postscriptForceBold = False
        testufo.info.postscriptBlueValues = [-12, 0, 486, 498, 712, 724]
        testufo.info.postscriptOtherBlues = [-217, -205]
        testufo.info.postscriptFamilyBlues = [-12, 0, 486, 498, 712, 724]
        testufo.info.postscriptFamilyOtherBlues = [-217, -205]

        compiler = OutlineOTFCompiler(testufo)
        compiler.otf = TTFont(sfntVersion="OTTO")

        compiler.setupTable_CFF()

        cff = compiler.otf["CFF "].cff
        private = cff[list(cff.keys())[0]].Private

        assert private.BlueFuzz == 2
        assert private.BlueShift == 8
        assert private.BlueScale == 0.049736
        assert private.ForceBold == 0
        assert private.BlueValues == [-12, 0, 486, 498, 712, 724]
        assert private.OtherBlues == [-217, -205]
        assert private.FamilyBlues == [-12, 0, 486, 498, 712, 724]
        assert private.FamilyOtherBlues == [-217, -205]

    def test_setupTable_CFF_no_blues_defined(self, testufo):
        # no blue values defined
        testufo.info.postscriptBlueValues = []
        testufo.info.postscriptOtherBlues = []
        testufo.info.postscriptFamilyBlues = []
        testufo.info.postscriptFamilyOtherBlues = []
        # the following attributes have no effect
        testufo.info.postscriptBlueFuzz = 2
        testufo.info.postscriptBlueShift = 8
        testufo.info.postscriptBlueScale = 0.049736
        testufo.info.postscriptForceBold = False

        compiler = OutlineOTFCompiler(testufo)
        compiler.otf = TTFont(sfntVersion="OTTO")

        compiler.setupTable_CFF()

        cff = compiler.otf["CFF "].cff
        private = cff[list(cff.keys())[0]].Private

        # expect default values as defined in fontTools' cffLib.py
        assert private.BlueFuzz == 1
        assert private.BlueShift == 7
        assert private.BlueScale == 0.039625
        assert private.ForceBold == 0
        # CFF PrivateDict has no blues attributes
        assert not hasattr(private, "BlueValues")
        assert not hasattr(private, "OtherBlues")
        assert not hasattr(private, "FamilyBlues")
        assert not hasattr(private, "FamilyOtherBlues")

    def test_setupTable_CFF_some_blues_defined(self, testufo):
        testufo.info.postscriptBlueFuzz = 2
        testufo.info.postscriptForceBold = True
        testufo.info.postscriptBlueValues = []
        testufo.info.postscriptOtherBlues = [-217, -205]
        testufo.info.postscriptFamilyBlues = []
        testufo.info.postscriptFamilyOtherBlues = []

        compiler = OutlineOTFCompiler(testufo)
        compiler.otf = TTFont(sfntVersion="OTTO")

        compiler.setupTable_CFF()

        cff = compiler.otf["CFF "].cff
        private = cff[list(cff.keys())[0]].Private

        assert private.BlueFuzz == 2
        assert private.BlueShift == 7  # default
        assert private.BlueScale == 0.039625  # default
        assert private.ForceBold is True
        assert not hasattr(private, "BlueValues")
        assert private.OtherBlues == [-217, -205]
        assert not hasattr(private, "FamilyBlues")
        assert not hasattr(private, "FamilyOtherBlues")

    @staticmethod
    def get_charstring_program(ttFont, glyphName):
        cff = ttFont["CFF "].cff
        charstrings = cff[list(cff.keys())[0]].CharStrings
        c, _ = charstrings.getItemAndSelector(glyphName)
        c.decompile()
        return c.program

    def assertProgramEqual(self, expected, actual):
        assert len(expected) == len(actual)
        for exp_token, act_token in zip(expected, actual):
            if isinstance(exp_token, basestring):
                assert exp_token == act_token
            else:
                assert not isinstance(act_token, basestring)
                assert exp_token == pytest.approx(act_token)

    def test_setupTable_CFF_round_all(self, testufo):
        # by default all floats are rounded to integer
        compiler = OutlineOTFCompiler(testufo)
        otf = compiler.otf = TTFont(sfntVersion="OTTO")

        compiler.setupTable_CFF()
        # glyph 'd' in TestFont.ufo contains float coordinates
        program = self.get_charstring_program(otf, "d")

        self.assertProgramEqual(
            program,
            [
                -26,
                151,
                197,
                "rmoveto",
                -34,
                -27,
                -27,
                -33,
                -33,
                27,
                -27,
                34,
                33,
                27,
                27,
                33,
                33,
                -27,
                27,
                -33,
                "hvcurveto",
                "endchar",
            ],
        )

    def test_setupTable_CFF_round_none(self, testufo):
        # roundTolerance=0 means 'don't round, keep all floats'
        compiler = OutlineOTFCompiler(testufo, roundTolerance=0)
        otf = compiler.otf = TTFont(sfntVersion="OTTO")

        compiler.setupTable_CFF()
        program = self.get_charstring_program(otf, "d")

        self.assertProgramEqual(
            program,
            [
                -26,
                150.66,
                197.32,
                "rmoveto",
                -33.66,
                -26.67,
                -26.99,
                -33.33,
                -33.33,
                26.67,
                -26.66,
                33.66,
                33.33,
                26.66,
                26.66,
                33.33,
                33.33,
                -26.66,
                26.99,
                -33.33,
                "hvcurveto",
                "endchar",
            ],
        )

    def test_setupTable_CFF_round_some(self, testufo):
        # only floats 'close enough' are rounded to integer
        compiler = OutlineOTFCompiler(testufo, roundTolerance=0.34)
        otf = compiler.otf = TTFont(sfntVersion="OTTO")

        compiler.setupTable_CFF()
        program = self.get_charstring_program(otf, "d")

        self.assertProgramEqual(
            program,
            [
                -26,
                150.66,
                197,
                "rmoveto",
                -33.66,
                -27,
                -27,
                -33,
                -33,
                27,
                -27,
                33.66,
                33.34,
                26.65,
                27,
                33,
                33,
                -26.65,
                27,
                -33.34,
                "hvcurveto",
                "endchar",
            ],
        )

    def test_makeGlyphsBoundingBoxes(self, testufo):
        # the call to 'makeGlyphsBoundingBoxes' happen in the __init__ method
        compiler = OutlineOTFCompiler(testufo)
        # with default roundTolerance, all coordinates and hence the bounding
        # box values are rounded with round()
        assert compiler.glyphBoundingBoxes["d"] == (90, 77, 211, 197)

    def test_makeGlyphsBoundingBoxes_floats(self, testufo):
        # specifying a custom roundTolerance affects which coordinates are
        # rounded; in this case, the top-most Y coordinate stays a float
        # (197.32), hence the bbox.yMax (198) is rounded using math.ceiling()
        compiler = OutlineOTFCompiler(testufo, roundTolerance=0.1)
        assert compiler.glyphBoundingBoxes["d"] == (90, 77, 211, 198)

    def test_importTTX(self, testufo):
        compiler = OutlineOTFCompiler(testufo)
        otf = compiler.otf = TTFont(sfntVersion="OTTO")
        compiler.importTTX()
        assert "CUST" in otf
        assert otf["CUST"].data == b"\x00\x01\xbe\xef"
        assert otf.sfntVersion == "OTTO"

    def test_no_contour_glyphs(self, testufo):
        for glyph in testufo:
            glyph.clearContours()
        compiler = OutlineOTFCompiler(testufo)
        compiler.compile()
        assert compiler.otf["hhea"].advanceWidthMax == 600
        assert compiler.otf["hhea"].minLeftSideBearing == 0
        assert compiler.otf["hhea"].minRightSideBearing == 0
        assert compiler.otf["hhea"].xMaxExtent == 0

    def test_optimized_default_and_nominal_widths(self, FontClass):
        ufo = FontClass()
        ufo.info.unitsPerEm = 1000
        for glyphName, width in (
            (".notdef", 500),
            ("space", 250),
            ("a", 388),
            ("b", 410),
            ("c", 374),
            ("d", 374),
            ("e", 388),
            ("f", 410),
            ("g", 388),
            ("h", 410),
            ("i", 600),
            ("j", 600),
            ("k", 600),
            ("l", 600),
        ):
            glyph = ufo.newGlyph(glyphName)
            glyph.width = width

        compiler = OutlineOTFCompiler(ufo)
        compiler.otf = TTFont(sfntVersion="OTTO")

        compiler.setupTable_hmtx()
        compiler.setupTable_CFF()

        cff = compiler.otf["CFF "].cff
        topDict = cff[list(cff.keys())[0]]
        private = topDict.Private

        assert private.defaultWidthX == 600
        assert private.nominalWidthX == 303

        charStrings = topDict.CharStrings
        # the following have width == defaultWidthX, so it's omitted
        for g in ("i", "j", "k", "l"):
            assert charStrings.getItemAndSelector(g)[0].program == ["endchar"]
        # 'space' has width 250, so the width encoded in its charstring is:
        # 250 - nominalWidthX
        assert charStrings.getItemAndSelector("space")[0].program == [
            -53,
            "endchar",
        ]


class TestGlyphOrder(object):

    def test_compile_original_glyph_order(self, testufo):
        DEFAULT_ORDER = [
            ".notdef",
            "space",
            "a",
            "b",
            "c",
            "d",
            "e",
            "f",
            "g",
            "h",
            "i",
            "j",
            "k",
            "l",
        ]
        compiler = OutlineTTFCompiler(testufo)
        compiler.compile()
        assert compiler.otf.getGlyphOrder() == DEFAULT_ORDER

    def test_compile_tweaked_glyph_order(self, testufo):
        NEW_ORDER = [
            ".notdef",
            "space",
            "b",
            "a",
            "c",
            "d",
            "e",
            "f",
            "g",
            "h",
            "i",
            "j",
            "k",
            "l",
        ]
        testufo.lib["public.glyphOrder"] = NEW_ORDER
        compiler = OutlineTTFCompiler(testufo)
        compiler.compile()
        assert compiler.otf.getGlyphOrder() == NEW_ORDER

    def test_compile_strange_glyph_order(self, testufo):
        """Move space and .notdef to end of glyph ids
        ufo2ft always puts .notdef first.
        """
        NEW_ORDER = ["b", "a", "c", "d", "space", ".notdef"]
        EXPECTED_ORDER = [
            ".notdef",
            "b",
            "a",
            "c",
            "d",
            "space",
            "e",
            "f",
            "g",
            "h",
            "i",
            "j",
            "k",
            "l",
        ]
        testufo.lib["public.glyphOrder"] = NEW_ORDER
        compiler = OutlineTTFCompiler(testufo)
        compiler.compile()
        assert compiler.otf.getGlyphOrder() == EXPECTED_ORDER


class TestNames(object):

    def test_compile_without_production_names(self, testufo):
        expected = [
            ".notdef",
            "space",
            "a",
            "b",
            "c",
            "d",
            "e",
            "f",
            "g",
            "h",
            "i",
            "j",
            "k",
            "l",
        ]

        result = compileTTF(testufo, useProductionNames=False)
        assert result.getGlyphOrder() == expected

        testufo.lib["com.github.googlei18n.ufo2ft.useProductionNames"] = False
        result = compileTTF(testufo)
        assert result.getGlyphOrder() == expected

    def test_compile_with_production_names(self, testufo):
        expected = [
            ".notdef",
            "uni0020",
            "uni0061",
            "uni0062",
            "uni0063",
            "uni0064",
            "uni0065",
            "uni0066",
            "uni0067",
            "uni0068",
            "uni0069",
            "uni006A",
            "uni006B",
            "uni006C",
        ]

        result = compileTTF(testufo)
        assert result.getGlyphOrder() == expected

        result = compileTTF(testufo, useProductionNames=True)
        assert result.getGlyphOrder() == expected

        testufo.lib["com.github.googlei18n.ufo2ft.useProductionNames"] = True
        result = compileTTF(testufo)
        assert result.getGlyphOrder() == expected

    CUSTOM_POSTSCRIPT_NAMES = {
        ".notdef": ".notdef",
        "space": "foo",
        "a": "bar",
        "b": "baz",
        "c": "meh",
        "d": "doh",
        "e": "bim",
        "f": "bum",
        "g": "bam",
        "h": "bib",
        "i": "bob",
        "j": "bub",
        "k": "kkk",
        "l": "lll",
    }

    def test_compile_with_custom_postscript_names(self, testufo):
        testufo.lib["public.postscriptNames"] = self.CUSTOM_POSTSCRIPT_NAMES
        result = compileTTF(testufo, useProductionNames=True)
        assert sorted(result.getGlyphOrder()) == sorted(
            self.CUSTOM_POSTSCRIPT_NAMES.values()
        )

    def test_compile_with_custom_postscript_names_notdef_preserved(
        self, testufo
    ):
        custom_names = dict(self.CUSTOM_POSTSCRIPT_NAMES)
        custom_names[".notdef"] = "defnot"
        testufo.lib["public.postscriptNames"] = custom_names
        result = compileTTF(testufo, useProductionNames=True)
        assert result.getGlyphOrder() == [
            ".notdef",
            "foo",
            "bar",
            "baz",
            "meh",
            "doh",
            "bim",
            "bum",
            "bam",
            "bib",
            "bob",
            "bub",
            "kkk",
            "lll",
        ]


ASCII = [unichr(c) for c in range(0x20, 0x7E)]


@pytest.mark.parametrize(
    "unicodes, expected",
    [
        [ASCII + ["Þ"], {0}],  # Latin 1
        [ASCII + ["Ľ"], {1}],  # Latin 2: Eastern Europe
        [ASCII + ["Ľ", "┤"], {1, 58}],  # Latin 2
        [["Б"], {2}],  # Cyrillic
        [["Б", "Ѕ", "┤"], {2, 57}],  # IBM Cyrillic
        [["Б", "╜", "┤"], {2, 49}],  # MS-DOS Russian
        [["Ά"], {3}],  # Greek
        [["Ά", "½", "┤"], {3, 48}],  # IBM Greek
        [["Ά", "√", "┤"], {3, 60}],  # Greek, former 437 G
        [ASCII + ["İ"], {4}],  # Turkish
        [ASCII + ["İ", "┤"], {4, 56}],  # IBM turkish
        [["א"], {5}],  # Hebrew
        [["א", "√", "┤"], {5, 53}],  # Hebrew
        [["ر"], {6}],  # Arabic
        [["ر", "√"], {6, 51}],  # Arabic
        [["ر", "√", "┤"], {6, 51, 61}],  # Arabic; ASMO 708
        [ASCII + ["ŗ"], {7}],  # Windows Baltic
        [ASCII + ["ŗ", "┤"], {7, 59}],  # MS-DOS Baltic
        [ASCII + ["₫"], {8}],  # Vietnamese
        [["ๅ"], {16}],  # Thai
        [["エ"], {17}],  # JIS/Japan
        [["ㄅ"], {18}],  # Chinese: Simplified chars
        [["ㄱ"], {19}],  # Korean wansung
        [["央"], {20}],  # Chinese: Traditional chars
        [["곴"], {21}],  # Korean Johab
        [ASCII + ["♥"], {30}],  # OEM Character Set
        [ASCII + ["þ", "┤"], {54}],  # MS-DOS Icelandic
        [ASCII + ["╚"], {62, 63}],  # WE/Latin 1
        [ASCII + ["┤", "√", "Å"], {50}],  # MS-DOS Nordic
        [ASCII + ["┤", "√", "é"], {52}],  # MS-DOS Canadian French
        [ASCII + ["┤", "√", "õ"], {55}],  # MS-DOS Portuguese
        [ASCII + ["‰", "∑"], {29}],  # Macintosh Character Set (US Roman)
    ],
)
def test_calcCodePageRanges(emptyufo, unicodes, expected):
    font = emptyufo
    for i, c in enumerate(unicodes):
        font.newGlyph("glyph%d" % i).unicode = byteord(c)

    compiler = OutlineOTFCompiler(font)
    compiler.compile()

    assert compiler.otf["OS/2"].ulCodePageRange1 == intListToNum(
        expected, start=0, length=32
    )
    assert compiler.otf["OS/2"].ulCodePageRange2 == intListToNum(
        expected, start=32, length=32
    )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main(sys.argv))
