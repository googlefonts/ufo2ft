from __future__ import division
import time
from fontTools.ttLib import TTFont, newTable
from fontTools.cffLib import TopDictIndex, TopDict, CharStrings, SubrsIndex, GlobalSubrsIndex, PrivateDict, IndexedStrings
from fontTools.ttLib.tables.O_S_2f_2 import Panose
from fontTools.ttLib.tables._h_e_a_d import parse_date
from charstringPen import T2CharStringPen


class OutlineOTFCompiler(object):

    def __init__(self, font, path, glyphOrder=None):
        self.ufo = font
        self.path = path
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
        self.fontBoundingBox = self.makeFontBoundingBox()
        # make a reusable character mapping
        self.unicodeToGlyphNameMapping = self.makeUnicodeToGlyphNameMapping()

    # -----------
    # Main Method
    # -----------

    def compile(self):
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
        return getFontBBox(self.allGlyphs.values())

    def makeUnicodeToGlyphNameMapping(self):
        mapping = {}
        for glyphName, glyph in self.allGlyphs.items():
            unicodes = glyph.unicodes
            for uni in unicodes:
                mapping[uni] = glyphName
        return mapping

    def makeMissingRequiredGlyphs(self):
        glyphs = {}
        defaultWidth = int(round(self.ufo.info.unitsPerEm * 0.5))
        if ".notdef" not in self.ufo:
            glyphs[".notdef"] = StubGlyph(name=".notdef", width=defaultWidth, unitsPerEm=self.ufo.info.unitsPerEm, ascender=self.ufo.info.ascender, descender=self.ufo.info.descender)
        if "space" not in self.ufo:
            glyphs["space"] = StubGlyph(name="space", width=defaultWidth, unitsPerEm=self.ufo.info.unitsPerEm, ascender=self.ufo.info.ascender, descender=self.ufo.info.descender, unicodes=[32])
        return glyphs

    def makeOfficialGlyphOrder(self, glyphOrder):
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
        pen = T2CharStringPen(glyph.width, self.allGlyphs)
        glyph.draw(pen)
        charString = pen.getCharString(private, globalSubrs)
        return charString

    # --------------
    # Table Builders
    # --------------

    def setupTable_head(self):
        self.otf["head"] = head = newTable("head")
        head.checkSumAdjustment = 0 # XXX this is a guess
        head.tableVersion = 1.0
        head.fontRevision = 1.0
        head.magicNumber = 0x5F0F3CF5
        # upm
        head.unitsPerEm = int(self.ufo.info.unitsPerEm)
        # times
        rightNow = parse_date(time.asctime(time.gmtime()))
        head.created = rightNow
        head.modified = rightNow
        # bounding box
        xMin, yMin, xMax, yMax = self.fontBoundingBox
        head.xMin = xMin
        head.yMin = yMin
        head.xMax = xMax
        head.yMax = yMax
        # style mapping
        head.macStyle = 0 # XXX this is a guess
        # misc
        head.flags = 3 # XXX this is a guess
        head.lowestRecPPEM = 3 # XXX FontValidator describes this as "unreasonably small"
        head.fontDirectionHint = 2 # XXX this is a guess
        head.indexToLocFormat = 0 # XXX this is a guess
        head.glyphDataFormat = 0

    def setupTable_name(self):
        self.otf["name"] = newTable("name")

    def setupTable_maxp(self):
        self.otf["maxp"] = maxp = newTable("maxp")
        maxp.tableVersion = 0x00005000

    def setupTable_cmap(self):
        from fontTools.ttLib.tables._c_m_a_p import cmap_format_4
        # mac
        cmap4_0_3 = cmap_format_4(4)
        cmap4_0_3.platformID = 0
        cmap4_0_3.platEncID = 3
        cmap4_0_3.language = 0
        cmap4_0_3.cmap = dict(self.unicodeToGlyphNameMapping)
        # windows
        cmap4_3_1 = cmap_format_4(4)
        cmap4_3_1.platformID = 3
        cmap4_3_1.platEncID = 1
        cmap4_3_1.language = 0
        cmap4_3_1.cmap = dict(self.unicodeToGlyphNameMapping)
        # store
        self.otf["cmap"] = cmap = newTable("cmap")
        cmap.tableVersion = 0
        cmap.tables = [cmap4_0_3, cmap4_3_1]

    def setupTable_OS2(self):
        self.otf["OS/2"] = os2 = newTable("OS/2")
        os2.version = 0x0003 # XXX has this been bumped up?
        # average glyph width
        widths = [glyph.width for glyph in self.allGlyphs.values() if glyph.width > 0]
        os2.xAvgCharWidth = int(round(sum(widths) / len(widths)))
        # weight and width classes
        os2.usWeightClass = 400
        os2.usWidthClass = 5
        # embedding
        os2.fsType = 0
        # superscript and subscript
        superAndSubscriptSize = int(round(self.ufo.info.ascender * 0.85)) # XXX what should the default be?
        os2.ySubscriptXSize = superAndSubscriptSize
        os2.ySubscriptYSize = superAndSubscriptSize
        os2.ySubscriptXOffset = 0 # XXX what should the default be?
        os2.ySubscriptYOffset = int(round(self.ufo.info.descender * 0.5)) # XXX what should the default be?
        os2.ySuperscriptXSize = superAndSubscriptSize
        os2.ySuperscriptYSize = superAndSubscriptSize
        os2.ySuperscriptXOffset = 0 # XXX what should the default be?
        os2.ySuperscriptYOffset = self.ufo.info.ascender - superAndSubscriptSize # XXX what should the default be?
        os2.yStrikeoutSize = int(round(self.ufo.info.unitsPerEm * 0.05)) # XXX what should the default be?
        os2.yStrikeoutPosition = int(round(self.ufo.info.unitsPerEm * .23)) # XXX what should the default be?
        os2.sFamilyClass = 0
        # Panose
        panose = Panose()
        panose.bFamilyType = 0
        panose.bSerifStyle = 0
        panose.bWeight = 0
        panose.bProportion = 0
        panose.bContrast = 0
        panose.bStrokeVariation = 0
        panose.bArmStyle = 0
        panose.bLetterForm = 0
        panose.bMidline = 0
        panose.bXHeight = 0
        os2.panose = panose
        # Unicode and code page ranges
        os2.ulUnicodeRange1 = 0
        os2.ulUnicodeRange2 = 0
        os2.ulUnicodeRange3 = 0
        os2.ulUnicodeRange4 = 0
        os2.ulCodePageRange1 = 0
        os2.ulCodePageRange2 = 0
        # vendor id
        os2.achVendID = "None" # XXX get vendor code from font
        # vertical metrics
        os2.sxHeight = int(round(self.ufo.info.ascender * 0.5))
        os2.sCapHeight = self.ufo.info.ascender
        os2.sTypoAscender = self.ufo.info.unitsPerEm + self.ufo.info.descender
        os2.sTypoDescender = self.ufo.info.descender
        os2.sTypoLineGap = 50
        os2.usWinAscent = self.fontBoundingBox[3]
        os2.usWinDescent = self.fontBoundingBox[1]
        # style mapping
        os2.fsSelection = 0 # XXX this is a guess
        # characetr indexes
        unicodes = [i for i in self.unicodeToGlyphNameMapping.keys() if i is not None]
        minIndex = min(unicodes)
        maxIndex = max(unicodes)
        if maxIndex >= 0xFFFF:
            # see OS/2 docs
            # need to find a value lower than 0xFFFF.
            # shouldn't get to this point though.
            raise NotImplementedError
        os2.fsFirstCharIndex = minIndex
        os2.fsLastCharIndex = maxIndex
        os2.usBreakChar = 32
        os2.usDefaultChar = 0
        # maximum contextual lookup length
        os2.usMaxContex = 0

    def setupTable_hmtx(self):
        self.otf["hmtx"] = hmtx = newTable("hmtx")
        hmtx.metrics = {}
        for glyphName, glyph in self.allGlyphs.items():
            width = glyph.width
            left = 0
            if len(glyph) or len(glyph.components):
                left = glyph.leftMargin
            hmtx[glyphName] = (width, left)

    def setupTable_hhea(self):
        self.otf["hhea"] = hhea = newTable("hhea")
        hhea.tableVersion = 1.0
        # vertical metrics
        hhea.ascent = int(self.ufo.info.unitsPerEm + self.ufo.info.descender)
        hhea.descent = int(self.ufo.info.descender)
        hhea.lineGap = 50
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
            bounds = glyph.bounds
            if bounds is not None:
                xMin, yMin, xMax, yMax = glyph.bounds
            else:
                xMin = 0
                xMax = 0
            extent = left + (xMax - xMin) # equation from spec for calculating xMaxExtent: Max(lsb + (xMax - xMin))
            extents.append(extent)
        hhea.advanceWidthMax = max(widths)
        hhea.minLeftSideBearing = min(lefts)
        hhea.minRightSideBearing = min(rights)
        hhea.xMaxExtent = max(extents)
        # misc
        hhea.caretSlopeRise = 1
        hhea.caretSlopeRun = 0
        hhea.caretOffset = 0 # XXX this is a guess
        hhea.reserved0 = 0
        hhea.reserved1 = 0
        hhea.reserved2 = 0
        hhea.reserved3 = 0
        hhea.metricDataFormat = 0
        # glyph count
        hhea.numberOfHMetrics = len(self.allGlyphs)

    def setupTable_post(self):
        self.otf["post"] = post = newTable("post")
        post.formatType = 3.0
        # italic angle
        italicAngle = self.ufo.info.italicAngle
        if italicAngle is None:
            italicAngle = 0
        post.italicAngle = italicAngle
        # underline
        post.underlinePosition = int(round(self.ufo.info.descender * 0.3)) # XXX this is a guess
        post.underlineThickness = int(round(self.ufo.info.unitsPerEm * .05)) # XXX this is a guess
        # determine if the font has a fixed width
        widths = set([glyph.width for glyph in self.allGlyphs.values()])
        post.isFixedPitch = bool(len(widths) == 1)
        # misc
        post.minMemType42 = 0 # XXX this is a guess
        post.maxMemType42 = 0 # XXX this is a guess
        post.minMemType1 = 0 # XXX this is a guess
        post.maxMemType1 = 0 # XXX this is a guess

    def setupTable_CFF(self):
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
        psName = makePSName(self.ufo)
        cff.fontNames.append(psName)
        topDict = cff.topDictIndex[0]
        topDict.FullName = "%s %s" % (info.familyName, info.styleName)
        topDict.FamilyName = info.familyName
        topDict.Weight = info.styleName
        topDict.FontName = psName
        # populate glyphs
        for glyphName in self.glyphOrder:
            glyph = self.allGlyphs[glyphName]
            glyphWidth = glyph.width
            unicodes = glyph.unicodes
            bounds = glyph.bounds
            if bounds is not None:
                xMin, yMin, xMax, yMax = bounds
            else:
                xMin = 0
                xMax = 0
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
        pass


def makePSName(font):
    familyName = font.info.familyName
    styleName = font.info.styleName
    return familyName.replace(" ", "") + "-" + styleName.replace(" ", "")

def getFontBBox(font):
    from fontTools.misc.arrayTools import unionRect
    rect = None
    for glyph in font:
        bounds = glyph.bounds
        if rect is None:
            rect = bounds
            continue
        if rect is not None and bounds is not None:
            rect = unionRect(rect, bounds)
    if rect is None:
        rect = (0, 0, 0, 0)
    return rect


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
