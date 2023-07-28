import difflib
import io
import os
import re
import sys
from pathlib import Path

import pytest
from fontTools.pens.boundsPen import BoundsPen

from ufo2ft import (
    compileInterpolatableTTFs,
    compileOTF,
    compileTTF,
    compileVariableCFF2,
    compileVariableCFF2s,
    compileVariableTTF,
    compileVariableTTFs,
)
from ufo2ft.constants import KEEP_GLYPH_NAMES
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

        assert "### LayerFont-Regular ###" in tmp.getvalue()
        assert "### LayerFont-Bold ###" in tmp.getvalue()

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

    def test_compileVariableTTF_glyf1_not_allQuadratic(self, designspace):
        base_master = designspace.findDefault()
        assert base_master is not None
        # add a glyph with some curveTo to exercise the cu2qu codepath
        glyph = base_master.font.newGlyph("curved")
        glyph.width = 1000
        pen = glyph.getPen()
        pen.moveTo((500, 0))
        pen.curveTo((500, 277.614), (388.072, 500), (250, 500))
        pen.curveTo((111.928, 500), (0, 277.614), (0, 0))
        pen.closePath()

        vf = compileVariableTTF(designspace, allQuadratic=False)
        expectTTX(vf, "TestVariableFont-TTF-not-allQuadratic.ttx", tables=["glyf"])

        assert vf["head"].glyphDataFormat == 1


if __name__ == "__main__":
    sys.exit(pytest.main(sys.argv))
