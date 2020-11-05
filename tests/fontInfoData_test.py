from __future__ import print_function, division, absolute_import, unicode_literals

import os
import random
import time
from ufo2ft.fontInfoData import (
    getAttrWithFallback,
    normalizeStringForPostscript,
    dateStringToTimeValue,
)
import pytest


@pytest.fixture
def info(InfoClass):
    """
    Returns info about the class

    Args:
        InfoClass: (todo): write your description
    """
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


class GetAttrWithFallbackTest(object):
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
        """
        Test if the information in the configuration file.

        Args:
            self: (todo): write your description
            info: (todo): write your description
            infoDict: (dict): write your description
            expected: (dict): write your description
        """
        for key, value in infoDict.items():
            setattr(info, key, value)
        for key, value in expected.items():
            assert getAttrWithFallback(info, key) == value

    def test_redundant_metadata(self, info):
        """
        Redundant metadata.

        Args:
            self: (todo): write your description
            info: (todo): write your description
        """
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
        """
        Determine the metadata.

        Args:
            self: (todo): write your description
            info: (todo): write your description
        """
        assert getAttrWithFallback(info, "postscriptWeightName") is None

        info.postscriptWeightName = "Normal"
        assert getAttrWithFallback(info, "postscriptWeightName") == "Normal"

    def test_vertical_metrics(self, info):
        """
        Test for backward backward metrics.

        Args:
            self: (todo): write your description
            info: (todo): write your description
        """
        assert getAttrWithFallback(info, "openTypeHheaAscender") == 950
        assert getAttrWithFallback(info, "openTypeHheaDescender") == -250

        assert getAttrWithFallback(info, "openTypeOS2TypoAscender") == 650
        assert getAttrWithFallback(info, "openTypeOS2TypoDescender") == -250
        assert getAttrWithFallback(info, "openTypeOS2WinAscent") == 950
        assert getAttrWithFallback(info, "openTypeOS2WinDescent") == 250

    def test_caret_slope(self, info):
        """
        Test out slope * info

        Args:
            self: (todo): write your description
            info: (todo): write your description
        """
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRise") == 1
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRun") == 0

        info.italicAngle = -12
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRise") == 1000
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRun") == 213

        info.italicAngle = 12
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRise") == 1000
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRun") == -213

        info.openTypeHheaCaretSlopeRise = 2048
        assert getattr(info, "openTypeHheaCaretSlopeRun") is None
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRise") == 2048
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRun") == -435

        info.openTypeHheaCaretSlopeRise = None
        info.openTypeHheaCaretSlopeRun = 200
        assert getattr(info, "openTypeHheaCaretSlopeRise") is None
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRise") == -941
        assert getAttrWithFallback(info, "openTypeHheaCaretSlopeRun") == 200

    def test_head_created(self, info):
        """
        Test if the head was created.

        Args:
            self: (todo): write your description
            info: (todo): write your description
        """
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
        """
        Test if an empty info class

        Args:
            self: (todo): write your description
            InfoClass: (todo): write your description
        """
        info = InfoClass()
        assert getAttrWithFallback(info, "familyName") == "New Font"
        assert getAttrWithFallback(info, "styleName") == "Regular"
        assert getAttrWithFallback(info, "unitsPerEm") == 1000
        assert getAttrWithFallback(info, "ascender") == 800
        assert getAttrWithFallback(info, "capHeight") == 700
        assert getAttrWithFallback(info, "xHeight") == 500
        assert getAttrWithFallback(info, "descender") == -200

    def test_empty_info_2048(self, InfoClass):
        """
        Test if the info class is empty.

        Args:
            self: (todo): write your description
            InfoClass: (todo): write your description
        """
        info = InfoClass()
        info.unitsPerEm = 2048
        assert getAttrWithFallback(info, "unitsPerEm") == 2048
        assert getAttrWithFallback(info, "ascender") == 1638
        assert getAttrWithFallback(info, "capHeight") == 1434
        assert getAttrWithFallback(info, "xHeight") == 1024
        assert getAttrWithFallback(info, "descender") == -410


class PostscriptBlueScaleFallbackTest(object):
    def test_without_blue_zones(self, info):
        """
        Test if the zonescript zonescript *

        Args:
            self: (todo): write your description
            info: (todo): write your description
        """
        postscriptBlueScale = getAttrWithFallback(info, "postscriptBlueScale")
        assert postscriptBlueScale == 0.039625

    def test_with_blue_zones(self, info):
        """
        Test if zone zone dim dim dims.

        Args:
            self: (todo): write your description
            info: (todo): write your description
        """
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


class NormalizeStringForPostscriptTest(object):
    def test_no_change(self):
        """
        Test if any change of a changescript.

        Args:
            self: (todo): write your description
        """
        assert (
            normalizeStringForPostscript("Sample copyright notice.")
            == "Sample copyright notice."
        )


class DateStringToTimeValueTest(object):
    def test_roundtrip_random_timestamp(self):
        """
        Round a random datetime.

        Args:
            self: (todo): write your description
        """
        timestamp = random.randint(0, 10 ** 9)
        ds = time.strftime("%Y/%m/%d %H:%M:%S", time.gmtime(timestamp))
        assert dateStringToTimeValue(ds) == timestamp


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main(sys.argv))
