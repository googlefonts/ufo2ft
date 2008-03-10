from __future__ import division
import time
from fontTools.ttLib import TTFont
from fontTools.ttLib import TTFont, newTable
from fontTools.cffLib import TopDictIndex, TopDict, CharStrings, SubrsIndex, GlobalSubrsIndex, PrivateDict, IndexedStrings
from fontTools.ttLib.tables.O_S_2f_2 import Panose
from charstringPen import T2CharStringPen


def makeOutlineOTF(font, path, glyphOrder=None):
    otf = TTFont(sfntVersion="OTTO")
    # populate default values
    _setupTable_head(otf, font)
    _setupTable_hhea(otf, font)
    _setupTable_hmtx(otf, font)
    _setupTable_name(otf, font)
    _setupTable_maxp(otf, font)
    _setupTable_cmap(otf, font)
    _setupTable_OS2(otf, font)
    _setupTable_post(otf, font)
    _setupTable_CFF(otf, font)
    # populate the outlines
    if glyphOrder is None:
        glyphOrder = sorted(font.keys())
    _populate_glyphs(otf, font, glyphOrder)
    # write the file
    otf.save(path)
    # discard the object
    otf.close()

def _setupTable_head(otf, font):
    otf["head"] = head = newTable("head")
    head.checkSumAdjustment = 0 # XXX this is a guess
    head.tableVersion = 1.0
    head.fontRevision = 1.0
    head.magicNumber = 0x5F0F3CF5
    head.flags = 0 # XXX this is a guess
    head.unitsPerEm = int(font.info.unitsPerEm)
    rightNow = long(time.time() - time.timezone)
    head.created = rightNow
    head.modified = rightNow
    head.xMin = 0
    head.yMin = 0
    head.xMax = 0
    head.yMax = 0
    head.macStyle = 0 # XXX this is a guess
    head.lowestRecPPEM = 3 # XXX FontValidator describes this as "unreasonably small"
    head.fontDirectionHint = 2 # XXX this is a guess
    head.indexToLocFormat = 0 # XXX this is a guess
    head.glyphDataFormat = 0

def _setupTable_name(otf, font):
    # this table must exist, but it can be empty.
    otf["name"] = newTable("name")

def _setupTable_maxp(otf, font):
    otf["maxp"] = maxp = newTable("maxp")
    maxp.tableVersion = 0x00005000

def _setupTable_cmap(otf, font):
    # XXX is this necessary for the outline source?
    # XXX need to make sure that these are the proper tables to write
    from fontTools.ttLib.tables._c_m_a_p import cmap_format_4, cmap_format_6
    cmap4_0_3 = cmap_format_4(4)
    cmap4_0_3.platformID = 0
    cmap4_0_3.platEncID = 3
    cmap4_0_3.language = 0
    cmap4_0_3.cmap = {}

    cmap6_1_0 = cmap_format_4(6)
    cmap6_1_0.platformID = 1
    cmap6_1_0.platEncID = 0
    cmap6_1_0.language = 0
    cmap6_1_0.cmap = {}

    cmap4_3_1 = cmap_format_4(4)
    cmap4_3_1.platformID = 3
    cmap4_3_1.platEncID = 1
    cmap4_3_1.language = 0
    cmap4_3_1.cmap = {}

    otf["cmap"] = cmap = newTable("cmap")
    cmap.tableVersion = 0
    cmap.tables = [cmap4_0_3]#, cmap6_1_0, cmap4_3_1] # XXX more tables? one of this is preventing compile

def _setupTable_OS2(otf, font):
    otf["OS/2"] = os2 = newTable("OS/2")
    os2.version = 0x0003 # XXX has this been bumped up?
    os2.xAvgCharWidth = int(round(font.info.unitsPerEm * 0.5)) # XXX calculate?
    os2.usWeightClass = 400
    os2.usWidthClass = 5
    os2.fsType = 0x0000
    superAndSubscriptSize = int(round(font.info.ascender * 0.85)) # XXX what should the default be?
    os2.ySubscriptXSize = superAndSubscriptSize
    os2.ySubscriptYSize = superAndSubscriptSize
    os2.ySubscriptXOffset = 0 # XXX what should the default be?
    os2.ySubscriptYOffset = int(round(font.info.descender * 0.5)) # XXX what should the default be?
    os2.ySuperscriptXSize = superAndSubscriptSize
    os2.ySuperscriptYSize = superAndSubscriptSize
    os2.ySuperscriptXOffset = 0 # XXX what should the default be?
    os2.ySuperscriptYOffset = font.info.ascender - superAndSubscriptSize # XXX what should the default be?
    os2.yStrikeoutSize = int(round(font.info.unitsPerEm * 0.05)) # XXX what should the default be?
    os2.yStrikeoutPosition = int(round(font.info.unitsPerEm * .23)) # XXX what should the default be?
    os2.sFamilyClass = 0
    panose = Panose()
    panose.bFamilyType = 2
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
    os2.ulUnicodeRange1 = 0
    os2.ulUnicodeRange2 = 0
    os2.ulUnicodeRange3 = 0
    os2.ulUnicodeRange4 = 0
    os2.achVendID = "None" # XXX get vendor code from font
    os2.fsSelection = 64 # XXX this is a guess
    os2.fsFirstCharIndex = 0 # usFirstCharIndex
    os2.fsLastCharIndex = 0 # usLastCharIndex
    os2.sTypoAscender = font.info.ascender
    os2.sTypoDescender = -font.info.descender
    os2.sTypoLineGap = 0
    os2.usWinAscent = font.info.ascender
    os2.usWinDescent = font.info.descender
    os2.ulCodePageRange1 = 0
    os2.ulCodePageRange2 = 0
    os2.sxHeight = int(round(font.info.ascender * 0.5))
    os2.sCapHeight = font.info.ascender
    os2.usDefaultChar = 0
    os2.usBreakChar = 1
    os2.usMaxContex = 0 # usMaxContext

def _setupTable_hmtx(otf,  font):
    # this is required, but it can be empty
    otf["hmtx"] = hmtx = newTable("hmtx")
    hmtx.metrics = {}

def _setupTable_hhea(otf, font):
    otf["hhea"] = hhea = newTable("hhea")
    hhea.tableVersion = 1.0
    hhea.ascent = int(font.info.ascender)
    hhea.descent = -int(font.info.descender)
    hhea.lineGap = 0
    hhea.advanceWidthMax = 0
    hhea.minLeftSideBearing = 0
    hhea.minRightSideBearing = 0
    hhea.xMaxExtent = 0
    hhea.caretSlopeRise = 1
    hhea.caretSlopeRun = 0
    hhea.caretOffset = 0 # XXX this is a guess
    hhea.reserved0 = 0
    hhea.reserved1 = 0
    hhea.reserved2 = 0
    hhea.reserved3 = 0
    hhea.metricDataFormat = 0
    hhea.numberOfHMetrics = 0

def _setupTable_post(otf, font):
    otf["post"] = post = newTable("post")
    post.formatType = 3.0
    italicAngle = font.info.italicAngle
    if italicAngle is None:
        italicAngle = 0
    post.italicAngle = italicAngle
    post.underlinePosition = -int(round(font.info.descender * 0.3)) # XXX this is a guess
    post.underlineThickness = int(round(font.info.unitsPerEm * .05)) # XXX this is a guess
    post.isFixedPitch = 0
    post.minMemType42 = 0 # XXX this is a guess
    post.maxMemType42 = 0 # XXX this is a guess
    post.minMemType1 = 0 # XXX this is a guess
    post.maxMemType1 = 0 # XXX this is a guess

def _setupTable_CFF(otf, font):
    otf["CFF "] = cff = newTable("CFF ")
    cff = cff.cff
    cff.major = 1
    cff.minor = 0
    cff.hdrSize = 4
    cff.offSize = 4
    cff.fontNames = [] # XXX need a real font name!
    strings = IndexedStrings()
    cff.strings = strings
    private = PrivateDict(strings=strings)
    private.rawDict.update(private.defaults)
    globalSubrs = GlobalSubrsIndex(private=private)
    topDict = TopDict(GlobalSubrs=globalSubrs, strings=strings)
    topDict.Private = private
    topDict.CharStrings = CharStrings(file=None, charset=None,
        globalSubrs=globalSubrs, private=private, fdSelect=None, fdArray=None)
    topDict.CharStrings.charStringsAreIndexed = True
    topDict.charset = []
    topDict.CharStrings.charStringsIndex = SubrsIndex(private=private, globalSubrs=globalSubrs)
    cff.topDictIndex = topDictIndex = TopDictIndex()
    topDictIndex.append(topDict)
    topDictIndex.strings = strings
    cff.GlobalSubrs = globalSubrs
    # populate data from the font.
    # this is required for a basic CFF table.
    info = font.info
    cff.fontNames.append(info.fontName)
    topDict = cff.topDictIndex[0]
    if hasattr(info, "fullName"):
        topDict.FullName = makePSName(font) # XXX this should probably draw from a real value
    if hasattr(info, "familyName"):
        topDict.FamilyName = info.familyName
    if hasattr(info, "styleName"):
        topDict.Weight = info.styleName
    if hasattr(info, "fontName"):
        topDict.FontName = makePSName(font) # XXX this should probably draw from a real value

def _populate_glyphs(otf, font, glyphOrder):
    mapping, widths, lefts, rights, fontBBox = _populate_CFF(otf, font, glyphOrder)
    glyphCount = len(widths)
    # populate the cmap table
    # XXX do we need to do this for the outline source?
    cmap = otf["cmap"]
    for unicodeValue, glyphName in mapping.items():
        for table in cmap.tables:
            pID = table.platformID
            eID = table.platEncID
            # XXX are these the only valid tables?
            if (pID, eID) in [(0, 3), (3, 1), (0, 4), (3, 10)]:
                table.cmap[unicodeValue] = glyphName
    # populate the hmtx table
    hmtx = otf["hmtx"]
    for glyphName, width in widths.items():
        left = lefts[glyphName]
        right = rights[glyphName]
        hmtx[glyphName] = (width, left)
    # update the OS/2 table
    os2 = otf["OS/2"]
    # the OS/2 doc states:
    # """
    # The value for xAvgCharWidth is calculated by obtaining the arithmetic
    # average of the width of all non-zero width glyphs in the font.
    # """
    # "non-zero width glyphs"? does that mean that glyphs with
    # a width of zero should not be counted? that doesn't seem right.
    avgWidth = int(round(sum(widths.values()) / glyphCount))
    os2.xAvgCharWidth = avgWidth
    minIndex = 32 # it is safe to asume that this is present since a space glyph is inserted
    maxIndex = max(mapping.keys())
    if maxIndex >= 0xFFFF:
        # see OS/2 docs
        # need to find a value lower than 0xFFFF.
        # shouldn't get to this point though.
        raise NotImplementedError
    os2.fsFirstCharIndex = minIndex
    os2.fsLastCharIndex = maxIndex
    os2.usBreakChar = 32
    os2.usDefaultChar = 32
    # update the hhea table
    hhea = otf["hhea"]
    hhea.advanceWidthMax = max(widths.values())
    hhea.minLeftSideBearing = min(lefts.values())
    rightSidebearing = [widths[glyphName] - rights[glyphName] for glyphName in widths.keys()]
    hhea.minRightSideBearing = min(rightSidebearing)
    hhea.xMaxExtent = max(rights.values()) # XXX the docs give an equation that is murky: Max(lsb + (xMax - xMin))
    hhea.numberOfHMetrics = glyphCount
    # update the head table
    head = otf["head"]
    head.xMin, head.yMin, head.xMax, head.yMax = fontBBox
    # update the post table
    post = otf["post"]
    # XXX make a guess at this?
    isFixedPitch = True
    testWidth = None
    for width in widths.values():
        if testWidth is None:
            testWidth = width
            continue
        if width != testWidth:
            isFixedPitch = False
            break
    post.isFixedPitch = isFixedPitch

def _populate_CFF(otf, font, glyphOrder):
    orderedGlyphs = _getOrderedGlyphs(font, glyphOrder)
    # as the CFF table is built, a bunch of info
    # for the other tables is stored.
    mapping = {}
    widths = {}
    lefts = {}
    rights = {}
    fontBBox = getFontBBox(font)
    # build the CFF table
    cff = otf["CFF "].cff
    topDict = cff.topDictIndex[0]
    charStrings = topDict.CharStrings
    charStringsIndex = charStrings.charStringsIndex
    private = charStringsIndex.private
    globalSubrs = charStringsIndex.globalSubrs
    for glyph in orderedGlyphs:
        glyphName = glyph.name
        glyphWidth = glyph.width
        unicodes = glyph.unicodes
        if hasattr(glyph, "box"):
            bounds = glyph.box
        else:
            bounds = glyph.bounds
        if bounds is not None:
            xMin, yMin, xMax, yMax = bounds
        else:
            xMin = 0
            xMax = 0
        # write the char string
        pen = T2CharStringPen(glyphWidth, font)
        glyph.draw(pen)
        charString = pen.getCharString(private, globalSubrs)
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
        # store needed values
        if unicodes:
            for unicodeValue in unicodes:
                mapping[unicodeValue] = glyphName
        widths[glyphName] = glyphWidth
        lefts[glyphName] = xMin
        rights[glyphName] = xMax
    topDict.FontBBox = fontBBox
    # write the glyph order
    glyphOrder = [glyph.name for glyph in orderedGlyphs]
    otf.setGlyphOrder(glyphOrder)
    # return the saved data
    return mapping, widths, lefts, rights, fontBBox

def _getOrderedGlyphs(font, glyphOrder):
    orderedGlyphs = []
    defaultWidth = int(round(font.info.unitsPerEm * 0.5))
    glyphOrder = list(glyphOrder)
    # .notdef should be the first glyph. create it if it does not exist.
    if ".notdef" not in font:
        notdef = StubGlyph(name=".notdef", width=defaultWidth, unitsPerEm=font.info.unitsPerEm, ascender=font.info.ascender, descender=font.info.descender)
    else:
        notdef = font[".notdef"]
    orderedGlyphs.append(notdef)
    # space should be the second glyph. create it if it does not exist.
    if "space" not in font:
        space = StubGlyph(name="space", width=defaultWidth, unitsPerEm=font.info.unitsPerEm, ascender=font.info.ascender, descender=font.info.descender, unicodes=[32])
    else:
        space = font["space"]
    orderedGlyphs.append(space)
    # make sure no glyphs are missing from the order
    for glyphName in sorted(font.keys()):
        if glyphName not in glyphOrder:
            glyphOrder.append(glyphName)
    # now gather the glyphs
    for glyphName in glyphOrder:
        if glyphName in [".notdef", "space"]:
            continue
        orderedGlyphs.append(font[glyphName])
    # done.
    return orderedGlyphs

def makePSName(font):
    familyName = font.info.familyName
    styleName = font.info.styleName
    return familyName.replace(" ", "") + "-" + styleName.replace(" ", "")

def getFontBBox(font):
    from fontTools.misc.arrayTools import unionRect
    rect = None
    for glyph in font:
        if hasattr(glyph, "box"):
            bounds = glyph.box
        else:
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
        if unicodes:
            self.unicode = unicodes[0]
        else:
            self.unicode = None
        if name == ".notdef":
            self.draw = self._drawDefaultNotdef

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

