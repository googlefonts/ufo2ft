import os
import shutil
import re
from fontInfoData import getAttrWithFallback, intListToNum
from outlineOTF import OutlineOTFCompiler
from featureTableWriter import FeatureTableWriter, winStr, macStr


def makeOTFParts(font, path, glyphOrder=None):
    if os.path.exists(path):
        shutil.rmtree(path)
    os.mkdir(path)

    if glyphOrder is None:
        glyphOrder = sorted(font.keys())

    menuNamePath = os.path.join(path, "menuname")
    _setupMenuNameDB(font, menuNamePath)

    glyphOrderPath = os.path.join(path, "glyphOrder")
    _setupGlyphOrderAndAliasDB(font, glyphOrderPath, glyphOrder)

    fontInfoPath = os.path.join(path, "fontinfo")
    _setupFontinfo(font, fontInfoPath)

    featuresPath = os.path.join(path, "features")
    _setupFeatures(font, featuresPath)

    outlinePath = os.path.join(path, "font.otf")
    c = OutlineOTFCompiler(font, outlinePath, glyphOrder)
    c.compile()

    paths = dict(
        outlineSourcePath=outlinePath,
        menuNamePath=menuNamePath,
        glyphOrderPath=glyphOrderPath,
        fontInfoPath=fontInfoPath,
        featuresPath=featuresPath)
    return paths

def _setupMenuNameDB(font, path):
    psName = getAttrWithFallback(font.info,"postscriptFontName")
    familyName = getAttrWithFallback(font.info,"openTypeNamePreferredFamilyName")
    styleName = getAttrWithFallback(font.info,"openTypeNamePreferredSubfamilyName")
    winCompatible = getAttrWithFallback(font.info,"styleMapFamilyName")
    macCompatible = getAttrWithFallback(font.info,"openTypeNameCompatibleFullName")
    lines = [
        "[%s]" % psName,
        "f=%s" % familyName,
        "s=%s" % styleName,
    ]
    if winCompatible != familyName:
        l = "l=%s" % winCompatible
        lines.append(l)
    if macCompatible != winCompatible:
        l = "m=1,%s" % macCompatible
        lines.append(l)
    text = "\n".join(lines) + "\n"
    f = open(path, "wb")
    f.write(text)
    f.close()

def _setupGlyphOrderAndAliasDB(font, path, glyphOrder):
    lines = []
    for glyphName in glyphOrder:
        if glyphName in font and font[glyphName].unicode is not None:
            code = font[glyphName].unicode
            code = hex(code)[2:].upper()
            if len(code) < 4:
                code = code.zfill(4)
            line = "%s %s uni%s" % (glyphName, glyphName, code)
        else:
            line = "%s %s" % (glyphName, glyphName)
        lines.append(line)
    text = "\n".join(lines) + "\n"
    f = open(path, "wb")
    f.write(text)
    f.close()

def _setupFontinfo(font, path):
    lines = []
    # style mapping
    styleMapStyleName = getAttrWithFallback(font.info,"styleMapStyleName")
    if styleMapStyleName in ("italic", "bold italic"):
        lines.append("IsItalicStyle true")
    else:
        lines.append("IsItalicStyle false")
    if styleMapStyleName in ("bold", "bold italic"):
        lines.append("IsBoldStyle true")
    else:
        lines.append("IsBoldStyle false")
    # fsSelection bits
    selection = getAttrWithFallback(font.info,"openTypeOS2Selection")
    if 7 in selection:
        lines.append("PreferOS/2TypoMetrics true")
    else:
        lines.append("PreferOS/2TypoMetrics false")
    if 8 in selection:
        lines.append("IsOS/2WidthWeigthSlopeOnly true")
    else:
        lines.append("IsOS/2WidthWeigthSlopeOnly false")
    if 9 in selection:
        lines.append("IsOS/2OBLIQUE true")
    else:
        lines.append("IsOS/2OBLIQUE false")
    # write the file
    if lines:
        f = open(path, "wb")
        f.write("\n".join(lines))
        f.close()

def _setupFeatures(font, path):
    features = _forceAbsoluteIncludesInFeatures(font.features.text, os.path.dirname(path))
    tables = [
        features,
        "",
        _writeFeatures_kern(font, features),
        "",
        _writeFeaturesTable_head(font),
        "",
        _writeFeaturesTable_hhea(font),
        "",
        _writeFeaturesTable_OS2(font),
        "",
        _writeFeaturesTable_name(font)
    ]
    tables = "\n".join(tables)
    features = "\n".join([tables])
    f = open(path, "wb")
    f.write(features)
    f.close()

def _forceAbsoluteIncludesInFeatures(text, directory):
    includeRE = re.compile(
        "include"
        "\("
        "([^\)]+)"
        "\)"
        )
    for includePath in includeRE.findall(text):
        currentDirectory = directory
        parts = includePath.split("/")
        for index, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            if part == "..":
                currentDirectory = os.path.dirname(currentDirectory)
            else:
                break
        subPath = "/".join(parts[index:])
        srcPath = os.path.join(currentDirectory, subPath)
        text = text.replace(includePath, srcPath)
    return text

def _writeFeatures_kern(font, existingFeatures):
    kernFeatureSearch_RE = re.compile(
        "feature"
        "\s+"
        "kern"
        "\s*"
        "{.+}"
        "\s*"
        "kern"
        "\s*"
        ";"
    )
    lines = [i.split("#")[0] for i in existingFeatures.splitlines()]
    existingFeatures = "\n".join(lines)
    if kernFeatureSearch_RE.search(existingFeatures):
        return ""
    if not font.kerning.items():
        return ""
    neededLeftGroups = set()
    neededRightGroups = set()
    noGroup = {}
    leftGroup = {}
    rightGroup = {}
    bothGroup = {}
    for (left, right), value in font.kerning.items():
        if left.startswith("@") and right.startswith("@"):
            bothGroup[left, right] = _roundInt(value)
            neededLeftGroups.add(left)
            neededRightGroups.add(right)
        elif left.startswith("@"):
            leftGroup[left, right] = _roundInt(value)
            neededLeftGroups.add(left)
        elif right.startswith("@"):
            rightGroup[left, right] = _roundInt(value)
            neededRightGroups.add(right)
        else:
            noGroup[left, right] = _roundInt(value)
    lines = ["feature kern {"]
    emptyGroups = set()
    for groupName in sorted(neededLeftGroups):
        contents = font.groups.get(groupName, [])
        if not contents:
            emptyGroups.add(groupName)
            continue
        lines.append("    %s = [%s];" % (groupName, " ".join(contents)))
    for groupName in sorted(neededRightGroups):
        contents = font.groups.get(groupName, [])
        if not contents:
            emptyGroups.add(groupName)
            continue
        lines.append("    %s = [%s];" % (groupName, " ".join(contents)))
    for (left, right), value in sorted(noGroup.items()):
        lines.append("    pos %s %s %d;" % (left, right, value))
    for (left, right), value in sorted(leftGroup.items()):
        if left in emptyGroups:
            continue
        lines.append("    pos %s %s %d;" % (left, right, value))
    for (left, right), value in sorted(rightGroup.items()):
        if right in emptyGroups:
            continue
        lines.append("    pos %s %s %d;" % (left, right, value))
    for (left, right), value in sorted(bothGroup.items()):
        if left in emptyGroups or right in emptyGroups:
            continue
        lines.append("    pos %s %s %d;" % (left, right, value))
    lines.append("} kern;")
    return "\n".join(lines)

def _writeFeaturesTable_head(font):
    versionMajor = getattr(font.info, "versionMajor")
    versionMinor = getattr(font.info, "versionMinor")
    value = "%d.%s" % (versionMajor, str(versionMinor).zfill(3))
    writer = FeatureTableWriter("head")
    writer.addLineWithKeyValue("FontRevision", value)
    return writer.write()

def _writeFeaturesTable_hhea(font):
    ascender = getAttrWithFallback(font.info, "openTypeHheaAscender")
    descender = getAttrWithFallback(font.info, "openTypeHheaDescender")
    lineGap = getAttrWithFallback(font.info, "openTypeHheaLineGap")
    caret = getAttrWithFallback(font.info, "openTypeHheaCaretOffset")
    writer = FeatureTableWriter("hhea")
    writer.addLineWithKeyValue("Ascender", _roundInt(ascender))
    writer.addLineWithKeyValue("Descender", _roundInt(descender))
    writer.addLineWithKeyValue("LineGap", _roundInt(lineGap))
    writer.addLineWithKeyValue("CaretOffset", _roundInt(caret))
    return writer.write()

def _writeFeaturesTable_name(font):
    idToAttr = [
        (0  , "copyright"),
        (7  , "trademark"),
        (8  , "openTypeNameManufacturer"),
        (9  , "openTypeNameDesigner"),
        (10 , "openTypeNameDescription"),
        (11 , "openTypeNameManufacturerURL"),
        (12 , "openTypeNameDesignerURL"),
        (13 , "openTypeNameLicense"),
        (14 , "openTypeNameLicenseURL"),
        (19 , "openTypeNameSampleText")
    ]
    multilineNameTableEntries = {}
    lines = []
    for id, attr in idToAttr:
        value = getAttrWithFallback(font.info, attr)
        if value is None:
            continue
        s = 'nameid %d "%s";' % (id, winStr(value))
        lines.append(s)
        s = 'nameid %d 1 "%s";' % (id, macStr(value))
        lines.append(s)
    if not lines:
        return ""
    writer = FeatureTableWriter("name")
    for line in lines:
        writer.addLine(line)
    return writer.write()

codePageBitTranslation = {
    0  : "1252",
    1  : "1250",
    2  : "1251",
    3  : "1253",
    4  : "1254",
    5  : "1255",
    6  : "1256",
    7  : "1257",
    8  : "1258",
    16 : "874",
    17 : "932",
    18 : "936",
    19 : "949",
    20 : "950",
    21 : "1361",
    48 : "869",
    49 : "866",
    50 : "865",
    51 : "864",
    52 : "863",
    53 : "862",
    54 : "861",
    55 : "860",
    56 : "857",
    57 : "855",
    58 : "852",
    59 : "775",
    60 : "737",
    61 : "708",
    62 : "850",
    63 : "437"
}

def _writeFeaturesTable_OS2(font):
    writer = FeatureTableWriter("OS/2")
    # type
    writer.addLineWithKeyValue("FSType", intListToNum(getAttrWithFallback(font.info, "openTypeOS2Type"), 0, 16))
    # panose
    panose = [str(i) for i in getAttrWithFallback(font.info, "openTypeOS2Panose")]
    writer.addLineWithKeyValue("Panose", " ".join(panose))
    # unicode ranges
    unicodeRange = [str(i) for i in getAttrWithFallback(font.info, "openTypeOS2UnicodeRanges")]
    if unicodeRange:
        writer.addLineWithKeyValue("UnicodeRange", " ".join(unicodeRange))
    # code page ranges
    codePageRange = [codePageBitTranslation[i] for i in getAttrWithFallback(font.info, "openTypeOS2CodePageRanges") if i in codePageBitTranslation]
    if codePageRange:
        writer.addLineWithKeyValue("CodePageRange", " ".join(codePageRange))
    # vertical metrics
    writer.addLineWithKeyValue("TypoAscender", _roundInt(getAttrWithFallback(font.info, "openTypeOS2TypoAscender")))
    writer.addLineWithKeyValue("TypoDescender", _roundInt(getAttrWithFallback(font.info, "openTypeOS2TypoDescender")))
    writer.addLineWithKeyValue("TypoLineGap", _roundInt(getAttrWithFallback(font.info, "openTypeOS2TypoLineGap")))
    writer.addLineWithKeyValue("winAscent", _roundInt(getAttrWithFallback(font.info, "openTypeOS2WinAscent")))
    writer.addLineWithKeyValue("winDescent", _roundInt(getAttrWithFallback(font.info, "openTypeOS2WinDescent")))
    writer.addLineWithKeyValue("XHeight", _roundInt(getAttrWithFallback(font.info, "xHeight")))
    writer.addLineWithKeyValue("CapHeight", _roundInt(getAttrWithFallback(font.info, "capHeight")))
    writer.addLineWithKeyValue("WeightClass", getAttrWithFallback(font.info, "openTypeOS2WeightClass"))
    writer.addLineWithKeyValue("WidthClass", getAttrWithFallback(font.info, "openTypeOS2WidthClass"))
    writer.addLineWithKeyValue("Vendor", '"%s"' % getAttrWithFallback(font.info, "openTypeOS2VendorID"))
    return writer.write()

def _roundInt(value):
    return int(round(value))
