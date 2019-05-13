from __future__ import print_function, division, absolute_import, unicode_literals
from fontTools.misc.py23 import *
from ufo2ft import (
    compileOTF,
    compileTTF,
    compileInterpolatableTTFs,
    compileVariableTTF,
    compileVariableCFF2,
)
import warnings
import difflib
import os
import sys
import pytest


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
    with open(getpath(expectedTTX), "r", encoding="utf-8") as f:
        expected = readLines(f)
    font.recalcTimestamp = False
    font["head"].created, font["head"].modified = 3570196637, 3601822698
    font["head"].checkSumAdjustment = 0x12345678
    f = UnicodeIO()
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


class IntegrationTest(object):

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

    def test_interpolatableTTFs_lazy(self, FontClass):
        # two same UFOs **must** be interpolatable
        ufos = [FontClass(getpath("TestFont.ufo")) for _ in range(2)]
        ttfs = list(compileInterpolatableTTFs(ufos))
        expectTTX(ttfs[0], "TestFont.ttx")
        expectTTX(ttfs[1], "TestFont.ttx")

    def test_optimizeCFF_none(self, testufo):
        otf = compileOTF(testufo, optimizeCFF=0)
        expectTTX(otf, "TestFont-NoOptimize-CFF.ttx")

    def test_optimizeCFF_specialize(self, testufo):
        otf = compileOTF(testufo, optimizeCFF=1)
        expectTTX(otf, "TestFont-Specialized-CFF.ttx")

    def test_optimizeCFF_subroutinize(self, testufo):
        otf = compileOTF(testufo, optimizeCFF=2)
        expectTTX(otf, "TestFont-CFF.ttx")

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


if __name__ == "__main__":
    sys.exit(pytest.main(sys.argv))
