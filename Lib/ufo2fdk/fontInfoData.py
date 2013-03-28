"""
This file provides fallback data for info attributes
that are required for building OTFs. There are two main
functions that are important:

* :func:`~getAttrWithFallback`
* :func:`~preflightInfo`

There are a set of other functions that are used internally
for synthesizing values for specific attributes. These can be
used externally as well.
"""

import time
import unicodedata
from fontTools.misc.textTools import binary2num
from fontTools.misc.arrayTools import unionRect
from robofab import ufoLib
try:
    set
except NameError:
    from sets import Set as set

# -----------------
# Special Fallbacks
# -----------------

# generic

def styleMapFamilyNameFallback(info):
    """
    Fallback to *openTypeNamePreferredFamilyName openTypeNamePreferredSubfamilyName*.
    """
    familyName = getAttrWithFallback(info, "openTypeNamePreferredFamilyName")
    styleName = getAttrWithFallback(info, "openTypeNamePreferredSubfamilyName")
    if styleName is None:
        styleName = u""
    return (familyName + u" " + styleName).strip()

# head

def dateStringForNow():
    year, month, day, hour, minute, second, weekDay, yearDay, isDST = time.localtime()
    year = str(year)
    month = str(month).zfill(2)
    day = str(day).zfill(2)
    hour = str(hour).zfill(2)
    minute = str(minute).zfill(2)
    second = str(second).zfill(2)
    return "%s/%s/%s %s:%s:%s" % (year, month, day, hour, minute, second)

def openTypeHeadCreatedFallback(info):
    """
    Fallback to now.
    """
    return dateStringForNow()

# hhea

def openTypeHheaAscenderFallback(info):
    """
    Fallback to *unitsPerEm + descender*.
    """
    return info.unitsPerEm + info.descender

def openTypeHheaDescenderFallback(info):
    """
    Fallback to *descender*.
    """
    return info.descender

# name

def openTypeNameVersionFallback(info):
    """
    Fallback to *versionMajor.versionMinor* in the form 0.000.
    """
    versionMajor = getAttrWithFallback(info, "versionMajor")
    versionMinor = getAttrWithFallback(info, "versionMinor")
    return "%d.%s" % (versionMajor, str(versionMinor).zfill(3))

def openTypeNameUniqueIDFallback(info):
    """
    Fallback to *openTypeNameVersion;openTypeOS2VendorID;styleMapFamilyName styleMapStyleName*.
    """
    version = getAttrWithFallback(info, "openTypeNameVersion")
    vendor = getAttrWithFallback(info, "openTypeOS2VendorID")
    familyName = getAttrWithFallback(info, "styleMapFamilyName")
    styleName = getAttrWithFallback(info, "styleMapStyleName").title()
    return u"%s;%s;%s %s" % (version, vendor, familyName, styleName)

def openTypeNamePreferredFamilyNameFallback(info):
    """
    Fallback to *familyName*.
    """
    return info.familyName

def openTypeNamePreferredSubfamilyNameFallback(info):
    """
    Fallback to *styleName*.
    """
    return info.styleName

def openTypeNameCompatibleFullNameFallback(info):
    """
    Fallback to *styleMapFamilyName styleMapStyleName*.
    If *styleMapStyleName* is *regular* this will not add
    the style name.
    """
    familyName = getAttrWithFallback(info, "styleMapFamilyName")
    styleMapStyleName = getAttrWithFallback(info, "styleMapStyleName")
    if styleMapStyleName != "regular":
        familyName += " " + styleMapStyleName.title()
    return familyName

def openTypeNameWWSFamilyNameFallback(info):
    # not yet supported
    return None

def openTypeNameWWSSubfamilyNameFallback(info):
    # not yet supported
    return None

# OS/2

def openTypeOS2TypoAscenderFallback(info):
    """
    Fallback to *unitsPerEm + descender*.
    """
    return info.unitsPerEm + info.descender

def openTypeOS2TypoDescenderFallback(info):
    """
    Fallback to *descender*.
    """
    return info.descender

def openTypeOS2WinAscentFallback(info):
    """
    Fallback to the maximum y value of the font's bounding box.
    If that is not available, fallback to *ascender*.
    """
    font = info.getParent()
    if font is None:
        return getAttrWithFallback(info, "ascender")
    bounds = getFontBounds(font)
    xMin, yMin, xMax, yMax = bounds
    return yMax

def openTypeOS2WinDescentFallback(info):
    """
    Fallback to the minimum y value of the font's bounding box.
    If that is not available, fallback to *descender*.
    """
    font = info.getParent()
    if font is None:
        return abs(getAttrWithFallback(info, "descender"))
    bounds = getFontBounds(font)
    if bounds is None:
        return abs(getAttrWithFallback(info, "descender"))
    xMin, yMin, xMax, yMax = bounds
    return abs(yMin)

# postscript

_postscriptFontNameExceptions = set("[](){}<>/%")
_postscriptFontNameAllowed = set([unichr(i) for i in xrange(33, 137)])

def normalizeStringForPostscript(s, allowSpaces=True):
    s = unicode(s)
    normalized = []
    for c in s:
        if c == " " and not allowSpaces:
            continue
        if c in _postscriptFontNameExceptions:
            continue
        if c not in _postscriptFontNameAllowed:
            c = unicodedata.normalize("NFKD", c).encode("ascii", "ignore")
        normalized.append(c)
    return "".join(normalized)

def normalizeNameForPostscript(name):
    return normalizeStringForPostscript(name, allowSpaces=False)

def postscriptFontNameFallback(info):
    """
    Fallback to a string containing only valid characters
    as defined in the specification. This will draw from
    *openTypeNamePreferredFamilyName* and *openTypeNamePreferredSubfamilyName*.
    """
    name = u"%s-%s" % (getAttrWithFallback(info, "openTypeNamePreferredFamilyName"), getAttrWithFallback(info, "openTypeNamePreferredSubfamilyName"))
    return normalizeNameForPostscript(name)

def postscriptFullNameFallback(info):
    """
    Fallback to *openTypeNamePreferredFamilyName openTypeNamePreferredSubfamilyName*.
    """
    return u"%s %s" % (getAttrWithFallback(info, "openTypeNamePreferredFamilyName"), getAttrWithFallback(info, "openTypeNamePreferredSubfamilyName"))

def postscriptSlantAngleFallback(info):
    """
    Fallback to *italicAngle*.
    """
    return getAttrWithFallback(info, "italicAngle")

_postscriptWeightNameOptions = {
    100 : "Thin",
    200 : "Extra-light",
    300 : "Light",
    400 : "Normal",
    500 : "Medium",
    600 : "Semi-bold",
    700 : "Bold",
    800 : "Extra-bold",
    900 : "Black"
}

def postscriptWeightNameFallback(info):
    """
    Fallback to the closest match of the *openTypeOS2WeightClass*
    in this table:

    ===  ===========
    100  Thin
    200  Extra-light
    300  Light
    400  Normal
    500  Medium
    600  Semi-bold
    700  Bold
    800  Extra-bold
    900  Black
    ===  ===========
    """
    value = getAttrWithFallback(info, "openTypeOS2WeightClass")
    value = int(round(value * .01) * 100)
    if value < 100:
        value = 100
    elif value > 900:
        value = 900
    name = _postscriptWeightNameOptions[value]
    return name

# --------------
# Attribute Maps
# --------------

staticFallbackData = dict(
    styleMapStyleName="regular",
    versionMajor=0,
    versionMinor=0,
    copyright=None,
    trademark=None,
    italicAngle=0,
    # not needed
    year=None,
    note=None,

    openTypeHeadLowestRecPPEM=6,
    openTypeHeadFlags=[0, 1],

    openTypeHheaLineGap=200,
    openTypeHheaCaretSlopeRise=1,
    openTypeHheaCaretSlopeRun=0,
    openTypeHheaCaretOffset=0,

    openTypeNameDesigner=None,
    openTypeNameDesignerURL=None,
    openTypeNameManufacturer=None,
    openTypeNameManufacturerURL=None,
    openTypeNameLicense=None,
    openTypeNameLicenseURL=None,
    openTypeNameDescription=None,
    openTypeNameSampleText=None,

    openTypeOS2WidthClass=5,
    openTypeOS2WeightClass=400,
    openTypeOS2Selection=[],
    openTypeOS2VendorID="NONE",
    openTypeOS2Panose=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    openTypeOS2FamilyClass=[0, 0],
    openTypeOS2UnicodeRanges=[],
    openTypeOS2CodePageRanges=[],
    openTypeOS2TypoLineGap=200,
    openTypeOS2Type=[2],
    # let the FDK fallback on these
    openTypeOS2SubscriptXSize=None,
    openTypeOS2SubscriptYSize=None,
    openTypeOS2SubscriptXOffset=None,
    openTypeOS2SubscriptYOffset=None,
    openTypeOS2SuperscriptXSize=None,
    openTypeOS2SuperscriptYSize=None,
    openTypeOS2SuperscriptXOffset=None,
    openTypeOS2SuperscriptYOffset=None,
    openTypeOS2StrikeoutSize=None,
    openTypeOS2StrikeoutPosition=None,

    # fallback to None on these
    # as the user should be in
    # complete control
    openTypeVheaVertTypoAscender=None,
    openTypeVheaVertTypoDescender=None,
    openTypeVheaVertTypoLineGap=None,
    openTypeVheaCaretSlopeRise=None,
    openTypeVheaCaretSlopeRun=None,
    openTypeVheaCaretOffset=None,

    postscriptUniqueID=None,
    postscriptUnderlineThickness=None,
    postscriptUnderlinePosition=None,
    postscriptIsFixedPitch=False,
    postscriptBlueValues=[],
    postscriptOtherBlues=[],
    postscriptFamilyBlues=[],
    postscriptFamilyOtherBlues=[],
    postscriptStemSnapH=[],
    postscriptStemSnapV=[],
    postscriptBlueFuzz=1,
    postscriptBlueShift=7,
    postscriptBlueScale=.039625,
    postscriptForceBold=False,
    postscriptDefaultWidthX=200,
    postscriptNominalWidthX=0,

    # not used in OTF
    postscriptDefaultCharacter=None,
    postscriptWindowsCharacterSet=None,

    # not used in OTF
    macintoshFONDFamilyID=None,
    macintoshFONDName=None
)

specialFallbacks = dict(
    styleMapFamilyName=styleMapFamilyNameFallback,
    openTypeHeadCreated=openTypeHeadCreatedFallback,
    openTypeHheaAscender=openTypeHheaAscenderFallback,
    openTypeHheaDescender=openTypeHheaDescenderFallback,
    openTypeNameVersion=openTypeNameVersionFallback,
    openTypeNameUniqueID=openTypeNameUniqueIDFallback,
    openTypeNamePreferredFamilyName=openTypeNamePreferredFamilyNameFallback,
    openTypeNamePreferredSubfamilyName=openTypeNamePreferredSubfamilyNameFallback,
    openTypeNameCompatibleFullName=openTypeNameCompatibleFullNameFallback,
    openTypeNameWWSFamilyName=openTypeNameWWSFamilyNameFallback,
    openTypeNameWWSSubfamilyName=openTypeNameWWSSubfamilyNameFallback,
    openTypeOS2TypoAscender=openTypeOS2TypoAscenderFallback,
    openTypeOS2TypoDescender=openTypeOS2TypoDescenderFallback,
    openTypeOS2WinAscent=openTypeOS2WinAscentFallback,
    openTypeOS2WinDescent=openTypeOS2WinDescentFallback,
    postscriptFontName=postscriptFontNameFallback,
    postscriptFullName=postscriptFullNameFallback,
    postscriptSlantAngle=postscriptSlantAngleFallback,
    postscriptWeightName=postscriptWeightNameFallback
)

requiredAttributes = set(ufoLib.fontInfoAttributesVersion2) - (set(staticFallbackData.keys()) | set(specialFallbacks.keys()))

recommendedAttributes = set([
    "styleMapFamilyName",
    "versionMajor",
    "versionMinor",
    "copyright",
    "trademark",
    "openTypeHeadCreated",
    "openTypeNameDesigner",
    "openTypeNameDesignerURL",
    "openTypeNameManufacturer",
    "openTypeNameManufacturerURL",
    "openTypeNameLicense",
    "openTypeNameLicenseURL",
    "openTypeNameDescription",
    "openTypeNameSampleText",
    "openTypeOS2WidthClass",
    "openTypeOS2WeightClass",
    "openTypeOS2VendorID",
    "openTypeOS2Panose",
    "openTypeOS2FamilyClass",
    "openTypeOS2UnicodeRanges",
    "openTypeOS2CodePageRanges",
    "openTypeOS2TypoLineGap",
    "openTypeOS2Type",
    "postscriptBlueValues",
    "postscriptOtherBlues",
    "postscriptFamilyBlues",
    "postscriptFamilyOtherBlues",
    "postscriptStemSnapH",
    "postscriptStemSnapV"
])

# ------------
# Main Methods
# ------------

def getAttrWithFallback(info, attr):
    """
    Get the value for *attr* from the *info* object.
    If the object does not have the attribute or the value
    for the atribute is None, this will either get a
    value from a predefined set of attributes or it
    will synthesize a value from the available data.
    """
    if hasattr(info, attr) and getattr(info, attr) is not None:
        value = getattr(info, attr)
    else:
        if attr in specialFallbacks:
            value = specialFallbacks[attr](info)
        else:
            value = staticFallbackData[attr]
    return value

def preflightInfo(info):
    """
    Returns a dict containing two items. The value for each
    item will be a list of info attribute names.

    ==================  ===
    missingRequired     Required data that is missing.
    missingRecommended  Recommended data that is missing.
    ==================  ===
    """
    missingRequired = set()
    missingRecommended = set()
    for attr in requiredAttributes:
        if not hasattr(info, attr) or getattr(info, attr) is None:
            missingRequired.add(attr)
    for attr in recommendedAttributes:
        if not hasattr(info, attr) or getattr(info, attr) is None:
            missingRecommended.add(attr)
    return dict(missingRequired=missingRequired, missingRecommended=missingRecommended)

def getFontBounds(font):
    """
    Get a tuple of (xMin, yMin, xMax, yMax) for all
    glyphs in the given *font*.
    """
    rect = None
    # defcon
    if hasattr(font, "bounds"):
        rect = font.bounds
    # others
    else:
        for glyph in font:
            # robofab
            if hasattr(glyph,"box"):
                bounds = glyph.box
            # others
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

# -----------------
# Low Level Support
# -----------------

# these should not be used outside of this package

def intListToNum(intList, start, length):
    all = []
    bin = ""
    for i in range(start, start+length):
        if i in intList:
            b = "1"
        else:
            b = "0"
        bin = b + bin
        if not (i + 1) % 8:
            all.append(bin)
            bin = ""
    if bin:
        all.append(bin)
    all.reverse()
    all = " ".join(all)
    return binary2num(all)

def dateStringToTimeValue(date):
    try:
        t = time.strptime(date, "%Y/%m/%d %H:%M:%S")
        return long(time.mktime(t))
    except OverflowError:
        return 0L

# ----
# Test
# ----

class _TestInfoObject(object):

    def __init__(self):
        self.familyName = "Family Name"
        self.styleName = "Style Name"
        self.unitsPerEm = 1000
        self.descender = -250
        self.xHeight = 450
        self.capHeight = 600
        self.ascender = 650
        self.bounds = (0, -225, 100, 755)

    def getParent(self):
        return self


def _test():
    """
    >>> info = _TestInfoObject()

    >>> getAttrWithFallback(info, "familyName")
    'Family Name'
    >>> getAttrWithFallback(info, "styleName")
    'Style Name'

    >>> getAttrWithFallback(info, "styleMapFamilyName")
    u'Family Name Style Name'
    >>> info.styleMapFamilyName = "Style Map Family Name"
    >>> getAttrWithFallback(info, "styleMapFamilyName")
    'Style Map Family Name'

    >>> getAttrWithFallback(info, "openTypeNamePreferredFamilyName")
    'Family Name'
    >>> getAttrWithFallback(info, "openTypeNamePreferredSubfamilyName")
    'Style Name'
    >>> getAttrWithFallback(info, "openTypeNameCompatibleFullName")
    'Style Map Family Name'

    >>> getAttrWithFallback(info, "openTypeHheaAscender")
    750
    >>> getAttrWithFallback(info, "openTypeHheaDescender")
    -250

    >>> getAttrWithFallback(info, "openTypeNameVersion")
    '0.000'
    >>> info.versionMinor = 1
    >>> info.versionMajor = 1
    >>> getAttrWithFallback(info, "openTypeNameVersion")
    '1.001'

    >>> getAttrWithFallback(info, "openTypeNameUniqueID")
    u'1.001;NONE;Style Map Family Name Regular'

    >>> getAttrWithFallback(info, "openTypeOS2TypoAscender")
    750
    >>> getAttrWithFallback(info, "openTypeOS2TypoDescender")
    -250
    >>> getAttrWithFallback(info, "openTypeOS2WinAscent")
    755
    >>> getAttrWithFallback(info, "openTypeOS2WinDescent")
    225

    >>> getAttrWithFallback(info, "postscriptSlantAngle")
    0
    >>> getAttrWithFallback(info, "postscriptWeightName")
    'Normal'
    """

if __name__ == "__main__":
    import doctest
    doctest.testmod()
