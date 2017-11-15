from __future__ import print_function, division, absolute_import, unicode_literals

import unittest
from ufo2ft.fontInfoData import (
    getAttrWithFallback,
    normalizeStringForPostscript)


class GetAttrWithFallbackTest(unittest.TestCase):
    def test_family_and_style_names(self):
        info = TestInfoObject()

        self.assertEqual(getAttrWithFallback(info, "familyName"), "Family Name")
        self.assertEqual(getAttrWithFallback(info, "styleName"), "Style Name")

        self.assertEqual(
            getAttrWithFallback(info, "styleMapFamilyName"),
            "Family Name Style Name")
        info.styleMapFamilyName = "Style Map Family Name"
        self.assertEqual(
            getAttrWithFallback(info, "styleMapFamilyName"),
            "Style Map Family Name")

        self.assertEqual(
            getAttrWithFallback(info, "openTypeNamePreferredFamilyName"),
            "Family Name")
        self.assertEqual(
            getAttrWithFallback(info, "openTypeNamePreferredSubfamilyName"),
            "Style Name")
        self.assertEqual(
            getAttrWithFallback(info, "openTypeNameCompatibleFullName"),
            "Style Map Family Name")

    def test_redundant_metadata(self):
        info = TestInfoObject()

        self.assertEqual(
            getAttrWithFallback(info, "openTypeNameVersion"),
            "Version 0.000")
        info.versionMinor = 1
        info.versionMajor = 1
        self.assertEqual(
            getAttrWithFallback(info, "openTypeNameVersion"),
            "Version 1.001")

        self.assertEqual(
            getAttrWithFallback(info, "openTypeNameUniqueID"),
            "1.001;NONE;FamilyName-StyleName")

        self.assertEqual(getAttrWithFallback(info, "postscriptSlantAngle"), 0)
        self.assertEqual(
            getAttrWithFallback(info, "postscriptWeightName"),
            "Normal")

    def test_vertical_metrics(self):
        info = TestInfoObject()

        self.assertEqual(
            getAttrWithFallback(info, "openTypeHheaAscender"), 950)
        self.assertEqual(
            getAttrWithFallback(info, "openTypeHheaDescender"), -250)

        self.assertEqual(
            getAttrWithFallback(info, "openTypeOS2TypoAscender"), 650)
        self.assertEqual(
            getAttrWithFallback(info, "openTypeOS2TypoDescender"), -250)
        self.assertEqual(
            getAttrWithFallback(info, "openTypeOS2WinAscent"), 950)
        self.assertEqual(
            getAttrWithFallback(info, "openTypeOS2WinDescent"), 250)

    def test_caret_slope(self):
        info = TestInfoObject()

        self.assertEqual(
            getAttrWithFallback(info, "openTypeHheaCaretSlopeRise"), 1)
        self.assertEqual(
            getAttrWithFallback(info, "openTypeHheaCaretSlopeRun"), 0)

        info.italicAngle = -12
        self.assertEqual(
            getAttrWithFallback(info, "openTypeHheaCaretSlopeRise"), 1000)
        self.assertEqual(
            getAttrWithFallback(info, "openTypeHheaCaretSlopeRun"), 213)

        info.italicAngle = 12
        self.assertEqual(
            getAttrWithFallback(info, "openTypeHheaCaretSlopeRise"), 1000)
        self.assertEqual(
            getAttrWithFallback(info, "openTypeHheaCaretSlopeRun"), -213)

        info.openTypeHheaCaretSlopeRise = 2048
        self.assertFalse(hasattr(info, "openTypeHheaCaretSlopeRun"))
        self.assertEqual(
            getAttrWithFallback(info, "openTypeHheaCaretSlopeRise"), 2048)
        self.assertEqual(
            getAttrWithFallback(info, "openTypeHheaCaretSlopeRun"), -435)

        del info.openTypeHheaCaretSlopeRise
        info.openTypeHheaCaretSlopeRun = 200
        self.assertFalse(hasattr(info, "openTypeHheaCaretSlopeRise"))
        self.assertEqual(
            getAttrWithFallback(info, "openTypeHheaCaretSlopeRise"), -941)
        self.assertEqual(
            getAttrWithFallback(info, "openTypeHheaCaretSlopeRun"), 200)


class PostscriptBlueScaleFallbackTest(unittest.TestCase):

    def test_without_blue_zones(self):
        info = TestInfoObject()
        postscriptBlueScale = getAttrWithFallback(info, "postscriptBlueScale")
        self.assertEqual(postscriptBlueScale, 0.039625)

    def test_with_blue_zones(self):
        info = TestInfoObject()
        info.postscriptBlueValues = [-13, 0, 470, 483, 534, 547, 556, 569,
                                     654, 667, 677, 690, 738, 758]
        info.postscriptOtherBlues = [-255, -245]
        postscriptBlueScale = getAttrWithFallback(info, "postscriptBlueScale")
        self.assertEqual(postscriptBlueScale, 0.0375)


class NormalizeStringForPostscriptTest(unittest.TestCase):
    def test_no_change(self):
        self.assertEqual(
            normalizeStringForPostscript('Sample copyright notice.'),
            "Sample copyright notice.")


class TestInfoObject(object):
    def __init__(self):
        self.familyName = "Family Name"
        self.styleName = "Style Name"
        self.unitsPerEm = 1000
        self.descender = -250
        self.xHeight = 450
        self.capHeight = 600
        self.ascender = 650
        self.italicAngle = 0
        self.openTypeHheaCaretSlopeRiseFallback = None
        self.openTypeHheaCaretSlopeRunFallback = None

if __name__ == "__main__":
    import sys
    sys.exit(unittest.main())

