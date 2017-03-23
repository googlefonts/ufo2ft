from __future__ import print_function, division, absolute_import, unicode_literals
from fontTools.misc.py23 import tounicode, round

import logging
import math
from collections import Counter, namedtuple

from fontTools.ttLib import TTFont, newTable
from fontTools.cffLib import TopDictIndex, TopDict, CharStrings, SubrsIndex, GlobalSubrsIndex, PrivateDict, IndexedStrings
from fontTools.pens.boundsPen import BoundsPen, ControlBoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables.O_S_2f_2 import Panose
from fontTools.ttLib.tables._h_e_a_d import mac_epoch_diff
from fontTools.ttLib.tables._g_l_y_f import USE_MY_METRICS
from fontTools.misc.arrayTools import unionRect

from ufo2ft.fontInfoData import getAttrWithFallback, dateStringToTimeValue, dateStringForNow, intListToNum, normalizeStringForPostscript

logger = logging.getLogger(__name__)


BoundingBox = namedtuple("BoundingBox", ["xMin", "yMin", "xMax", "yMax"])


def _isNonBMP(s):
    for c in s:
        if ord(c) > 65535:
            return True
    return False


def _getVerticalOrigin(glyph):
    height = glyph.height
    if (hasattr(glyph, "verticalOrigin") and
            glyph.verticalOrigin is not None):
        verticalOrigin = glyph.verticalOrigin
    else:
        verticalOrigin = height
    return round(verticalOrigin)


class BaseOutlineCompiler(object):
    """Create a feature-less outline binary."""

    sfntVersion = None

    def __init__(self, font, glyphOrder=None):
        self.ufo = font
        self.log = []
        # make any missing glyphs and store them locally
        missingRequiredGlyphs = self.makeMissingRequiredGlyphs()
        # make a dict of all glyphs
        self.allGlyphs = {}
        for glyph in font:
            self.allGlyphs[glyph.name] = glyph
        self.allGlyphs.update(missingRequiredGlyphs)
        # store the glyph order
        if glyphOrder is None:
            if hasattr(font, 'glyphOrder'):
                glyphOrder = font.glyphOrder
            else:
                glyphOrder = sorted(self.allGlyphs.keys())
        self.glyphOrder = self.makeOfficialGlyphOrder(glyphOrder)
        # make reusable glyphs/font bounding boxes
        self.glyphBoundingBoxes = self.makeGlyphsBoundingBoxes()
        self.fontBoundingBox = self.makeFontBoundingBox()
        # make a reusable character mapping
        self.unicodeToGlyphNameMapping = self.makeUnicodeToGlyphNameMapping()

    def compile(self):
        """
        Compile the OpenType binary.
        """
        self.otf = TTFont(sfntVersion=self.sfntVersion)

        self.vertical = False
        for glyph in self.allGlyphs.values():
            if (hasattr(glyph, "verticalOrigin") and
                    glyph.verticalOrigin is not None):
                self.vertical = True
                break

        # populate basic tables
        self.setupTable_head()
        self.setupTable_hmtx()
        self.setupTable_hhea()
        self.setupTable_name()
        self.setupTable_maxp()
        self.setupTable_cmap()
        self.setupTable_OS2()
        self.setupTable_post()
        if self.vertical:
            self.setupTable_vmtx()
            self.setupTable_vhea()
        self.setupOtherTables()

        return self.otf

    def makeGlyphsBoundingBoxes(self):
        """
        Make bounding boxes for all the glyphs, and return a dictionary of
        BoundingBox(xMin, xMax, yMin, yMax) namedtuples keyed by glyph names.
        The bounding box of empty glyphs (without contours or components) is
        set to None.

        Float values are rounded to integers using the built-in round().

        **This should not be called externally.** Subclasses
        may override this method to handle the bounds creation
        in a different way if desired.
        """
        glyphBoxes = {}
        for glyphName, glyph in self.allGlyphs.items():
            bounds = None
            if glyph or glyph.components:
                bounds = glyph.controlPointBounds
                if bounds:
                    bounds = BoundingBox(*(round(v) for v in bounds))
            glyphBoxes[glyphName] = bounds
        return glyphBoxes

    def makeFontBoundingBox(self):
        """
        Make a bounding box for the font.

        **This should not be called externally.** Subclasses
        may override this method to handle the bounds creation
        in a different way if desired.
        """
        if not hasattr(self, "glyphBoundingBoxes"):
            self.glyphBoundingBoxes = self.makeGlyphsBoundingBoxes()
        fontBox = None
        for glyphName, glyphBox in self.glyphBoundingBoxes.items():
            if glyphBox is None:
                continue
            if fontBox is None:
                fontBox = glyphBox
            else:
                fontBox = unionRect(fontBox, glyphBox)
        if fontBox is None:  # unlikely
            fontBox = BoundingBox(0, 0, 0, 0)
        return fontBox

    def makeUnicodeToGlyphNameMapping(self):
        """
        Make a ``unicode : glyph name`` mapping for the font.

        **This should not be called externally.** Subclasses
        may override this method to handle the mapping creation
        in a different way if desired.
        """
        mapping = {}
        for glyphName, glyph in self.allGlyphs.items():
            unicodes = glyph.unicodes
            for uni in unicodes:
                mapping[uni] = glyphName
        return mapping

    def makeMissingRequiredGlyphs(self):
        """
        Add .notdef to the font if it is not present.

        **This should not be called externally.** Subclasses
        may override this method to handle the glyph creation
        in a different way if desired.
        """
        glyphs = {}
        font = self.ufo
        unitsPerEm = round(getAttrWithFallback(font.info, "unitsPerEm"))
        ascender = round(getAttrWithFallback(font.info, "ascender"))
        descender = round(getAttrWithFallback(font.info, "descender"))
        defaultWidth = round(unitsPerEm * 0.5)
        if ".notdef" not in self.ufo:
            glyphs[".notdef"] = StubGlyph(name=".notdef", width=defaultWidth, unitsPerEm=unitsPerEm, ascender=ascender, descender=descender)
        return glyphs

    def makeOfficialGlyphOrder(self, glyphOrder):
        """
        Make a the final glyph order.

        **This should not be called externally.** Subclasses
        may override this method to handle the order creation
        in a different way if desired.
        """

        orderedGlyphs = [".notdef"]
        for glyphName in glyphOrder:
            if glyphName == ".notdef":
                continue
            if glyphName not in self.ufo:
                continue
            orderedGlyphs.append(glyphName)
        for glyphName in sorted(self.allGlyphs.keys()):
            if glyphName not in orderedGlyphs:
                orderedGlyphs.append(glyphName)
        return orderedGlyphs

    # --------------
    # Table Builders
    # --------------

    def setupTable_gasp(self):
        self.otf["gasp"] = gasp = newTable("gasp")
        gasp_ranges = dict()
        for record in self.ufo.info.openTypeGaspRangeRecords:
            rangeMaxPPEM = record["rangeMaxPPEM"]
            behavior_bits = record["rangeGaspBehavior"]
            rangeGaspBehavior = intListToNum(behavior_bits, 0, 4)
            gasp_ranges[rangeMaxPPEM] = rangeGaspBehavior
        gasp.gaspRange = gasp_ranges

    def setupTable_head(self):
        """
        Make the head table.

        **This should not be called externally.** Subclasses
        may override or supplement this method to handle the
        table creation in a different way if desired.
        """

        self.otf["head"] = head = newTable("head")
        font = self.ufo
        head.checkSumAdjustment = 0
        head.tableVersion = 1.0
        head.magicNumber = 0x5F0F3CF5

        # version numbers
        # limit minor version to 3 digits as recommended in OpenType spec:
        # https://www.microsoft.com/typography/otspec/recom.htm
        versionMajor = getAttrWithFallback(font.info, "versionMajor")
        versionMinor = getAttrWithFallback(font.info, "versionMinor")
        fullFontRevision = float("%d.%03d" % (versionMajor, versionMinor))
        head.fontRevision = round(fullFontRevision, 3)
        if head.fontRevision != fullFontRevision:
            logger.warning(
                "Minor version in %s has too many digits and won't fit into "
                "the head table's fontRevision field; rounded to %s.",
                fullFontRevision, head.fontRevision)

        # upm
        head.unitsPerEm = getAttrWithFallback(font.info, "unitsPerEm")

        # times
        head.created = dateStringToTimeValue(getAttrWithFallback(font.info, "openTypeHeadCreated")) - mac_epoch_diff
        head.modified = dateStringToTimeValue(dateStringForNow()) - mac_epoch_diff

        # bounding box
        xMin, yMin, xMax, yMax = self.fontBoundingBox
        head.xMin = xMin
        head.yMin = yMin
        head.xMax = xMax
        head.yMax = yMax

        # style mapping
        styleMapStyleName = getAttrWithFallback(font.info, "styleMapStyleName")
        macStyle = []
        if styleMapStyleName == "bold":
            macStyle = [0]
        elif styleMapStyleName == "bold italic":
            macStyle = [0, 1]
        elif styleMapStyleName == "italic":
            macStyle = [1]
        head.macStyle = intListToNum(macStyle, 0, 16)

        # misc
        head.flags = intListToNum(getAttrWithFallback(font.info, "openTypeHeadFlags"), 0, 16)
        head.lowestRecPPEM = round(getAttrWithFallback(font.info, "openTypeHeadLowestRecPPEM"))
        head.fontDirectionHint = 2
        head.indexToLocFormat = 0
        head.glyphDataFormat = 0

    def setupTable_name(self):
        """
        Make the name table.

        **This should not be called externally.** Subclasses
        may override or supplement this method to handle the
        table creation in a different way if desired.
        """

        font = self.ufo
        self.otf["name"] = name = newTable("name")
        name.names = []

        # Set name records from font.info.openTypeNameRecords
        for nameRecord in getAttrWithFallback(
                font.info, "openTypeNameRecords"):
            nameId = nameRecord["nameID"]
            platformId = nameRecord["platformID"]
            platEncId = nameRecord["encodingID"]
            langId = nameRecord["languageID"]
            # on Python 2, plistLib (used by ufoLib) returns unicode strings
            # only when plist data contain non-ascii characters, and returns
            # ascii-encoded bytes when it can. On the other hand, fontTools's
            # name table `setName` method wants unicode strings, so we must
            # decode them first
            nameVal = tounicode(nameRecord["string"], encoding='ascii')
            name.setName(nameVal, nameId, platformId, platEncId, langId)

        # Build name records
        familyName = getAttrWithFallback(font.info, "styleMapFamilyName")
        styleName = getAttrWithFallback(font.info, "styleMapStyleName").title()

        # If name ID 2 is "Regular", it can be omitted from name ID 4
        fullName = familyName
        if styleName != "Regular":
            fullName += " %s" % styleName

        nameVals = {
            0: getAttrWithFallback(font.info, "copyright"),
            1: familyName,
            2: styleName,
            3: getAttrWithFallback(font.info, "openTypeNameUniqueID"),
            4: fullName,
            5: getAttrWithFallback(font.info, "openTypeNameVersion"),
            6: getAttrWithFallback(font.info, "postscriptFontName"),
            7: getAttrWithFallback(font.info, "trademark"),
            8: getAttrWithFallback(font.info, "openTypeNameManufacturer"),
            9: getAttrWithFallback(font.info, "openTypeNameDesigner"),
            10: getAttrWithFallback(font.info, "openTypeNameDescription"),
            11: getAttrWithFallback(font.info, "openTypeNameManufacturerURL"),
            12: getAttrWithFallback(font.info, "openTypeNameDesignerURL"),
            13: getAttrWithFallback(font.info, "openTypeNameLicense"),
            14: getAttrWithFallback(font.info, "openTypeNameLicenseURL"),
            16: getAttrWithFallback(
                font.info, "openTypeNamePreferredFamilyName"),
            17: getAttrWithFallback(
                font.info, "openTypeNamePreferredSubfamilyName"),
        }

        # don't add typographic names if they are the same as the legacy ones
        if nameVals[1] == nameVals[16]:
            del nameVals[16]
        if nameVals[2] == nameVals[17]:
            del nameVals[17]
        # postscript font name
        if nameVals[6]:
            nameVals[6] = normalizeStringForPostscript(nameVals[6])

        for nameId in sorted(nameVals.keys()):
            nameVal = nameVals[nameId]
            if not nameVal:
                continue
            nameVal = tounicode(nameVal, encoding='ascii')
            platformId = 3
            platEncId = 10 if _isNonBMP(nameVal) else 1
            langId = 0x409
            # Set built name record if not set yet
            if name.getName(nameId, platformId, platEncId, langId):
                continue
            name.setName(nameVal, nameId, platformId, platEncId, langId)

    def setupTable_maxp(self):
        """
        Make the maxp table.

        **This should not be called externally.** Subclasses
        must override or supplement this method to handle the
        table creation for either CFF or TT data.
        """
        raise NotImplementedError

    def setupTable_cmap(self):
        """
        Make the cmap table.

        **This should not be called externally.** Subclasses
        may override or supplement this method to handle the
        table creation in a different way if desired.
        """
        from fontTools.ttLib.tables._c_m_a_p import cmap_format_4

        nonBMP = dict((k,v) for k,v in self.unicodeToGlyphNameMapping.items() if k > 65535)
        if nonBMP:
            mapping = dict((k,v) for k,v in self.unicodeToGlyphNameMapping.items() if k <= 65535)
        else:
            mapping = dict(self.unicodeToGlyphNameMapping)
        # mac
        cmap4_0_3 = cmap_format_4(4)
        cmap4_0_3.platformID = 0
        cmap4_0_3.platEncID = 3
        cmap4_0_3.language = 0
        cmap4_0_3.cmap = mapping
        # windows
        cmap4_3_1 = cmap_format_4(4)
        cmap4_3_1.platformID = 3
        cmap4_3_1.platEncID = 1
        cmap4_3_1.language = 0
        cmap4_3_1.cmap = mapping
        # store
        self.otf["cmap"] = cmap = newTable("cmap")
        cmap.tableVersion = 0
        cmap.tables = [cmap4_0_3, cmap4_3_1]
        # If we have glyphs outside Unicode BMP, we must set another
        # subtable that can hold longer codepoints for them.
        if nonBMP:
            from fontTools.ttLib.tables._c_m_a_p import cmap_format_12
            nonBMP.update(mapping)
            # mac
            cmap12_0_4 = cmap_format_12(12)
            cmap12_0_4.platformID = 0
            cmap12_0_4.platEncID = 4
            cmap12_0_4.language = 0
            cmap12_0_4.cmap = nonBMP
            # windows
            cmap12_3_10 = cmap_format_12(12)
            cmap12_3_10.platformID = 3
            cmap12_3_10.platEncID = 10
            cmap12_3_10.language = 0
            cmap12_3_10.cmap = nonBMP
            # update tables registry
            cmap.tables = [cmap4_0_3, cmap4_3_1, cmap12_0_4, cmap12_3_10]

    def setupTable_OS2(self):
        """
        Make the OS/2 table.

        **This should not be called externally.** Subclasses
        may override or supplement this method to handle the
        table creation in a different way if desired.
        """
        self.otf["OS/2"] = os2 = newTable("OS/2")
        font = self.ufo
        os2.version = 0x0004
        # average glyph width
        widths = [glyph.width for glyph in self.allGlyphs.values() if glyph.width > 0]
        os2.xAvgCharWidth = round(sum(widths) / len(widths))
        # weight and width classes
        os2.usWeightClass = getAttrWithFallback(font.info, "openTypeOS2WeightClass")
        os2.usWidthClass = getAttrWithFallback(font.info, "openTypeOS2WidthClass")
        # embedding
        os2.fsType = intListToNum(getAttrWithFallback(font.info, "openTypeOS2Type"), 0, 16)

        # subscript, superscript, strikeout values, taken from AFDKO:
        # FDK/Tools/Programs/makeotf/makeotf_lib/source/hotconv/hot.c
        unitsPerEm = getAttrWithFallback(font.info, "unitsPerEm")
        italicAngle = getAttrWithFallback(font.info, "italicAngle")
        xHeight = getAttrWithFallback(font.info, "xHeight")
        def adjustOffset(offset, angle):
            """Adjust Y offset based on italic angle, to get X offset."""
            return offset * math.tan(math.radians(-angle)) if angle else 0

        v = getAttrWithFallback(font.info, "openTypeOS2SubscriptXSize")
        if v is None:
            v = unitsPerEm * 0.65
        os2.ySubscriptXSize = round(v)
        v = getAttrWithFallback(font.info, "openTypeOS2SubscriptYSize")
        if v is None:
            v = unitsPerEm * 0.6
        os2.ySubscriptYSize = round(v)
        v = getAttrWithFallback(font.info, "openTypeOS2SubscriptYOffset")
        if v is None:
            v = unitsPerEm * 0.075
        os2.ySubscriptYOffset = round(v)
        v = getAttrWithFallback(font.info, "openTypeOS2SubscriptXOffset")
        if v is None:
            v = adjustOffset(-os2.ySubscriptYOffset, italicAngle)
        os2.ySubscriptXOffset = round(v)

        v = getAttrWithFallback(font.info, "openTypeOS2SuperscriptXSize")
        if v is None:
            v = os2.ySubscriptXSize
        os2.ySuperscriptXSize = round(v)
        v = getAttrWithFallback(font.info, "openTypeOS2SuperscriptYSize")
        if v is None:
            v = os2.ySubscriptYSize
        os2.ySuperscriptYSize = round(v)
        v = getAttrWithFallback(font.info, "openTypeOS2SuperscriptYOffset")
        if v is None:
            v = unitsPerEm * 0.35
        os2.ySuperscriptYOffset = round(v)
        v = getAttrWithFallback(font.info, "openTypeOS2SuperscriptXOffset")
        if v is None:
            v = adjustOffset(os2.ySuperscriptYOffset, italicAngle)
        os2.ySuperscriptXOffset = round(v)

        v = getAttrWithFallback(font.info, "openTypeOS2StrikeoutSize")
        if v is None:
            v = getAttrWithFallback(font.info, "postscriptUnderlineThickness")
        os2.yStrikeoutSize = round(v)
        v = getAttrWithFallback(font.info, "openTypeOS2StrikeoutPosition")
        if v is None:
            v = xHeight * 0.6 if xHeight else unitsPerEm * 0.22
        os2.yStrikeoutPosition = round(v)

        # family class
        ibmFontClass, ibmFontSubclass = getAttrWithFallback(
            font.info, "openTypeOS2FamilyClass")
        os2.sFamilyClass = (ibmFontClass << 8) + ibmFontSubclass
        # panose
        data = getAttrWithFallback(font.info, "openTypeOS2Panose")
        panose = Panose()
        panose.bFamilyType = data[0]
        panose.bSerifStyle = data[1]
        panose.bWeight = data[2]
        panose.bProportion = data[3]
        panose.bContrast = data[4]
        panose.bStrokeVariation = data[5]
        panose.bArmStyle = data[6]
        panose.bLetterForm = data[7]
        panose.bMidline = data[8]
        panose.bXHeight = data[9]
        os2.panose = panose
        # Unicode ranges
        uniRanges = getAttrWithFallback(font.info, "openTypeOS2UnicodeRanges")
        os2.ulUnicodeRange1 = intListToNum(uniRanges, 0, 32)
        os2.ulUnicodeRange2 = intListToNum(uniRanges, 32, 32)
        os2.ulUnicodeRange3 = intListToNum(uniRanges, 64, 32)
        os2.ulUnicodeRange4 = intListToNum(uniRanges, 96, 32)
        # codepage ranges
        codepageRanges = getAttrWithFallback(font.info, "openTypeOS2CodePageRanges")
        os2.ulCodePageRange1 = intListToNum(codepageRanges, 0, 32)
        os2.ulCodePageRange2 = intListToNum(codepageRanges, 32, 32)
        # vendor id
        os2.achVendID = tounicode(
            getAttrWithFallback(font.info, "openTypeOS2VendorID"),
            encoding="ascii", errors="ignore")
        # vertical metrics
        os2.sxHeight = round(getAttrWithFallback(font.info, "xHeight"))
        os2.sCapHeight = round(getAttrWithFallback(font.info, "capHeight"))
        os2.sTypoAscender = round(getAttrWithFallback(font.info, "openTypeOS2TypoAscender"))
        os2.sTypoDescender = round(getAttrWithFallback(font.info, "openTypeOS2TypoDescender"))
        os2.sTypoLineGap = round(getAttrWithFallback(font.info, "openTypeOS2TypoLineGap"))
        os2.usWinAscent = round(getAttrWithFallback(font.info, "openTypeOS2WinAscent"))
        os2.usWinDescent = round(getAttrWithFallback(font.info, "openTypeOS2WinDescent"))
        # style mapping
        selection = list(getAttrWithFallback(font.info, "openTypeOS2Selection"))
        styleMapStyleName = getAttrWithFallback(font.info, "styleMapStyleName")
        if styleMapStyleName == "regular":
            selection.append(6)
        elif styleMapStyleName == "bold":
            selection.append(5)
        elif styleMapStyleName == "italic":
            selection.append(0)
        elif styleMapStyleName == "bold italic":
            selection += [0, 5]
        os2.fsSelection = intListToNum(selection, 0, 16)
        # characetr indexes
        unicodes = [i for i in self.unicodeToGlyphNameMapping.keys() if i is not None]
        if unicodes:
            minIndex = min(unicodes)
            maxIndex = max(unicodes)
        else:
            # the font may have *no* unicode values (it really happens!) so
            # there needs to be a fallback. use 0xFFFF, as AFDKO does:
            # FDK/Tools/Programs/makeotf/makeotf_lib/source/hotconv/map.c
            minIndex = 0xFFFF
            maxIndex = 0xFFFF
        if maxIndex > 0xFFFF:
            # the spec says that 0xFFFF should be used
            # as the max if the max exceeds 0xFFFF
            maxIndex = 0xFFFF
        os2.fsFirstCharIndex = minIndex
        os2.fsLastCharIndex = maxIndex
        os2.usBreakChar = 32
        os2.usDefaultChar = 0
        # maximum contextual lookup length
        os2.usMaxContex = 0

    def setupTable_hmtx(self):
        """
        Make the hmtx table.

        **This should not be called externally.** Subclasses
        may override or supplement this method to handle the
        table creation in a different way if desired.
        """

        self.otf["hmtx"] = hmtx = newTable("hmtx")
        hmtx.metrics = {}
        for glyphName, glyph in self.allGlyphs.items():
            width = glyph.width
            if width < 0:
                raise ValueError(
                    "The width should not be negative: '%s'" % (glyphName))
            bounds = self.glyphBoundingBoxes[glyphName]
            left = bounds.xMin if bounds else 0
            hmtx[glyphName] = (round(width), left)

    def setupTable_hhea(self):
        """
        Make the hhea table. This assumes that the hmtx table was made first.

        **This should not be called externally.** Subclasses
        may override or supplement this method to handle the
        table creation in a different way if desired.
        """
        self.otf["hhea"] = hhea = newTable("hhea")
        hmtx = self.otf["hmtx"]
        font = self.ufo
        hhea.tableVersion = 0x00010000
        # vertical metrics
        hhea.ascent = round(getAttrWithFallback(font.info, "openTypeHheaAscender"))
        hhea.descent = round(getAttrWithFallback(font.info, "openTypeHheaDescender"))
        hhea.lineGap = round(getAttrWithFallback(font.info, "openTypeHheaLineGap"))
        # horizontal metrics
        widths = []
        lefts = []
        rights = []
        extents = []
        for glyphName in self.allGlyphs:
            width, left = hmtx[glyphName]
            widths.append(width)
            bounds = self.glyphBoundingBoxes[glyphName]
            if bounds is None:
                continue
            right = width - left - (bounds.xMax - bounds.xMin)
            lefts.append(left)
            rights.append(right)
            # equation from the hhea spec for calculating xMaxExtent:
            #   Max(lsb + (xMax - xMin))
            extent = left + (bounds.xMax - bounds.xMin)
            extents.append(extent)
        hhea.advanceWidthMax = max(widths)
        hhea.minLeftSideBearing = min(lefts)
        hhea.minRightSideBearing = min(rights)
        hhea.xMaxExtent = max(extents)
        # misc
        hhea.caretSlopeRise = getAttrWithFallback(font.info, "openTypeHheaCaretSlopeRise")
        hhea.caretSlopeRun = getAttrWithFallback(font.info, "openTypeHheaCaretSlopeRun")
        hhea.caretOffset = round(getAttrWithFallback(font.info, "openTypeHheaCaretOffset"))
        hhea.reserved0 = 0
        hhea.reserved1 = 0
        hhea.reserved2 = 0
        hhea.reserved3 = 0
        hhea.metricDataFormat = 0
        # glyph count
        hhea.numberOfHMetrics = len(self.allGlyphs)

    def setupTable_vmtx(self):
        """
        Make the vmtx table.

        **This should not be called externally.** Subclasses
        may override or supplement this method to handle the
        table creation in a different way if desired.
        """

        self.otf["vmtx"] = vmtx = newTable("vmtx")
        vmtx.metrics = {}
        for glyphName, glyph in self.allGlyphs.items():
            height = glyph.height
            verticalOrigin = _getVerticalOrigin(glyph)
            bounds = self.glyphBoundingBoxes[glyphName]
            top = bounds.yMax if bounds else 0
            vmtx[glyphName] = (round(height), verticalOrigin - top)

    def setupTable_VORG(self):
        """
        Make the VORG table.

        **This should not be called externally.** Subclasses
        may override or supplement this method to handle the
        table creation in a different way if desired.
        """
        self.otf["VORG"] = vorg = newTable("VORG")
        vorg.majorVersion = 1
        vorg.minorVersion = 0
        vorg.VOriginRecords = {}
        # Find the most frequent verticalOrigin
        vorg_count = Counter(_getVerticalOrigin(glyph)
                             for glyph in self.allGlyphs.values())
        vorg.defaultVertOriginY = vorg_count.most_common(1)[0][0]
        if len(vorg_count) > 1:
            for glyphName, glyph in self.allGlyphs.items():
                vorg.VOriginRecords[glyphName] = _getVerticalOrigin(glyph)
        vorg.numVertOriginYMetrics = len(vorg.VOriginRecords)

    def setupTable_vhea(self):
        """
        Make the vhea table. This assumes that the head and vmtx tables were
        made first.

        **This should not be called externally.** Subclasses
        may override or supplement this method to handle the
        table creation in a different way if desired.
        """
        self.otf["vhea"] = vhea = newTable("vhea")
        font = self.ufo
        head = self.otf["head"]
        vmtx = self.otf["vmtx"]
        vhea.tableVersion = 0x00011000
        # horizontal metrics
        vhea.ascent = round(getAttrWithFallback(font.info, "openTypeVheaVertTypoAscender"))
        vhea.descent = round(getAttrWithFallback(font.info, "openTypeVheaVertTypoDescender"))
        vhea.lineGap = round(getAttrWithFallback(font.info, "openTypeVheaVertTypoLineGap"))
        # vertical metrics
        heights = []
        tops = []
        bottoms = []
        for glyphName in self.allGlyphs:
            height, top = vmtx[glyphName]
            heights.append(height)
            bounds = self.glyphBoundingBoxes[glyphName]
            if bounds is None:
                continue
            bottom = height - top - (bounds.yMax - bounds.yMin)
            tops.append(top)
            bottoms.append(bottom)
        vhea.advanceHeightMax = max(heights)
        vhea.minTopSideBearing = max(tops)
        vhea.minBottomSideBearing = max(bottoms)
        vhea.yMaxExtent = vhea.minTopSideBearing - (head.yMax - head.yMin)
        # misc
        vhea.caretSlopeRise = getAttrWithFallback(font.info, "openTypeVheaCaretSlopeRise")
        vhea.caretSlopeRun = getAttrWithFallback(font.info, "openTypeVheaCaretSlopeRun")
        vhea.caretOffset = getAttrWithFallback(font.info, "openTypeVheaCaretOffset")
        vhea.reserved0 = 0
        vhea.reserved1 = 0
        vhea.reserved2 = 0
        vhea.reserved3 = 0
        vhea.reserved4 = 0
        vhea.metricDataFormat = 0
        # glyph count
        vhea.numberOfVMetrics = len(self.allGlyphs)

    def setupTable_post(self):
        """
        Make the post table.

        **This should not be called externally.** Subclasses
        may override or supplement this method to handle the
        table creation in a different way if desired.
        """
        self.otf["post"] = post = newTable("post")
        font = self.ufo
        post.formatType = 3.0
        # italic angle
        italicAngle = getAttrWithFallback(font.info, "italicAngle")
        post.italicAngle = italicAngle
        # underline
        underlinePosition = getAttrWithFallback(font.info, "postscriptUnderlinePosition")
        post.underlinePosition = round(underlinePosition)
        underlineThickness = getAttrWithFallback(font.info, "postscriptUnderlineThickness")
        post.underlineThickness = round(underlineThickness)
        # determine if the font has a fixed width
        widths = set([glyph.width for glyph in self.allGlyphs.values()])
        post.isFixedPitch = getAttrWithFallback(font.info, "postscriptIsFixedPitch")
        # misc
        post.minMemType42 = 0
        post.maxMemType42 = 0
        post.minMemType1 = 0
        post.maxMemType1 = 0

    def setupOtherTables(self):
        """
        Make the other tables. The default implementation does nothing.

        **This should not be called externally.** Subclasses
        may override this method to add other tables to the
        font if desired.
        """
        pass


class OutlineOTFCompiler(BaseOutlineCompiler):
    """Compile a .otf font with CFF outlines."""

    sfntVersion = "OTTO"

    def __init__(self, font, glyphOrder=None, roundTolerance=None):
        if roundTolerance is not None:
            self.roundTolerance = float(roundTolerance)
        else:
            # round all coordinates to integers by default
            self.roundTolerance = 0.5
        super(OutlineOTFCompiler, self).__init__(font, glyphOrder)

    def makeGlyphsBoundingBoxes(self):
        """
        Make bounding boxes for all the glyphs, and return a dictionary of
        BoundingBox(xMin, xMax, yMin, yMax) namedtuples keyed by glyph names.
        The bounding box of empty glyphs (without contours or components) is
        set to None.

        Check that the float values are within the range of the specified
        self.roundTolerance, and if so use the rounded value; else take the
        floor or ceiling to ensure that the bounding box encloses the original
        values.
        """

        def toInt(value, else_callback):
            rounded = round(value)
            if tolerance >= 0.5 or abs(rounded - value) <= tolerance:
                return rounded
            else:
                return int(else_callback(value))

        tolerance = self.roundTolerance
        glyphBoxes = {}
        for glyphName, glyph in self.allGlyphs.items():
            bounds = None
            if glyph or glyph.components:
                bounds = glyph.controlPointBounds
                if bounds:
                    rounded = []
                    for value in bounds[:2]:
                        rounded.append(toInt(value, math.floor))
                    for value in bounds[2:]:
                        rounded.append(toInt(value, math.ceil))
                    bounds = BoundingBox(*rounded)
            glyphBoxes[glyphName] = bounds
        return glyphBoxes

    def getCharStringForGlyph(self, glyph, private, globalSubrs):
        """
        Get a Type2CharString for the *glyph*

        **This should not be called externally.** Subclasses
        may override this method to handle the charstring creation
        in a different way if desired.
        """
        width = glyph.width
        # subtract the nominal width
        postscriptNominalWidthX = getAttrWithFallback(self.ufo.info, "postscriptNominalWidthX")
        if postscriptNominalWidthX:
            width = width - postscriptNominalWidthX
        # round
        width = round(width)
        pen = T2CharStringPen(width, self.allGlyphs,
                              roundTolerance=self.roundTolerance)
        glyph.draw(pen)
        charString = pen.getCharString(private, globalSubrs)
        return charString

    def setupTable_maxp(self):
        """Make the maxp table."""

        self.otf["maxp"] = maxp = newTable("maxp")
        maxp.tableVersion = 0x00005000

    def setupOtherTables(self):
        self.setupTable_CFF()
        if self.vertical:
            self.setupTable_VORG()

    def setupTable_CFF(self):
        """Make the CFF table."""

        self.otf["CFF "] = cff = newTable("CFF ")
        cff = cff.cff
        # set up the basics
        cff.major = 1
        cff.minor = 0
        cff.hdrSize = 4
        cff.offSize = 4
        cff.fontNames = []
        strings = IndexedStrings()
        cff.strings = strings
        private = PrivateDict(strings=strings)
        private.rawDict.update(private.defaults)
        globalSubrs = GlobalSubrsIndex(private=private)
        topDict = TopDict(GlobalSubrs=globalSubrs, strings=strings)
        topDict.Private = private
        charStrings = topDict.CharStrings = CharStrings(file=None, charset=None,
            globalSubrs=globalSubrs, private=private, fdSelect=None, fdArray=None)
        charStrings.charStringsAreIndexed = True
        topDict.charset = []
        charStringsIndex = charStrings.charStringsIndex = SubrsIndex(private=private, globalSubrs=globalSubrs)
        cff.topDictIndex = topDictIndex = TopDictIndex()
        topDictIndex.append(topDict)
        topDictIndex.strings = strings
        cff.GlobalSubrs = globalSubrs
        # populate naming data
        info = self.ufo.info
        psName = getAttrWithFallback(info, "postscriptFontName")
        cff.fontNames.append(psName)
        topDict = cff.topDictIndex[0]
        topDict.version = "%d.%d" % (getAttrWithFallback(info, "versionMajor"), getAttrWithFallback(info, "versionMinor"))
        trademark = getAttrWithFallback(info, "trademark")
        if trademark:
            trademark = normalizeStringForPostscript(trademark.replace("\u00A9", "Copyright"))
        if trademark != self.ufo.info.trademark:
            self.log.append("[Warning] The trademark was normalized for storage in the CFF table and consequently some characters were dropped: '%s'" % trademark)
        if trademark is None:
            trademark = ""
        topDict.Notice = trademark
        copyright = getAttrWithFallback(info, "copyright")
        if copyright:
            copyright = normalizeStringForPostscript(copyright.replace("\u00A9", "Copyright"))
        if copyright != self.ufo.info.copyright:
            self.log.append("[Warning] The copyright was normalized for storage in the CFF table and consequently some characters were dropped: '%s'" % copyright)
        if copyright is None:
            copyright = ""
        topDict.Copyright = copyright
        topDict.FullName = getAttrWithFallback(info, "postscriptFullName")
        topDict.FamilyName = getAttrWithFallback(info, "openTypeNamePreferredFamilyName")
        topDict.Weight = getAttrWithFallback(info, "postscriptWeightName")
        topDict.FontName = psName
        # populate various numbers
        topDict.isFixedPitch = getAttrWithFallback(info, "postscriptIsFixedPitch")
        topDict.ItalicAngle = getAttrWithFallback(info, "italicAngle")
        underlinePosition = getAttrWithFallback(info, "postscriptUnderlinePosition")
        topDict.UnderlinePosition = round(underlinePosition)
        underlineThickness = getAttrWithFallback(info, "postscriptUnderlineThickness")
        topDict.UnderlineThickness = round(underlineThickness)
        # populate font matrix
        unitsPerEm = round(getAttrWithFallback(info, "unitsPerEm"))
        topDict.FontMatrix = [1.0 / unitsPerEm, 0, 0, 1.0 / unitsPerEm, 0, 0]
        # populate the width values
        defaultWidthX = round(getAttrWithFallback(info, "postscriptDefaultWidthX"))
        if defaultWidthX:
            private.rawDict["defaultWidthX"] = defaultWidthX
        nominalWidthX = round(getAttrWithFallback(info, "postscriptNominalWidthX"))
        if nominalWidthX:
            private.rawDict["nominalWidthX"] = nominalWidthX
        # populate hint data
        blueFuzz = round(getAttrWithFallback(info, "postscriptBlueFuzz"))
        blueShift = round(getAttrWithFallback(info, "postscriptBlueShift"))
        blueScale = getAttrWithFallback(info, "postscriptBlueScale")
        forceBold = getAttrWithFallback(info, "postscriptForceBold")
        blueValues = getAttrWithFallback(info, "postscriptBlueValues")
        if isinstance(blueValues, list):
            blueValues = [round(i) for i in blueValues]
        otherBlues = getAttrWithFallback(info, "postscriptOtherBlues")
        if isinstance(otherBlues, list):
            otherBlues = [round(i) for i in otherBlues]
        familyBlues = getAttrWithFallback(info, "postscriptFamilyBlues")
        if isinstance(familyBlues, list):
            familyBlues = [round(i) for i in familyBlues]
        familyOtherBlues = getAttrWithFallback(info, "postscriptFamilyOtherBlues")
        if isinstance(familyOtherBlues, list):
            familyOtherBlues = [round(i) for i in familyOtherBlues]
        stemSnapH = getAttrWithFallback(info, "postscriptStemSnapH")
        if isinstance(stemSnapH, list):
            stemSnapH = [round(i) for i in stemSnapH]
        stemSnapV = getAttrWithFallback(info, "postscriptStemSnapV")
        if isinstance(stemSnapV, list):
            stemSnapV = [round(i) for i in stemSnapV]
        # only write the blues data if some blues are defined.
        if any((blueValues, otherBlues, familyBlues, familyOtherBlues)):
            private.rawDict["BlueFuzz"] = blueFuzz
            private.rawDict["BlueShift"] = blueShift
            private.rawDict["BlueScale"] = blueScale
            private.rawDict["ForceBold"] = forceBold
            if blueValues:
                private.rawDict["BlueValues"] = blueValues
            if otherBlues:
                private.rawDict["OtherBlues"] = otherBlues
            if familyBlues:
                private.rawDict["FamilyBlues"] = familyBlues
            if familyOtherBlues:
                private.rawDict["FamilyOtherBlues"] = familyOtherBlues
        # only write the stems if both are defined.
        if (stemSnapH and stemSnapV):
            private.rawDict["StemSnapH"] = stemSnapH
            private.rawDict["StdHW"] = stemSnapH[0]
            private.rawDict["StemSnapV"] = stemSnapV
            private.rawDict["StdVW"] = stemSnapV[0]
        # populate glyphs
        for glyphName in self.glyphOrder:
            glyph = self.allGlyphs[glyphName]
            charString = self.getCharStringForGlyph(glyph, private, globalSubrs)
            # add to the font
            if glyphName in charStrings:
                # XXX a glyph already has this name. should we choke?
                glyphID = charStrings.charStrings[glyphName]
                charStringsIndex.items[glyphID] = charString
            else:
                charStringsIndex.append(charString)
                glyphID = len(topDict.charset)
                charStrings.charStrings[glyphName] = glyphID
                topDict.charset.append(glyphName)
        topDict.FontBBox = self.fontBoundingBox
        # write the glyph order
        self.otf.setGlyphOrder(self.glyphOrder)


class OutlineTTFCompiler(BaseOutlineCompiler):
    """Compile a .ttf font with TrueType outlines."""

    sfntVersion = "\000\001\000\000"

    def __init__(self, font, glyphOrder=None, convertCubics=True,
                 cubicConversionError=2):
        super(OutlineTTFCompiler, self).__init__(font, glyphOrder)
        self.convertCubics = convertCubics
        self.cubicConversionError = cubicConversionError

    def setupTable_maxp(self):
        """Make the maxp table."""

        self.otf["maxp"] = maxp = newTable("maxp")
        maxp.tableVersion = 0x00010000
        maxp.maxZones = 1
        maxp.maxTwilightPoints = 0
        maxp.maxStorage = 0
        maxp.maxFunctionDefs = 0
        maxp.maxInstructionDefs = 0
        maxp.maxStackElements = 0
        maxp.maxSizeOfInstructions = 0
        maxp.maxComponentElements = max(len(g.components)
                                        for g in self.allGlyphs.values())

    def setupTable_post(self):
        """Make a format 2 post table with the compiler's glyph order."""

        super(OutlineTTFCompiler, self).setupTable_post()
        post = self.otf["post"]
        post.formatType = 2.0
        post.extraNames = []
        post.mapping = {}
        post.glyphOrder = self.glyphOrder

    def setupOtherTables(self):
        self.setupTable_glyf()
        if self.ufo.info.openTypeGaspRangeRecords:
            self.setupTable_gasp()

    def setupTable_glyf(self):
        """Make the glyf table."""

        allGlyphs = self.allGlyphs
        if self.convertCubics:
            from cu2qu.pens import Cu2QuPen
            allGlyphs = {}
            for name, glyph in self.allGlyphs.items():
                if isinstance(glyph, StubGlyph):
                    allGlyphs[name] = glyph
                    continue
                newGlyph = glyph.__class__()
                glyph.draw(Cu2QuPen(
                    newGlyph.getPen(), self.cubicConversionError,
                    reverse_direction=True))
                allGlyphs[name] = newGlyph

        self.otf["loca"] = newTable("loca")
        self.otf["glyf"] = glyf = newTable("glyf")
        glyf.glyphs = {}
        glyf.glyphOrder = self.glyphOrder

        for name in self.glyphOrder:
            glyph = allGlyphs[name]
            pen = TTGlyphPen(allGlyphs)
            glyph.draw(pen)
            ttGlyph = pen.glyph()
            if ttGlyph.isComposite() and self.autoUseMyMetrics:
                self.autoUseMyMetrics(ttGlyph, glyph.width, allGlyphs)
            glyf[name] = ttGlyph

    @staticmethod
    def autoUseMyMetrics(ttGlyph, width, glyphSet):
        """ Set the "USE_MY_METRICS" flag on the first component having the
        same advance width as the composite glyph, no transform and no
        horizontal shift (but allow it to shift vertically).
        This forces the composite glyph to use the possibly hinted horizontal
        metrics of the sub-glyph, instead of those from the "hmtx" table.
        """
        for component in ttGlyph.components:
            try:
                baseName, transform = component.getComponentInfo()
            except AttributeError:
                # component uses '{first,second}Pt' instead of 'x' and 'y'
                continue
            if (glyphSet[baseName].width == width and
                    transform[:-1] == (1, 0, 0, 1, 0)):
                component.flags |= USE_MY_METRICS
                break


class StubGlyph(object):

    """
    This object will be used to create missing glyphs
    (specifically .notdef) in the provided UFO.
    """

    def __init__(self, name, width, unitsPerEm, ascender, descender, unicodes=[]):
        self.name = name
        self.width = width
        self.unitsPerEm = unitsPerEm
        self.ascender = ascender
        self.descender = descender
        self.unicodes = unicodes
        self.components = []
        if unicodes:
            self.unicode = unicodes[0]
        else:
            self.unicode = None
        if name == ".notdef":
            self.draw = self._drawDefaultNotdef

    def __len__(self):
        if self.name == ".notdef":
            return 1
        return 0

    def _get_leftMargin(self):
        if self.bounds is None:
            return 0
        return self.bounds[0]

    leftMargin = property(_get_leftMargin)

    def _get_rightMargin(self):
        bounds = self.bounds
        if bounds is None:
            return 0
        xMin, yMin, xMax, yMax = bounds
        return self.width - bounds[2]

    rightMargin = property(_get_rightMargin)

    def draw(self, pen):
        pass

    def _drawDefaultNotdef(self, pen):
        width = round(self.unitsPerEm * 0.5)
        stroke = round(self.unitsPerEm * 0.05)
        ascender = self.ascender
        descender = self.descender
        xMin = stroke
        xMax = width - stroke
        yMax = ascender
        yMin = descender
        pen.moveTo((xMin, yMin))
        pen.lineTo((xMax, yMin))
        pen.lineTo((xMax, yMax))
        pen.lineTo((xMin, yMax))
        pen.lineTo((xMin, yMin))
        pen.closePath()
        xMin += stroke
        xMax -= stroke
        yMax -= stroke
        yMin += stroke
        pen.moveTo((xMin, yMin))
        pen.lineTo((xMin, yMax))
        pen.lineTo((xMax, yMax))
        pen.lineTo((xMax, yMin))
        pen.lineTo((xMin, yMin))
        pen.closePath()

    def _get_controlPointBounds(self):
        pen = ControlBoundsPen(None)
        self.draw(pen)
        return pen.bounds

    controlPointBounds = property(_get_controlPointBounds)
