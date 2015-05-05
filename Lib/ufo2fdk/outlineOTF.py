from __future__ import division
import time
from fontTools.ttLib import TTFont, newTable
from fontTools.cffLib import TopDictIndex, TopDict, CharStrings, SubrsIndex, GlobalSubrsIndex, PrivateDict, IndexedStrings
from fontTools.ttLib.tables.O_S_2f_2 import Panose
from fontTools.ttLib.tables._h_e_a_d import mac_epoch_diff
from pens.t2CharStringPen import T2CharStringPen
from fontInfoData import getFontBounds, getAttrWithFallback, dateStringToTimeValue, dateStringForNow, intListToNum, normalizeStringForPostscript
try:
    set
except NameError:
    from sets import Set as set
try:
    sorted
except NameError:
    def sorted(l):
        l = list(l)
        l.sort()
        return l

def _roundInt(v):
    return int(round(v))


class OutlineOTFCompiler(object):

    """
    This object will create a bare-bones OTF-CFF containing
    outline data and not much else. The only external
    method is :meth:`ufo2fdk.tools.outlineOTF.compile`.

    When creating this object, you must provide a *font*
    object and a *path* indicating where the OTF should
    be saved. Optionally, you can provide a *glyphOrder*
    list of glyph names indicating the order of the glyphs
    in the font.
    """

    def __init__(self, font, path, glyphOrder=None):
        self.ufo = font
        self.path = path
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
            glyphOrder = sorted(self.allGlyphs.keys())
        self.glyphOrder = self.makeOfficialGlyphOrder(glyphOrder)
        # make a reusable bounding box
        self.fontBoundingBox = tuple([_roundInt(i) for i in self.makeFontBoundingBox()])
        # make a reusable character mapping
        self.unicodeToGlyphNameMapping = self.makeUnicodeToGlyphNameMapping()

    # -----------
    # Main Method
    # -----------

    def compile(self):
        """
        Compile the OTF.
        """
        self.otf = TTFont(sfntVersion="OTTO")
        # populate basic tables
        self.setupTable_head()
        self.setupTable_hhea()
        self.setupTable_hmtx()
        self.setupTable_name()
        self.setupTable_maxp()
        self.setupTable_cmap()
        self.setupTable_OS2()
        self.setupTable_post()
        self.setupTable_CFF()
        self.setupOtherTables()
        # write the file
        self.otf.save(self.path)
        # discard the object
        self.otf.close()
        del self.otf

    # -----
    # Tools
    # -----

    def makeFontBoundingBox(self):
        """
        Make a bounding box for the font.

        **This should not be called externally.** Subclasses
        may override this method to handle the bounds creation
        in a different way if desired.
        """
        return getFontBounds(self.ufo)

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
        Add space and .notdef to the font if they are not present.

        **This should not be called externally.** Subclasses
        may override this method to handle the glyph creation
        in a different way if desired.
        """
        glyphs = {}
        font = self.ufo
        unitsPerEm = _roundInt(getAttrWithFallback(font.info, "unitsPerEm"))
        ascender = _roundInt(getAttrWithFallback(font.info, "ascender"))
        descender = _roundInt(getAttrWithFallback(font.info, "descender"))
        defaultWidth = _roundInt(unitsPerEm * 0.5)
        if ".notdef" not in self.ufo:
            glyphs[".notdef"] = StubGlyph(name=".notdef", width=defaultWidth, unitsPerEm=unitsPerEm, ascender=ascender, descender=descender)
        if "space" not in self.ufo:
            glyphs["space"] = StubGlyph(name="space", width=defaultWidth, unitsPerEm=unitsPerEm, ascender=ascender, descender=descender, unicodes=[32])
        return glyphs

    def makeOfficialGlyphOrder(self, glyphOrder):
        """
        Make a the final glyph order.

        **This should not be called externally.** Subclasses
        may override this method to handle the order creation
        in a different way if desired.
        """
        allGlyphs = self.allGlyphs
        orderedGlyphs = [".notdef", "space"]
        for glyphName in glyphOrder:
            if glyphName in [".notdef", "space"]:
                continue
            orderedGlyphs.append(glyphName)
        for glyphName in sorted(self.allGlyphs.keys()):
            if glyphName not in orderedGlyphs:
                orderedGlyphs.append(glyphName)
        return orderedGlyphs

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
        width = _roundInt(width)
        pen = T2CharStringPen(width, self.allGlyphs)
        glyph.draw(pen)
        charString = pen.getCharString(private, globalSubrs)
        return charString

    # --------------
    # Table Builders
    # --------------

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
        versionMajor = getAttrWithFallback(font.info, "versionMajor")
        versionMinor = getAttrWithFallback(font.info, "versionMinor") * .001
        head.fontRevision = versionMajor + versionMinor
        head.magicNumber = 0x5F0F3CF5
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
        head.lowestRecPPEM = _roundInt(getAttrWithFallback(font.info, "openTypeHeadLowestRecPPEM"))
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
        self.otf["name"] = newTable("name")

    def setupTable_maxp(self):
        """
        Make the maxp table.

        **This should not be called externally.** Subclasses
        may override or supplement this method to handle the
        table creation in a different way if desired.
        """
        self.otf["maxp"] = maxp = newTable("maxp")
        maxp.tableVersion = 0x00005000

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
        os2.xAvgCharWidth = _roundInt(sum(widths) / len(widths))
        # weight and width classes
        os2.usWeightClass = getAttrWithFallback(font.info, "openTypeOS2WeightClass")
        os2.usWidthClass = getAttrWithFallback(font.info, "openTypeOS2WidthClass")
        # embedding
        os2.fsType = intListToNum(getAttrWithFallback(font.info, "openTypeOS2Type"), 0, 16)
        # subscript
        v = getAttrWithFallback(font.info, "openTypeOS2SubscriptXSize")
        if v is None:
            v = 0
        os2.ySubscriptXSize = _roundInt(v)
        v = getAttrWithFallback(font.info, "openTypeOS2SubscriptYSize")
        if v is None:
            v = 0
        os2.ySubscriptYSize = _roundInt(v)
        v = getAttrWithFallback(font.info, "openTypeOS2SubscriptXOffset")
        if v is None:
            v = 0
        os2.ySubscriptXOffset = _roundInt(v)
        v = getAttrWithFallback(font.info, "openTypeOS2SubscriptYOffset")
        if v is None:
            v = 0
        os2.ySubscriptYOffset = _roundInt(v)
        # superscript
        v = getAttrWithFallback(font.info, "openTypeOS2SuperscriptXSize")
        if v is None:
            v = 0
        os2.ySuperscriptXSize = _roundInt(v)
        v = getAttrWithFallback(font.info, "openTypeOS2SuperscriptYSize")
        if v is None:
            v = 0
        os2.ySuperscriptYSize = _roundInt(v)
        v = getAttrWithFallback(font.info, "openTypeOS2SuperscriptXOffset")
        if v is None:
            v = 0
        os2.ySuperscriptXOffset = _roundInt(v)
        v = getAttrWithFallback(font.info, "openTypeOS2SuperscriptYOffset")
        if v is None:
            v = 0
        os2.ySuperscriptYOffset = _roundInt(v)
        # strikeout
        v = getAttrWithFallback(font.info, "openTypeOS2StrikeoutSize")
        if v is None:
            v = 0
        os2.yStrikeoutSize = _roundInt(v)
        v = getAttrWithFallback(font.info, "openTypeOS2StrikeoutPosition")
        if v is None:
            v = 0
        os2.yStrikeoutPosition = _roundInt(v)
        # family class
        os2.sFamilyClass = 0 # XXX not sure how to create the appropriate value
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
        os2.achVendID = str(getAttrWithFallback(font.info, "openTypeOS2VendorID").decode("ascii", "ignore"))
        # vertical metrics
        os2.sxHeight = _roundInt(getAttrWithFallback(font.info, "xHeight"))
        os2.sCapHeight = _roundInt(getAttrWithFallback(font.info, "capHeight"))
        os2.sTypoAscender = _roundInt(getAttrWithFallback(font.info, "openTypeOS2TypoAscender"))
        os2.sTypoDescender = _roundInt(getAttrWithFallback(font.info, "openTypeOS2TypoDescender"))
        os2.sTypoLineGap = _roundInt(getAttrWithFallback(font.info, "openTypeOS2TypoLineGap"))
        os2.usWinAscent = _roundInt(getAttrWithFallback(font.info, "openTypeOS2WinAscent"))
        os2.usWinDescent = _roundInt(getAttrWithFallback(font.info, "openTypeOS2WinDescent"))
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
            # the font may have *no* unicode values
            # (it really happens!) so there needs
            # to be a fallback. use space for this.
            minIndex = 0x0020
            maxIndex = 0x0020
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
            left = 0
            if len(glyph) or len(glyph.components):
                left = glyph.leftMargin
            if left is None:
                left = 0
            hmtx[glyphName] = (_roundInt(width), _roundInt(left))

    def setupTable_hhea(self):
        """
        Make the hhea table.

        **This should not be called externally.** Subclasses
        may override or supplement this method to handle the
        table creation in a different way if desired.
        """
        self.otf["hhea"] = hhea = newTable("hhea")
        font = self.ufo
        hhea.tableVersion = 1.0
        # vertical metrics
        hhea.ascent = _roundInt(getAttrWithFallback(font.info, "openTypeHheaAscender"))
        hhea.descent = _roundInt(getAttrWithFallback(font.info, "openTypeHheaDescender"))
        hhea.lineGap = _roundInt(getAttrWithFallback(font.info, "openTypeHheaLineGap"))
        # horizontal metrics
        widths = []
        lefts = []
        rights = []
        extents = []
        for glyph in self.allGlyphs.values():
            left = glyph.leftMargin
            right = glyph.rightMargin
            if left is None:
                left = 0
            if right is None:
                right = 0
            widths.append(glyph.width)
            lefts.append(left)
            rights.append(right)
            # robofab
            if hasattr(glyph, "box"):
                bounds = glyph.box
            # others
            else:
                bounds = glyph.bounds
            if bounds is not None:
                xMin, yMin, xMax, yMax = bounds
            else:
                xMin = 0
                xMax = 0
            extent = left + (xMax - xMin) # equation from spec for calculating xMaxExtent: Max(lsb + (xMax - xMin))
            extents.append(extent)
        hhea.advanceWidthMax = _roundInt(max(widths))
        hhea.minLeftSideBearing = _roundInt(min(lefts))
        hhea.minRightSideBearing = _roundInt(min(rights))
        hhea.xMaxExtent = _roundInt(max(extents))
        # misc
        hhea.caretSlopeRise = getAttrWithFallback(font.info, "openTypeHheaCaretSlopeRise")
        hhea.caretSlopeRun = getAttrWithFallback(font.info, "openTypeHheaCaretSlopeRun")
        hhea.caretOffset = _roundInt(getAttrWithFallback(font.info, "openTypeHheaCaretOffset"))
        hhea.reserved0 = 0
        hhea.reserved1 = 0
        hhea.reserved2 = 0
        hhea.reserved3 = 0
        hhea.metricDataFormat = 0
        # glyph count
        hhea.numberOfHMetrics = len(self.allGlyphs)

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
        if underlinePosition is None:
            underlinePosition = 0
        post.underlinePosition = _roundInt(underlinePosition)
        underlineThickness = getAttrWithFallback(font.info, "postscriptUnderlineThickness")
        if underlineThickness is None:
            underlineThickness = 0
        post.underlineThickness = _roundInt(underlineThickness)
        # determine if the font has a fixed width
        widths = set([glyph.width for glyph in self.allGlyphs.values()])
        post.isFixedPitch = getAttrWithFallback(font.info, "postscriptIsFixedPitch")
        # misc
        post.minMemType42 = 0
        post.maxMemType42 = 0
        post.minMemType1 = 0
        post.maxMemType1 = 0

    def setupTable_CFF(self):
        """
        Make the CFF table.

        **This should not be called externally.** Subclasses
        may override or supplement this method to handle the
        table creation in a different way if desired.
        """
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
            trademark = normalizeStringForPostscript(trademark.replace(u"\u00A9", "Copyright"))
        if trademark != self.ufo.info.trademark:
            self.log.append("[Warning] The trademark was normalized for storage in the CFF table and consequently some characters were dropped: '%s'" % trademark)
        if trademark is None:
            trademark = ""
        topDict.Notice = trademark
        copyright = getAttrWithFallback(info, "copyright")
        if copyright:
            copyright = normalizeStringForPostscript(copyright.replace(u"\u00A9", "Copyright"))
        if copyright != self.ufo.info.copyright:
            self.log.append("[Warning] The copyright was normalized for storage in the CFF table and consequently some characters were dropped: '%s'" % copyright)
        if copyright is None:
            copyright = ""
        topDict.Copyright = copyright
        topDict.FullName = getAttrWithFallback(info, "postscriptFullName")
        topDict.FamilyName = getAttrWithFallback(info, "openTypeNamePreferredFamilyName")
        topDict.Weight = getAttrWithFallback(info, "postscriptWeightName")
        topDict.FontName = getAttrWithFallback(info, "postscriptFontName")
        # populate various numbers
        topDict.isFixedPitch = getAttrWithFallback(info, "postscriptIsFixedPitch")
        topDict.ItalicAngle = getAttrWithFallback(info, "italicAngle")
        underlinePosition = getAttrWithFallback(info, "postscriptUnderlinePosition")
        if underlinePosition is None:
            underlinePosition = 0
        topDict.UnderlinePosition = _roundInt(underlinePosition)
        underlineThickness = getAttrWithFallback(info, "postscriptUnderlineThickness")
        if underlineThickness is None:
            underlineThickness = 0
        topDict.UnderlineThickness = _roundInt(underlineThickness)
        # populate font matrix
        unitsPerEm = _roundInt(getAttrWithFallback(info, "unitsPerEm"))
        topDict.FontMatrix = [1.0 / unitsPerEm, 0, 0, 1.0 / unitsPerEm, 0, 0]
        # populate the width values
        defaultWidthX = _roundInt(getAttrWithFallback(info, "postscriptDefaultWidthX"))
        if defaultWidthX:
            private.rawDict["defaultWidthX"] = defaultWidthX
        nominalWidthX = _roundInt(getAttrWithFallback(info, "postscriptNominalWidthX"))
        if nominalWidthX:
            private.rawDict["nominalWidthX"] = nominalWidthX
        # populate hint data
        blueFuzz = _roundInt(getAttrWithFallback(info, "postscriptBlueFuzz"))
        blueShift = _roundInt(getAttrWithFallback(info, "postscriptBlueShift"))
        blueScale = getAttrWithFallback(info, "postscriptBlueScale")
        forceBold = getAttrWithFallback(info, "postscriptForceBold")
        blueValues = getAttrWithFallback(info, "postscriptBlueValues")
        if isinstance(blueValues, list):
            blueValues = [_roundInt(i) for i in blueValues]
        otherBlues = getAttrWithFallback(info, "postscriptOtherBlues")
        if isinstance(otherBlues, list):
            otherBlues = [_roundInt(i) for i in otherBlues]
        familyBlues = getAttrWithFallback(info, "postscriptFamilyBlues")
        if isinstance(familyBlues, list):
            familyBlues = [_roundInt(i) for i in familyBlues]
        familyOtherBlues = getAttrWithFallback(info, "postscriptFamilyOtherBlues")
        if isinstance(familyOtherBlues, list):
            familyOtherBlues = [_roundInt(i) for i in familyOtherBlues]
        stemSnapH = getAttrWithFallback(info, "postscriptStemSnapH")
        if isinstance(stemSnapH, list):
            stemSnapH = [_roundInt(i) for i in stemSnapH]
        stemSnapV = getAttrWithFallback(info, "postscriptStemSnapV")
        if isinstance(stemSnapV, list):
            stemSnapV = [_roundInt(i) for i in stemSnapV]
        # only write the blues data if some blues are defined.
        if (blueValues or otherBlues):
            private.rawDict["BlueFuzz"] = blueFuzz
            private.rawDict["BlueShift"] = blueShift
            private.rawDict["BlueScale"] = blueScale
            private.rawDict["ForceBold"] = forceBold
            private.rawDict["BlueValues"] = blueValues
            private.rawDict["OtherBlues"] = otherBlues
            private.rawDict["FamilyBlues"] = familyBlues
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
            unicodes = glyph.unicodes
            charString = self.getCharStringForGlyph(glyph, private, globalSubrs)
            # add to the font
            exists = charStrings.has_key(glyphName)
            if exists:
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

    def setupOtherTables(self):
        """
        Make the other tables. The default implementation does nothing.

        **This should not be called externally.** Subclasses
        may override this method to add other tables to the
        font if desired.
        """
        pass


class StubGlyph(object):

    """
    This object will be used to create missing glyphs
    (specifically the space and the .notdef) in the
    provided UFO.
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
        width = int(round(self.unitsPerEm * 0.5))
        stroke = int(round(self.unitsPerEm * 0.05))
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

    def _get_bounds(self):
        from fontTools.pens.boundsPen import BoundsPen
        pen = BoundsPen(None)
        self.draw(pen)
        return pen.bounds

    bounds = property(_get_bounds)
