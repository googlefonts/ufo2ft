import difflib
import io
import logging
import os
import re
import sys
from pathlib import Path
from textwrap import dedent

import pytest
from fontTools.designspaceLib import DesignSpaceDocument
from fontTools.otlLib.optimize.gpos import COMPRESSION_LEVEL as GPOS_COMPRESSION_LEVEL
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib.tables._g_l_y_f import (
    OVERLAP_COMPOUND,
    flagCubic,
    flagOverlapSimple,
)

from ufo2ft import (
    compileInterpolatableTTFs,
    compileOTF,
    compileTTF,
    compileVariableCFF2,
    compileVariableCFF2s,
    compileVariableTTF,
    compileVariableTTFs,
)
from ufo2ft.constants import KEEP_GLYPH_NAMES, TRUETYPE_OVERLAP_KEY
from ufo2ft.errors import InvalidFontData
from ufo2ft.filters import TransformationsFilter


def getpath(filename):
    dirname = os.path.dirname(__file__)
    return os.path.join(dirname, "data", filename)


@pytest.fixture
def testufo(FontClass):
    return FontClass(getpath("TestFont.ufo"))


def readLines(f):
    f.seek(0)
    lines = []
    for line in f.readlines():
        # Elide ttLibVersion because it frequently changes.
        # Use os-native line separators so we can run difflib.
        if line.startswith("<ttFont "):
            lines.append("<ttFont>" + os.linesep)
        else:
            lines.append(line.rstrip() + os.linesep)
    return lines


def expectTTX(font, expectedTTX, tables=None):
    with open(getpath(expectedTTX), encoding="utf-8") as f:
        expected = readLines(f)
    font.recalcTimestamp = False
    font["head"].created, font["head"].modified = 3570196637, 3601822698
    font["head"].checkSumAdjustment = 0x12345678
    f = io.StringIO()
    font.saveXML(f, tables=tables)

    actual = readLines(f)
    if actual != expected:
        for line in difflib.unified_diff(
            expected, actual, fromfile=expectedTTX, tofile="<generated>"
        ):
            sys.stderr.write(line)
        pytest.fail("TTX output is different from expected")


@pytest.fixture(params=[None, True, False])
def useProductionNames(request):
    return request.param


class IntegrationTest:
    _layoutTables = ["GDEF", "GSUB", "GPOS", "BASE"]

    # We have specific unit tests for CFF vs TrueType output, but we run
    # an integration test here to make sure things work end-to-end.
    # No need to test both formats for every single test case.

    def test_TestFont_TTF(self, testufo):
        ttf = compileTTF(testufo)
        expectTTX(ttf, "TestFont.ttx")

    def test_TestFont_CFF(self, testufo):
        otf = compileOTF(testufo)
        expectTTX(otf, "TestFont-CFF.ttx")

    def test_included_features(self, FontClass):
        """Checks how the compiler handles include statements in features.fea.

        The compiler should detect which features are defined by the
        features.fea inside the compiled UFO, or by feature files that
        are included from there.

        https://github.com/googlei18n/ufo2ft/issues/108

        Relative paths should be resolved taking the UFO path as reference,
        not the embedded features.fea file.

        https://github.com/unified-font-object/ufo-spec/issues/55
        """
        ufo = FontClass(getpath("Bug108.ufo"))
        ttf = compileTTF(ufo)
        expectTTX(ttf, "Bug108.ttx", tables=self._layoutTables)

    def test_included_features_with_custom_include_dir(self, FontClass, tmp_path):
        ufo = FontClass(getpath("Bug108.ufo"))
        features_dir = tmp_path / "features"
        features_dir.mkdir()
        (features_dir / "foobarbaz.fea").write_text(
            Path(getpath("Bug108_included.fea")).read_text()
        )
        ufo.features.text = "include(features/foobarbaz.fea);"
        ttf = compileTTF(ufo, feaIncludeDir=tmp_path)
        expectTTX(ttf, "Bug108.ttx", tables=self._layoutTables)

    def test_mti_features(self, FontClass):
        """Checks handling of UFOs with embdedded MTI/Monotype feature files
        https://github.com/googlei18n/fontmake/issues/289
        """
        ufo = FontClass(getpath("MTIFeatures.ufo"))
        ttf = compileTTF(ufo)
        expectTTX(ttf, "MTIFeatures.ttx", tables=self._layoutTables)

    def test_removeOverlaps_CFF(self, testufo):
        otf = compileOTF(testufo, removeOverlaps=True)
        expectTTX(otf, "TestFont-NoOverlaps-CFF.ttx")

    def test_removeOverlaps_CFF_pathops(self, testufo):
        otf = compileOTF(testufo, removeOverlaps=True, overlapsBackend="pathops")
        expectTTX(otf, "TestFont-NoOverlaps-CFF-pathops.ttx")

    def test_removeOverlaps(self, testufo):
        ttf = compileTTF(testufo, removeOverlaps=True)
        expectTTX(ttf, "TestFont-NoOverlaps-TTF.ttx")

    def test_removeOverlaps_pathops(self, testufo):
        ttf = compileTTF(testufo, removeOverlaps=True, overlapsBackend="pathops")
        expectTTX(ttf, "TestFont-NoOverlaps-TTF-pathops.ttx")

    def test_nestedComponents(self, FontClass):
        ufo = FontClass(getpath("NestedComponents-Regular.ufo"))
        ttf = compileTTF(ufo)
        assert ttf["maxp"].maxComponentDepth != 1
        ttf = compileTTF(ufo, flattenComponents=True)
        assert ttf["maxp"].maxComponentDepth == 1

    def test_nestedComponents_interpolatable(self, FontClass):
        ufos = [
            FontClass(getpath("NestedComponents-Regular.ufo")),
            FontClass(getpath("NestedComponents-Bold.ufo")),
        ]
        ttfs = compileInterpolatableTTFs(ufos)
        for ttf in ttfs:
            assert ttf["maxp"].maxComponentDepth != 1
        ttfs = compileInterpolatableTTFs(ufos, flattenComponents=True)
        for ttf in ttfs:
            assert ttf["maxp"].maxComponentDepth == 1

    def test_interpolatableTTFs_lazy(self, FontClass):
        # two same UFOs **must** be interpolatable
        ufos = [FontClass(getpath("TestFont.ufo")) for _ in range(2)]
        ttfs = list(compileInterpolatableTTFs(ufos))
        expectTTX(ttfs[0], "TestFont.ttx")
        expectTTX(ttfs[1], "TestFont.ttx")

    @pytest.mark.parametrize(
        "cff_version, expected_ttx",
        [(1, "TestFont-NoOptimize-CFF.ttx"), (2, "TestFont-NoOptimize-CFF2.ttx")],
        ids=["cff1", "cff2"],
    )
    def test_optimizeCFF_none(self, testufo, cff_version, expected_ttx):
        otf = compileOTF(testufo, optimizeCFF=0, cffVersion=cff_version)
        expectTTX(otf, expected_ttx)

    @pytest.mark.parametrize(
        "cff_version, expected_ttx",
        [(1, "TestFont-Specialized-CFF.ttx"), (2, "TestFont-Specialized-CFF2.ttx")],
        ids=["cff1", "cff2"],
    )
    def test_optimizeCFF_specialize(self, testufo, cff_version, expected_ttx):
        otf = compileOTF(testufo, optimizeCFF=1, cffVersion=cff_version)
        expectTTX(otf, expected_ttx)

    @pytest.mark.parametrize(
        "subroutinizer, cff_version, expected_ttx",
        [
            (None, 1, "TestFont-CFF.ttx"),
            ("compreffor", 1, "TestFont-CFF-compreffor.ttx"),
            ("cffsubr", 1, "TestFont-CFF.ttx"),
            (None, 2, "TestFont-CFF2-cffsubr.ttx"),
            # ("compreffor", 2, "TestFont-CFF2-compreffor.ttx"),
            ("cffsubr", 2, "TestFont-CFF2-cffsubr.ttx"),
        ],
        ids=[
            "default-cff1",
            "compreffor-cff1",
            "cffsubr-cff1",
            "default-cff2",
            # "compreffor-cff2",
            "cffsubr-cff2",
        ],
    )
    def test_optimizeCFF_subroutinize(
        self, testufo, cff_version, subroutinizer, expected_ttx
    ):
        otf = compileOTF(
            testufo, optimizeCFF=2, cffVersion=cff_version, subroutinizer=subroutinizer
        )
        expectTTX(otf, expected_ttx)

    def test_compileVariableTTF(self, designspace, useProductionNames):
        varfont = compileVariableTTF(designspace, useProductionNames=useProductionNames)
        expectTTX(
            varfont,
            "TestVariableFont-TTF{}.ttx".format(
                "-useProductionNames" if useProductionNames else ""
            ),
        )

    def test_compileVariableCFF2(self, designspace, useProductionNames):
        varfont = compileVariableCFF2(
            designspace, useProductionNames=useProductionNames
        )
        expectTTX(
            varfont,
            "TestVariableFont-CFF2{}.ttx".format(
                "-useProductionNames" if useProductionNames else ""
            ),
        )

    def test_compileVariableCFF2_subroutinized(self, designspace):
        varfont = compileVariableCFF2(designspace, optimizeCFF=2)
        expectTTX(varfont, "TestVariableFont-CFF2-cffsubr.ttx")

    def test_debugFeatureFile(self, designspace):
        tmp = io.StringIO()

        _ = compileVariableTTF(designspace, debugFeatureFile=tmp)
        assert "\n" + tmp.getvalue() == dedent(
            """
            markClass dotabovecomb <anchor -2 465> @MC_top;

            feature liga {
                sub a e s s by s;
            } liga;

            feature mark {
                lookup mark2base {
                    pos base e
                        <anchor (wght=350:314 wght=450:314 wght=625:315) (wght=350:556 wght=450:556 wght=625:644)> mark @MC_top;
                } mark2base;

            } mark;
        """  # noqa: B950
        )

    @pytest.mark.parametrize(
        "output_format, options, expected_ttx",
        [
            ("TTF", {}, "TestFont-TTF-post3.ttx"),
            ("OTF", {"cffVersion": 2}, "TestFont-CFF2-post3.ttx"),
        ],
    )
    def test_drop_glyph_names(self, testufo, output_format, options, expected_ttx):
        testufo.lib[KEEP_GLYPH_NAMES] = False
        compile_func = globals()[f"compile{output_format}"]
        ttf = compile_func(testufo, **options)
        expectTTX(ttf, expected_ttx)

    @pytest.mark.parametrize(
        "output_format, options, expected_ttx",
        [
            ("VariableTTF", {}, "TestVariableFont-TTF-post3.ttx"),
            ("VariableCFF2", {}, "TestVariableFont-CFF2-post3.ttx"),
        ],
    )
    def test_drop_glyph_names_variable(
        self, designspace, output_format, options, expected_ttx
    ):
        # set keepGlyphNames in the default UFO.lib where postProcessor finds it
        designspace.findDefault().font.lib[KEEP_GLYPH_NAMES] = False
        compile_func = globals()[f"compile{output_format}"]
        ttf = compile_func(designspace, **options)
        expectTTX(ttf, expected_ttx)

    @pytest.mark.parametrize(
        "compileFunc",
        [
            compileOTF,
            compileTTF,
        ],
    )
    def test_compile_filters(self, compileFunc, FontClass):
        ufo = FontClass(getpath("LayerFont-Regular.ufo"))
        filters = [TransformationsFilter(OffsetY=10)]
        ttf = compileFunc(ufo, filters=filters)

        pen1 = BoundsPen(ufo)
        glyph = ufo["a"]
        glyph.draw(pen1)

        glyphSet = ttf.getGlyphSet()
        tt_glyph = glyphSet["a"]
        pen2 = BoundsPen(glyphSet)
        tt_glyph.draw(pen2)

        assert pen1.bounds[0] == pen2.bounds[0]
        assert pen1.bounds[1] + 10 == pen2.bounds[1]
        assert pen1.bounds[2] == pen2.bounds[2]
        assert pen1.bounds[3] + 10 == pen2.bounds[3]

    @pytest.mark.parametrize(
        "compileFunc",
        [
            compileVariableTTF,
            compileVariableCFF2,
        ],
    )
    def test_compileVariable_filters(self, designspace, compileFunc):
        filters = [TransformationsFilter(OffsetY=10)]
        varfont = compileFunc(designspace, filters=filters)

        ufo = designspace.sources[0].font
        pen1 = BoundsPen(ufo)
        glyph = ufo["a"]
        glyph.draw(pen1)

        glyphSet = varfont.getGlyphSet()
        tt_glyph = glyphSet["a"]
        pen2 = BoundsPen(glyphSet)
        tt_glyph.draw(pen2)

        assert pen1.bounds[0] == pen2.bounds[0]
        assert pen1.bounds[1] + 10 == pen2.bounds[1]
        assert pen1.bounds[2] == pen2.bounds[2]
        assert pen1.bounds[3] + 10 == pen2.bounds[3]

    def test_compileInterpolatableTTFs(self, FontClass):
        ufos = [
            FontClass(getpath("NestedComponents-Regular.ufo")),
            FontClass(getpath("NestedComponents-Bold.ufo")),
        ]
        filters = [TransformationsFilter(OffsetY=10)]
        ttfs = compileInterpolatableTTFs(ufos, filters=filters)

        for i, ttf in enumerate(ttfs):
            glyph = ufos[i]["a"]
            pen1 = BoundsPen(ufos[i])
            glyph.draw(pen1)

            glyphSet = ttf.getGlyphSet()
            tt_glyph = glyphSet["uni0061"]
            pen2 = BoundsPen(glyphSet)
            tt_glyph.draw(pen2)

            assert pen1.bounds[0] == pen2.bounds[0]
            assert pen1.bounds[1] + 10 == pen2.bounds[1]
            assert pen1.bounds[2] == pen2.bounds[2]
            assert pen1.bounds[3] + 10 == pen2.bounds[3]

    def test_compileVariableTTFs(self, designspace_v5):
        fonts = compileVariableTTFs(designspace_v5)

        # NOTE: Test dumps were generated like this:
        # for k, font in fonts.items():
        #     font.recalcTimestamp = False
        #     font["head"].created, font["head"].modified = 3570196637, 3601822698
        #     font["head"].checkSumAdjustment = 0x12345678
        #     font.saveXML(f"tests/data/DSv5/{k}-TTF.ttx")

        assert set(fonts.keys()) == {
            "MutatorSansVariable_Weight_Width",
            "MutatorSansVariable_Weight",
            "MutatorSansVariable_Width",
            "MutatorSerifVariable_Width",
        }
        # The STAT table is set to [SRIF=0, wght=[300, 700], wdth=[50, 200]] + S1 + S2
        expectTTX(
            fonts["MutatorSansVariable_Weight_Width"],
            "DSv5/MutatorSansVariable_Weight_Width-TTF.ttx",
        )
        # The STAT table is set to [SRIF=0, wght=[300, 700], wdth=50]
        expectTTX(
            fonts["MutatorSansVariable_Weight"],
            "DSv5/MutatorSansVariable_Weight-TTF.ttx",
        )
        # The STAT table is set to [SRIF=0, wght=300, wdth=[50, 200]]
        expectTTX(
            fonts["MutatorSansVariable_Width"],
            "DSv5/MutatorSansVariable_Width-TTF.ttx",
        )
        # The STAT table is set to [SRIF=1, wght=300, wdth=[50, 200]]
        expectTTX(
            fonts["MutatorSerifVariable_Width"],
            "DSv5/MutatorSerifVariable_Width-TTF.ttx",
        )

    def test_compileVariableCFF2s(self, designspace_v5):
        fonts = compileVariableCFF2s(designspace_v5)

        # NOTE: Test dumps were generated like this:
        # for k, font in fonts.items():
        #     font.recalcTimestamp = False
        #     font["head"].created, font["head"].modified = 3570196637, 3601822698
        #     font["head"].checkSumAdjustment = 0x12345678
        #     font.saveXML(f"tests/data/DSv5/{k}-CFF2.ttx")

        assert set(fonts.keys()) == {
            "MutatorSansVariable_Weight_Width",
            "MutatorSansVariable_Weight",
            "MutatorSansVariable_Width",
            "MutatorSerifVariable_Width",
        }
        # The STAT table is set to [SRIF=0, wght=[300, 700], wdth=[50, 200]] + S1 + S2
        expectTTX(
            fonts["MutatorSansVariable_Weight_Width"],
            "DSv5/MutatorSansVariable_Weight_Width-CFF2.ttx",
        )
        # The STAT table is set to [SRIF=0, wght=[300, 700], wdth=50]
        expectTTX(
            fonts["MutatorSansVariable_Weight"],
            "DSv5/MutatorSansVariable_Weight-CFF2.ttx",
        )
        # The STAT table is set to [SRIF=0, wght=300, wdth=[50, 200]]
        expectTTX(
            fonts["MutatorSansVariable_Width"],
            "DSv5/MutatorSansVariable_Width-CFF2.ttx",
        )
        # The STAT table is set to [SRIF=1, wght=300, wdth=[50, 200]]
        expectTTX(
            fonts["MutatorSerifVariable_Width"],
            "DSv5/MutatorSerifVariable_Width-CFF2.ttx",
        )

    @pytest.mark.parametrize(
        "compileFunc",
        [
            compileOTF,
            compileTTF,
        ],
    )
    def test_compile_overloaded_codepoints(self, FontClass, compileFunc):
        """Confirm that ufo2ft produces an error when compiling a UFO with
        multiple glyphs using the same codepoint. Currently only covers
        individual UFOs."""

        # Create a UFO in-memory with two glyphs using the same codepoint.
        ufo = FontClass()
        glyph_a = ufo.newGlyph("A")
        glyph_b = ufo.newGlyph("B")
        glyph_a.unicode = glyph_b.unicode = 0x0041

        # Confirm that ufo2ft raises an appropriate exception with an
        # appropriate description when compiling.
        with pytest.raises(
            InvalidFontData,
            match=re.escape("cannot map 'B' to U+0041; already mapped to 'A'"),
        ):
            _ = compileFunc(ufo)

    def test_compileTTF_glyf1_not_allQuadratic(self, testufo):
        ttf = compileTTF(testufo, allQuadratic=False)
        expectTTX(ttf, "TestFont-not-allQuadratic.ttx", tables=["glyf"])

        assert ttf["head"].glyphDataFormat == 1

    @staticmethod
    def drawCurvedContour(glyph, transform=None):
        pen = glyph.getPen()
        if transform is not None:
            pen = TransformPen(pen, transform)
        pen.moveTo((500, 0))
        pen.curveTo((500, 277.614), (388.072, 500), (250, 500))
        pen.curveTo((111.928, 500), (0, 277.614), (0, 0))
        pen.closePath()

    def test_compileVariableTTF_glyf1_not_allQuadratic(self, designspace):
        base_master = designspace.findDefault()
        assert base_master is not None
        # add a glyph with some curveTo to exercise the cu2qu codepath
        glyph = base_master.font.newGlyph("curved")
        glyph.width = 1000
        self.drawCurvedContour(glyph)

        vf = compileVariableTTF(designspace, allQuadratic=False)
        expectTTX(vf, "TestVariableFont-TTF-not-allQuadratic.ttx", tables=["glyf"])

        assert vf["head"].glyphDataFormat == 1

    def test_compileTTF_overlap_simple_flag(self, testufo):
        """Test that the OVERLAP_{SIMPLE,COMPOUND} are set on glyphs that have it"""
        testufo["a"].lib = {TRUETYPE_OVERLAP_KEY: True}
        testufo["h"].lib = {TRUETYPE_OVERLAP_KEY: True}
        ttf = compileTTF(testufo, useProductionNames=False)

        # OVERLAP_SIMPLE is set on 'a' but not on 'b'
        assert ttf["glyf"]["a"].flags[0] & flagOverlapSimple
        assert not ttf["glyf"]["b"].flags[0] & flagOverlapSimple
        # OVERLAP_COMPOUND is set on 'h' but not on 'g'
        assert not ttf["glyf"]["g"].components[0].flags & OVERLAP_COMPOUND
        assert ttf["glyf"]["h"].components[0].flags & OVERLAP_COMPOUND

    def test_compileVariableTTF_notdefGlyph_with_curves(self, designspace):
        # The test DS contains two full masters (Regular and Bold) and one intermediate
        # 'sparse' (Medium) master, which does not contain a .notdef glyph and as such
        # is supposed to inherit one from the default master. If the notdef contains
        # any curves, an error occured because these are weren't been converted to
        # quadratic: https://github.com/googlefonts/ufo2ft/issues/501

        # First we draw an additional contour containing cubic curves in the Regular
        # and Bold's .notdef glyphs
        for src_idx, transform in ((0, (1, 0, 0, 1, 0, 0)), (2, (2, 0, 0, 2, 0, 0))):
            notdef = designspace.sources[src_idx].font[".notdef"]
            self.drawCurvedContour(notdef, transform)
        assert ".notdef" not in designspace.sources[1].font.layers["Medium"]

        # this must NOT fail!
        vf = compileVariableTTF(designspace, convertCubics=True, allQuadratic=True)

        # and because allQuadratic=True, we expect .notdef contains no cubic curves
        assert not any(f & flagCubic for f in vf["glyf"][".notdef"].flags)

        # ensure .notdef has variations and was NOT dropped as incompatible,
        # varLib only warns: https://github.com/fonttools/fonttools/issues/2572
        assert ".notdef" in vf["gvar"].variations

    def test_compileVariableCFF2_sparse_notdefGlyph(self, designspace):
        # test that sparse layer without .notdef does not participate in computation
        # of CFF2 and HVAR deltas for the .notdef glypht
        for src_idx, transform in ((0, (1, 0, 0, 1, 0, 0)), (2, (2, 0, 0, 2, 0, 0))):
            notdef = designspace.sources[src_idx].font[".notdef"]
            self.drawCurvedContour(notdef, transform)
        designspace.sources[2].font[".notdef"].width *= 2
        assert ".notdef" not in designspace.sources[1].font.layers["Medium"]

        vf = compileVariableCFF2(designspace)

        expectTTX(
            vf,
            "TestVariableFont-CFF2-sparse-notdefGlyph.ttx",
            tables=["CFF2", "hmtx", "HVAR"],
        )

    @pytest.mark.parametrize("compileMethod", [compileTTF, compileOTF])
    @pytest.mark.parametrize("compression_level", [0, 9])
    def test_compile_static_font_with_gpos_compression(
        self, caplog, compileMethod, testufo, compression_level
    ):
        with caplog.at_level(logging.INFO, logger="fontTools"):
            compileMethod(testufo, ftConfig={GPOS_COMPRESSION_LEVEL: compression_level})
        disabled = compression_level == 0
        logged = "Compacting GPOS..." in caplog.text
        assert logged ^ disabled

    @pytest.mark.parametrize("compileMethod", [compileVariableTTF, compileVariableCFF2])
    @pytest.mark.parametrize("variableFeatures", [True, False])
    @pytest.mark.parametrize("compression_level", [0, 9])
    def test_compile_variable_font_with_gpos_compression(
        self, caplog, compileMethod, FontClass, variableFeatures, compression_level
    ):
        designspace = DesignSpaceDocument.fromfile(getpath("TestVarfea.designspace"))
        designspace.loadSourceFonts(FontClass)
        with caplog.at_level(logging.INFO, logger="fontTools"):
            compileMethod(
                designspace,
                ftConfig={GPOS_COMPRESSION_LEVEL: compression_level},
                variableFeatures=variableFeatures,
            )
        disabled = compression_level == 0
        logged = "Compacting GPOS..." in caplog.text
        assert logged ^ disabled

    @pytest.mark.parametrize(
        "compileMethod", [compileVariableTTFs, compileVariableCFF2s]
    )
    def test_apply_varfont_info(self, FontClass, compileMethod):
        designspace = DesignSpaceDocument.fromfile(getpath("TestVarFont.designspace"))
        designspace.loadSourceFonts(FontClass)

        fonts = compileMethod(designspace)
        assert len(fonts) == 2

        expectTTX(fonts["MyFontVF1"], "TestVarFont-MyFontVF1.ttx", ["head", "name"])
        expectTTX(fonts["MyFontVF2"], "TestVarFont-MyFontVF2.ttx", ["head", "name"])

    def test_compile_variable_ttf_drop_implied_oncurves(self, FontClass, caplog):
        # https://github.com/googlefonts/ufo2ft/pull/817
        designspace = DesignSpaceDocument.fromfile(getpath("OTestFont.designspace"))
        designspace.loadSourceFonts(FontClass)

        # dropImpliedOnCurves is False by default
        vf1 = compileVariableTTF(designspace)

        with caplog.at_level(logging.INFO, logger="fontTools.varLib"):
            vf2 = compileVariableTTF(designspace, dropImpliedOnCurves=True)

        assert "Failed to drop implied oncurves" not in caplog.text
        assert "Dropped 4 on-curve points" in caplog.text

        o1 = vf1["glyf"]["o"].coordinates
        o2 = vf2["glyf"]["o"].coordinates
        assert len(o1) == len(o2) + 4


if __name__ == "__main__":
    sys.exit(pytest.main(sys.argv))
