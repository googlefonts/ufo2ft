import os
import random
import time

import pytest

from ufo2ft.fontInfoData import (
    dateStringToTimeValue,
    getAttrWithFallback,
    normalizeStringForPostscript,
)


@pytest.fixture
def info(InfoClass):
    self = InfoClass()
    self.familyName = "Family Name"
    self.styleName = "Style Name"
    self.unitsPerEm = 1000
    self.descender = -250
    self.xHeight = 450
    self.capHeight = 600
    self.ascender = 650
    self.italicAngle = 0
    return self


class GetAttrWithFallbackTest:
    @pytest.mark.parametrize(
        "infoDict,expected",
        [
            # no styleMapFamilyName, no styleMapStyleName
            (
                {},
                {
                    "familyName": "Family Name",
                    "styleName": "Style Name",
                    "styleMapFamilyName": "Family Name Style Name",
                    "styleMapStyleName": "regular",
                    "openTypeNamePreferredFamilyName": "Family Name",
                    "openTypeNamePreferredSubfamilyName": "Style Name",
                },
            ),
            # no styleMapStyleName
            (
                {"styleMapFamilyName": "Style Map Family Name"},
                {
                    "styleMapFamilyName": "Style Map Family Name",
                    "styleMapStyleName": "regular",
                    "openTypeNamePreferredFamilyName": "Family Name",
                    "openTypeNamePreferredSubfamilyName": "Style Name",
                },
            ),
            # no styleMapFamilyName, no styleMapStyleName but styleName="Regular"
            (
                {"styleName": "Regular"},
                {
                    "familyName": "Family Name",
                    "styleName": "Regular",
                    "styleMapFamilyName": "Family Name",
                    "styleMapStyleName": "regular",
                    "openTypeNamePreferredFamilyName": "Family Name",
                    "openTypeNamePreferredSubfamilyName": "Regular",
                },
            ),
            # no styleMapFamilyName but styleName="Regular"
            (
                {"styleName": "Regular", "styleMapStyleName": "regular"},
                {
                    "styleMapFamilyName": "Family Name",
                    "styleMapStyleName": "regular",
                    "openTypeNamePreferredFamilyName": "Family Name",
                    "openTypeNamePreferredSubfamilyName": "Regular",
                },
            ),
            # no styleMapStyleName but styleName="Regular"
            (
                {"styleName": "Regular", "styleMapFamilyName": "Style Map Family Name"},
                {
                    "styleMapFamilyName": "Style Map Family Name",
                    "styleMapStyleName": "regular",
                    "openTypeNamePreferredFamilyName": "Family Name",
                    "openTypeNamePreferredSubfamilyName": "Regular",
                },
            ),
            # no styleMapFamilyName, no styleMapStyleName but styleName="Bold"
            (
                {"styleName": "Bold"},
                {
                    "familyName": "Family Name",
                    "styleName": "Bold",
                    "styleMapFamilyName": "Family Name",
                    "styleMapStyleName": "bold",
                    "openTypeNamePreferredFamilyName": "Family Name",
                    "openTypeNamePreferredSubfamilyName": "Bold",
                },
            ),
        ],
    )
    def test_family_and_style_names(self, info, infoDict, expected):
        for key, value in infoDict.items():
            setattr(info, key, value)
        for key, value in expected.items():
            assert getAttrWithFallback(info, key) == value

    def test_redundant_metadata(self, info):
        assert getAttrWithFallback(info, "openTypeNameVersion") == "Version 0.000"

        info.versionMinor = 1
        info.versionMajor = 1
        assert getAttrWithFallback(info, "openTypeNameVersion") == "Version 1.001"

        assert (
            getAttrWithFallback(info, "openTypeNameUniqueID")
            == "1.001;NONE;FamilyName-StyleName"
        )

        assert getAttrWithFallback(info, "postscriptSlantAngle") == 0

    def test_unecessary_metadata(self, info):
        assert getAttrWithFallback(info, "postscriptWeightName") is None

        info.postscriptWeightName = "Normal"
        assert getAttrWithFallback(info, "postscriptWeightName") == "Normal"

    def test_vertical_metrics(self, info):
        assert getAttrWithFallback(info, "openTypeHheaAscender") == 950
        assert getAttrWithFallback(info, "openTypeHheaDescender") == -250

        assert getAttrWithFallback(info, "openTypeOS2TypoAscender") == 650
        assert getAttrWithFallback(info, "openTypeOS2TypoDescender") == -250
        assert getAttrWithFallback(info, "openTypeOS2WinAscent") == 950
        assert getAttrWithFallback(info, "openTypeOS2WinDescent") == 250

    def test_caret_slope(self, info):
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRise") == 1
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRun") == 0

        info.italicAngle = -12
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRise") == 1000
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRun") == 213

        info.italicAngle = 12
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRise") == 1000
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRun") == -213

        info.openTypeHheaCaretSlopeRise = 2048
        assert info.openTypeHheaCaretSlopeRun is None
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRise") == 2048
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRun") == -435

        info.openTypeHheaCaretSlopeRise = None
        info.openTypeHheaCaretSlopeRun = 200
        assert info.openTypeHheaCaretSlopeRise is None
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRise") == -941
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRun") == 200

    def test_head_created(self, info):
        os.environ["SOURCE_DATE_EPOCH"] = "1514485183"
        try:
            assert (
                getAttrWithFallback(info, "openTypeHeadCreated")
                == "2017/12/28 18:19:43"
            )
        finally:
            del os.environ["SOURCE_DATE_EPOCH"]
        assert getAttrWithFallback(info, "openTypeHeadCreated") != "2017/12/28 18:19:43"

    def test_empty_info(self, InfoClass):
        info = InfoClass()
        assert getAttrWithFallback(info, "familyName") == "New Font"
        assert getAttrWithFallback(info, "styleName") == "Regular"
        assert getAttrWithFallback(info, "unitsPerEm") == 1000
        assert getAttrWithFallback(info, "ascender") == 800
        assert getAttrWithFallback(info, "capHeight") == 700
        assert getAttrWithFallback(info, "xHeight") == 500
        assert getAttrWithFallback(info, "descender") == -200

    def test_empty_info_2048(self, InfoClass):
        info = InfoClass()
        info.unitsPerEm = 2048
        assert getAttrWithFallback(info, "unitsPerEm") == 2048
        assert getAttrWithFallback(info, "ascender") == 1638
        assert getAttrWithFallback(info, "capHeight") == 1434
        assert getAttrWithFallback(info, "xHeight") == 1024
        assert getAttrWithFallback(info, "descender") == -410


class PostscriptBlueScaleFallbackTest:
    def test_without_blue_zones(self, info):
        postscriptBlueScale = getAttrWithFallback(info, "postscriptBlueScale")
        assert postscriptBlueScale == 0.039625

    def test_with_blue_zones(self, info):
        info.postscriptBlueValues = [
            -13,
            0,
            470,
            483,
            534,
            547,
            556,
            569,
            654,
            667,
            677,
            690,
            738,
            758,
        ]
        info.postscriptOtherBlues = [-255, -245]
        postscriptBlueScale = getAttrWithFallback(info, "postscriptBlueScale")
        assert postscriptBlueScale == 0.0375


class NormalizeStringForPostscriptTest:
    def test_no_change(self):
        assert (
            normalizeStringForPostscript("Sample copyright notice.")
            == "Sample copyright notice."
        )


class DateStringToTimeValueTest:
    def test_roundtrip_random_timestamp(self):
        timestamp = random.randint(0, 10 ** 9)
        ds = time.strftime("%Y/%m/%d %H:%M:%S", time.gmtime(timestamp))
        assert dateStringToTimeValue(ds) == timestamp


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main(sys.argv))
