# -*- coding: utf-8 -*-
from __future__ import print_function, absolute_import, division, unicode_literals
from fontTools.ttLib import TTFont
from fontTools.misc.py23 import basestring, unichr, byteord
from fontTools import designspaceLib
from ufo2ft.outlineCompiler import OutlineTTFCompiler, OutlineOTFCompiler
from ufo2ft.fontInfoData import intListToNum
from fontTools.ttLib.tables._g_l_y_f import USE_MY_METRICS
from ufo2ft.constants import (
    USE_PRODUCTION_NAMES,
    GLYPHS_DONT_USE_PRODUCTION_NAMES,
    SPARSE_TTF_MASTER_TABLES,
    SPARSE_OTF_MASTER_TABLES,
)
from ufo2ft import (
    compileTTF,
    compileOTF,
    compileInterpolatableTTFs,
    compileInterpolatableTTFsFromDS,
    compileInterpolatableOTFsFromDS,
)
import os
import logging
import pytest


def getpath(filename):
    dirname = os.path.dirname(__file__)
    return os.path.join(dirname, "data", filename)


@pytest.fixture
def testufo(FontClass):
    font = FontClass(getpath("TestFont.ufo"))
    del font.lib["public.postscriptNames"]
    return font


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

    def test_missing_component(self, emptyufo):
        ufo = emptyufo
        a = ufo.newGlyph("a")
        pen = a.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((100, 0))
        pen.lineTo((100, 100))
        pen.lineTo((0, 100))
        pen.closePath()

        # a mixed contour/component glyph, which is decomposed by the
        # TTGlyphPen; one of the components does not exist thus should
        # be dropped
        b = ufo.newGlyph("b")
        pen = b.getPen()
        pen.moveTo((0, 200))
        pen.lineTo((100, 200))
        pen.lineTo((50, 300))
        pen.closePath()
        pen.addComponent("a", (1, 0, 0, 1, 0, 0))
        pen.addComponent("c", (1, 0, 0, 1, 0, 0))  # missing

        d = ufo.newGlyph("d")
        pen = d.getPen()
        pen.addComponent("c", (1, 0, 0, 1, 0, 0))  # missing

        e = ufo.newGlyph("e")
        pen = e.getPen()
        pen.addComponent("a", (1, 0, 0, 1, 0, 0))
        pen.addComponent("c", (1, 0, 0, 1, 0, 0))  # missing

        compiler = OutlineTTFCompiler(ufo)
        ttFont = compiler.compile()
        glyf = ttFont["glyf"]

        assert glyf["a"].numberOfContours == 1
        assert glyf["b"].numberOfContours == 2
        assert glyf["d"].numberOfContours == 0
        assert glyf["e"].numberOfContours == -1  # composite glyph
        assert len(glyf["e"].components) == 1


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

    def test_setupTable_CFF_optimize(self, testufo):
        compiler = OutlineOTFCompiler(testufo, optimizeCFF=True)
        otf = compiler.otf = TTFont(sfntVersion="OTTO")

        compiler.setupTable_CFF()
        program = self.get_charstring_program(otf, "a")

        self.assertProgramEqual(
            program,
            [-12, 66, "hmoveto", 256, "hlineto", -128, 510, "rlineto", "endchar"],
        )

    def test_setupTable_CFF_no_optimize(self, testufo):
        compiler = OutlineOTFCompiler(testufo, optimizeCFF=False)
        otf = compiler.otf = TTFont(sfntVersion="OTTO")

        compiler.setupTable_CFF()
        program = self.get_charstring_program(otf, "a")

        self.assertProgramEqual(
            program,
            [-12, 66, 0, "rmoveto", 256, 0, "rlineto", -128, 510, "rlineto", "endchar"],
        )

    def test_makeGlyphsBoundingBoxes(self, testufo):
        # the call to 'makeGlyphsBoundingBoxes' happen in the __init__ method
        compiler = OutlineOTFCompiler(testufo)
        # with default roundTolerance, all coordinates and hence the bounding
        # box values are rounded with otRound()
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
        assert charStrings.getItemAndSelector("space")[0].program == [-53, "endchar"]


class GlyphOrderTest(object):
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


class NamesTest(object):
    @pytest.mark.parametrize(
        "prod_names_key, prod_names_value",
        [(USE_PRODUCTION_NAMES, False), (GLYPHS_DONT_USE_PRODUCTION_NAMES, True)],
        ids=["useProductionNames", "Don't use Production Names"],
    )
    def test_compile_without_production_names(
        self, testufo, prod_names_key, prod_names_value
    ):
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

        testufo.lib[prod_names_key] = prod_names_value
        result = compileTTF(testufo)
        assert result.getGlyphOrder() == expected

    def test_compile_with_production_names(self, testufo):
        original = [
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
        modified = [
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
        assert result.getGlyphOrder() == original

        result = compileTTF(testufo, useProductionNames=True)
        assert result.getGlyphOrder() == modified

        testufo.lib[USE_PRODUCTION_NAMES] = True
        result = compileTTF(testufo)
        assert result.getGlyphOrder() == modified

    def test_postprocess_production_names_no_notdef(self, testufo):
        import ufo2ft

        del testufo[".notdef"]
        assert ".notdef" not in testufo
        result = compileTTF(testufo, useProductionNames=False)
        assert ".notdef" in result.getGlyphOrder()

        pp = ufo2ft.postProcessor.PostProcessor(result, testufo, glyphSet=None)
        try:
            f = pp.process(useProductionNames=True)
        except Exception as e:
            pytest.xfail("Unexpected exception: " + str(e))
        assert ".notdef" in f.getGlyphOrder()

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

    @pytest.mark.parametrize("use_production_names", [None, True])
    def test_compile_with_custom_postscript_names(self, testufo, use_production_names):
        testufo.lib["public.postscriptNames"] = self.CUSTOM_POSTSCRIPT_NAMES
        result = compileTTF(testufo, useProductionNames=use_production_names)
        assert sorted(result.getGlyphOrder()) == sorted(
            self.CUSTOM_POSTSCRIPT_NAMES.values()
        )

    @pytest.mark.parametrize("use_production_names", [None, True])
    def test_compile_with_custom_postscript_names_notdef_preserved(
        self, testufo, use_production_names
    ):
        custom_names = dict(self.CUSTOM_POSTSCRIPT_NAMES)
        del custom_names[".notdef"]
        testufo.lib["public.postscriptNames"] = custom_names
        result = compileTTF(testufo, useProductionNames=use_production_names)
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

    def test_warn_name_exceeds_max_length(self, testufo, caplog):
        long_name = 64 * "a"
        testufo.newGlyph(long_name)

        with caplog.at_level(logging.WARNING, logger="ufo2ft.postProcessor"):
            result = compileTTF(testufo, useProductionNames=True)

        assert "length exceeds 63 characters" in caplog.text
        assert long_name in result.getGlyphOrder()

    def test_duplicate_glyph_names(self, testufo):
        order = ["ab", "ab.1", "a-b", "a/b", "ba"]
        testufo.lib["public.glyphOrder"] = order
        testufo.lib["public.postscriptNames"] = {"ba": "ab"}
        for name in order:
            if name not in testufo:
                testufo.newGlyph(name)

        result = compileTTF(testufo, useProductionNames=True).getGlyphOrder()

        assert result[1] == "ab"
        assert result[2] == "ab.1"
        assert result[3] == "ab.2"
        assert result[4] == "ab.3"
        assert result[5] == "ab.4"

    def test_too_long_production_name(self, testufo):
        name = "_".join(("a",) * 16)
        testufo.newGlyph(name)

        result = compileTTF(testufo, useProductionNames=True).getGlyphOrder()

        # the production name uniXXXX would exceed the max length so the
        # original name is used
        assert name in result


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
        [[" ", "0", "1", "2", "අ"], {0}],  # always fallback to Latin 1
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


def test_custom_layer_compilation(layertestrgufo):
    ufo = layertestrgufo

    font_otf = compileOTF(ufo, layerName="Medium")
    assert font_otf.getGlyphOrder() == [".notdef", "e"]
    font_ttf = compileTTF(ufo, layerName="Medium")
    assert font_ttf.getGlyphOrder() == [".notdef", "e"]


def test_custom_layer_compilation_interpolatable(layertestrgufo, layertestbdufo):
    ufo1 = layertestrgufo
    ufo2 = layertestbdufo

    master_ttfs = list(
        compileInterpolatableTTFs([ufo1, ufo1, ufo2], layerNames=[None, "Medium", None])
    )
    assert master_ttfs[0].getGlyphOrder() == [
        ".notdef",
        "a",
        "e",
        "s",
        "dotabovecomb",
        "edotabove",
    ]
    assert master_ttfs[1].getGlyphOrder() == [".notdef", "e"]
    assert master_ttfs[2].getGlyphOrder() == [
        ".notdef",
        "a",
        "e",
        "s",
        "dotabovecomb",
        "edotabove",
    ]

    sparse_tables = [tag for tag in master_ttfs[1].keys() if tag != "GlyphOrder"]
    assert SPARSE_TTF_MASTER_TABLES.issuperset(sparse_tables)


@pytest.mark.parametrize("inplace", [False, True], ids=["not inplace", "inplace"])
def test_custom_layer_compilation_interpolatable_from_ds(designspace, inplace):
    result = compileInterpolatableTTFsFromDS(designspace, inplace=inplace)
    assert (designspace is result) == inplace

    master_ttfs = [s.font for s in result.sources]

    assert master_ttfs[0].getGlyphOrder() == [
        ".notdef",
        "a",
        "e",
        "s",
        "dotabovecomb",
        "edotabove",
    ]
    assert master_ttfs[1].getGlyphOrder() == [".notdef", "e"]
    assert master_ttfs[2].getGlyphOrder() == [
        ".notdef",
        "a",
        "e",
        "s",
        "dotabovecomb",
        "edotabove",
    ]

    sparse_tables = [tag for tag in master_ttfs[1].keys() if tag != "GlyphOrder"]
    assert SPARSE_TTF_MASTER_TABLES.issuperset(sparse_tables)

    # sentinel value used by varLib to ignore the post table for this sparse
    # master when building the MVAR table
    assert master_ttfs[1]["post"].underlinePosition == -0x8000
    assert master_ttfs[1]["post"].underlineThickness == -0x8000


@pytest.mark.parametrize("inplace", [False, True], ids=["not inplace", "inplace"])
def test_custom_layer_compilation_interpolatable_otf_from_ds(designspace, inplace):
    result = compileInterpolatableOTFsFromDS(designspace, inplace=inplace)
    assert (designspace is result) == inplace

    master_otfs = [s.font for s in result.sources]

    assert master_otfs[0].getGlyphOrder() == [
        ".notdef",
        "a",
        "e",
        "s",
        "dotabovecomb",
        "edotabove",
    ]
    assert master_otfs[1].getGlyphOrder() == [".notdef", "e"]
    assert master_otfs[2].getGlyphOrder() == [
        ".notdef",
        "a",
        "e",
        "s",
        "dotabovecomb",
        "edotabove",
    ]

    sparse_tables = [tag for tag in master_otfs[1].keys() if tag != "GlyphOrder"]
    assert SPARSE_OTF_MASTER_TABLES.issuperset(sparse_tables)


def test_compilation_from_ds_missing_source_font(designspace):
    designspace.sources[0].font = None
    with pytest.raises(AttributeError, match="missing required 'font'"):
        compileInterpolatableTTFsFromDS(designspace)


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main(sys.argv))
