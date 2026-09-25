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

    def test_name_stat_value_keeps_its_string_when_style_name_changes(
        self, testttf, testufo
    ):
        # The STAT built from the default master may point an axis value at a
        # standard name ID whose string matched, e.g. name ID 2 "Regular" for
        # the elidable default label. When the variable font's fontinfo renames
        # name ID 2, the axis value must keep saying "Regular". The default label
        # is often the same string on several axes; those axis values share one
        # name record and must keep sharing it after the move.
        from fontTools.otlLib.builder import buildStatTable

        assert testttf["name"].getDebugName(2) == "Regular"
        buildStatTable(
            testttf,
            [
                dict(
                    tag="wght",
                    name="Weight",
                    values=[
                        dict(value=400, name="Regular", flags=0x2),
                        dict(value=700, name="Bold"),
                    ],
                ),
                dict(
                    tag="wdth",
                    name="Width",
                    values=[dict(value=100, name="Regular", flags=0x2)],
                ),
            ],
            windowsNames=True,
            macNames=False,
        )
        stat = testttf["STAT"].table
        assert [v.ValueNameID for v in stat.AxisValueArray.AxisValue][::2] == [2, 2]

        info = {"styleName": "Italic", "styleMapStyleName": "italic"}
        compiler = InfoCompiler(testttf, testufo, info)
        ttf = compiler.compile()

        name = ttf["name"]
        assert name.getDebugName(2) == "Italic"
        values = ttf["STAT"].table.AxisValueArray.AxisValue
        assert [name.getDebugName(v.ValueNameID) for v in values] == [
            "Regular",
            "Bold",
            "Regular",
        ]
        assert values[0].ValueNameID >= 256
        assert values[2].ValueNameID == values[0].ValueNameID
        assert [n.nameID for n in name.names if n.toUnicode() == "Regular"] == [
            values[0].ValueNameID
        ]

    def test_OS2(self, testttf, testufo):
        info = {
            "openTypeOS2TypoAscender": 100,
            "openTypeOS2TypoDescender": -200,
            "openTypeOS2CodePageRanges": [0, 1, 2, 3, 32, 32 + 1, 32 + 2, 32 + 3],
        }
        compiler = InfoCompiler(testttf, testufo, info)
        ttf = compiler.compile()
        assert ttf["OS/2"].sTypoAscender == 100
        assert ttf["OS/2"].sTypoDescender == -200
        assert ttf["OS/2"].ulCodePageRange1 == 0b1111
        assert ttf["OS/2"].ulCodePageRange2 == 0b1111

    def test_OS2_dont_overwrite_codePageRanges(self, testttf, testufo):
        # if the variable-font's 'public.fontInfo' lib key does not override the
        # openTypeOS2CodePageRanges, we should keep the original values as defined
        # or computed for the default master TTF.
        ulCodePageRange1 = testttf["OS/2"].ulCodePageRange1
        ulCodePageRange2 = testttf["OS/2"].ulCodePageRange2
        testufo.info.openTypeOS2CodePageRanges = None
        info = {}
        compiler = InfoCompiler(testttf, testufo, info)
        ttf = compiler.compile()
        assert ttf["OS/2"].ulCodePageRange1 == ulCodePageRange1
        assert ttf["OS/2"].ulCodePageRange2 == ulCodePageRange2

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
