import pytest
from fontTools.ttLib import TTFont

from ufo2ft.infoCompiler import InfoCompiler

from .outlineCompiler_test import getpath


@pytest.fixture
def testttf():
    font = TTFont()
    font.importXML(getpath("TestFont.ttx"))
    return font


@pytest.fixture
def testufo(FontClass):
    font = FontClass(getpath("TestFont.ufo"))
    return font


class InfoCompilerTest:

    def test_head(self, testttf, testufo):
        info = {"versionMajor": 5, "versionMinor": 6}
        compiler = InfoCompiler(testttf, testufo, info)
        ttf = compiler.compile()
        assert ttf["head"].fontRevision == 5.006

    def test_hhea(self, testttf, testufo):
        info = {"openTypeHheaAscender": 100, "openTypeHheaDescender": -200}
        compiler = InfoCompiler(testttf, testufo, info)
        ttf = compiler.compile()
        assert ttf["hhea"].ascent == 100
        assert ttf["hhea"].descent == -200

    def test_vhea(self, testttf, testufo):
        info = {
            "openTypeVheaVertTypoAscender": 100,
            "openTypeVheaVertTypoDescender": -200,
        }
        compiler = InfoCompiler(testttf, testufo, info)
        ttf = compiler.compile()
        assert ttf["vhea"].ascent == 100
        assert ttf["vhea"].descent == -200

    def test_name(self, testttf, testufo):
        info = {"postscriptFontName": "TestFontOverride-Italic"}
        compiler = InfoCompiler(testttf, testufo, info)
        ttf = compiler.compile()
        assert ttf["name"].getDebugName(6) == "TestFontOverride-Italic"

    def test_OS2(self, testttf, testufo):
        info = {"openTypeOS2TypoAscender": 100, "openTypeOS2TypoDescender": -200}
        compiler = InfoCompiler(testttf, testufo, info)
        ttf = compiler.compile()
        assert ttf["OS/2"].sTypoAscender == 100
        assert ttf["OS/2"].sTypoDescender == -200

    def test_post(self, testttf, testufo):
        info = {"italicAngle": 30.6}
        compiler = InfoCompiler(testttf, testufo, info)
        ttf = compiler.compile()
        assert ttf["post"].italicAngle == 30.6

    def test_gasp(self, testttf, testufo):
        info = {
            "openTypeGaspRangeRecords": [
                {
                    "rangeMaxPPEM": 8,
                    "rangeGaspBehavior": [0, 2],
                }
            ]
        }
        compiler = InfoCompiler(testttf, testufo, info)
        ttf = compiler.compile()
        assert ttf["gasp"].gaspRange == {8: 5}
