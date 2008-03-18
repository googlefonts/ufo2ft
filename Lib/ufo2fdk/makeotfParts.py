import os
import shutil
import re
from outlineOTF import makePSName, makeOutlineOTF
from featureTableWriter import FeatureTableWriter, winStr, macStr
from outlineOTF import makeOutlineOTF, getFontBBox


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
    multilineNameTableEntries = _setupFeatures(font, featuresPath)

    outlinePath = os.path.join(path, "font.otf")
    makeOutlineOTF(font, outlinePath, glyphOrder)

    paths = dict(
        outlineSourcePath=outlinePath,
        menuNamePath=menuNamePath,
        glyphOrderPath=glyphOrderPath,
        fontInfoPath=fontInfoPath,
        featuresPath=featuresPath)
    return paths, multilineNameTableEntries

def _setupMenuNameDB(font, path):
    familyName = font.info.otFamilyName
    styleName = font.info.otStyleName
    winCompatible = font.info.menuName
    macCompatible = winCompatible
    if font.info.fontStyle:
        if font.info.fontStyle & 32 and font.info.fontStyle & 1:
            macCompatible = "%s BoldItalic" % winCompatible
        elif font.info.fontStyle & 32:
            macCompatible = "%s Bold" % winCompatible
        elif font.info.fontStyle & 1:
            macCompatible = "%s Italic" % winCompatible
    lines = [
        "[%s]" % makePSName(font),
        "f=%s" % familyName,
        "s=%s" % styleName,
        "c=%s" % winCompatible, 
        "c=1,%s" % macCompatible
    ]
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
    fontStyle = font.info.fontStyle
    if fontStyle is None:
        return
    # 64 : regular
    # 32 : italic
    # 1 : bold
    # 33 : bold italic
    lines = []
    if font.info.fontStyle & 1:
        lines.append("IsItalicStyle true")
    else:
        lines.append("IsItalicStyle false")
    if font.info.fontStyle & 32:
        lines.append("IsBoldStyle true")
    else:
        lines.append("IsBoldStyle false")
    lines.append("PreferOS/2TypoMetricsPreferOS/2TypoMetrics true")
    lines.append("IsOS/2WidthWeigthSlopeOnlyIsOS/2WidthWeigthSlopeOnly true")
    lines.append("IsOS/2OBLIQUEIsOS/2OBLIQUE false")
    if lines:
        f = open(path, "wb")
        f.write("\n".join(lines))
        f.close()

def _setupFeatures(font, path):
    # XXX where should the features be drawn from?
    featuresPath = os.path.join(font.path, "features.fea")
    if os.path.exists(featuresPath):
        f = open(featuresPath, "rb")
        features = f.read()
        f.close()
    else:
        features = ""
    features = _forceAbsoluteIncludesInFeatures(features, os.path.dirname(path))
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
        ""
    ]
    nameTable, multilineNameTableEntries = _writeFeaturesTable_name(font)
    tables.append(nameTable)
    tables = "\n".join(tables)
    features = "\n".join([tables])
    f = open(path, "wb")
    f.write(features)
    f.close()
    return multilineNameTableEntries

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
    versionMajor = font.info.versionMajor
    versionMinor = font.info.versionMinor
    if versionMajor is None:
        versionMajor = 0
    if versionMinor is None:
        versionMinor = 0
    value = "%d.%s" % (versionMajor, str(versionMinor).zfill(3))
    writer = FeatureTableWriter("head")
    writer.addLineWithKeyValue("FontRevision", value)
    return writer.write()

def _writeFeaturesTable_hhea(font):
    # XXX is the caret necessary?
    ascender = font.info.unitsPerEm - abs(font.info.descender)
    descender = font.info.descender
    # XXX lineGap = naked.ttinfo.hhea_line_gap
    writer = FeatureTableWriter("hhea")
    writer.addLineWithKeyValue("Ascender", _roundInt(ascender))
    writer.addLineWithKeyValue("Descender", _roundInt(descender))
    #writer.addLineWithKeyValue("LineGap", lineGap)
    return writer.write()

def _writeFeaturesTable_name(font):
    idToAttr = [
        (0  , "copyright"),
        (7  , "trademark"),
        (8  , "createdBy"),
        (9  , "designer"),
        (10 , "notice"), # description
        (11 , "vendorURL"),
        (12 , "designerURL"),
        (13 , "license"),
        (14 , "licenseURL"),
        #(19 , "sampleText")
    ]
    multilineNameTableEntries = {}
    lines = []
    for id, attr in idToAttr:
        value = getattr(font.info, attr)
        if value is None:
            continue
        if len(value.splitlines()) > 1:
            multilineNameTableEntries[id] = value
            continue
        s = 'nameid %d "%s";' % (id, winStr(value))
        lines.append(s)
        s = 'nameid %d 1 "%s";' % (id, macStr(value))
        lines.append(s)
    if not lines:
        return "", {}
    writer = FeatureTableWriter("name")
    for line in lines:
        writer.addLine(line)
    return writer.write(), multilineNameTableEntries

def _writeFeaturesTable_OS2(font):
    widthNames = [
        "Ultra-condensed",
        "Extra-condensed",
        "Condensed",
        "Semi-condensed",
        "Medium (normal)",
        "Semi-expanded",
        "Expanded",
        "Extra-expanded",
        "Ultra-expanded"
    ]
    writer = FeatureTableWriter("OS/2")
    xMin, yMin, xMax, yMax = getFontBBox(font)
    #writer.addLineWithKeyValue("FSType", font.info.fsType)
    #panose = [str(i) for i in naked.panose]
    #writer.addLineWithKeyValue("Panose", " ".join(panose))
    #unicodeRange = [str(i) for i in font.info.unicodeRange]
    #if unicodeRange:
    #    writer.addLineWithKeyValue("UnicodeRange", " ".join(unicodeRange))
    #codePageRange = [str(i) for i in font.info.codePageRange]
    #if codePageRange:
    #    writer.addLineWithKeyValue("CodePageRange", " ".join(codePageRange))
    writer.addLineWithKeyValue("TypoAscender", _roundInt(font.info.unitsPerEm - abs(font.info.descender)))
    writer.addLineWithKeyValue("TypoDescender", _roundInt(font.info.descender))
    # writer.addLineWithKeyValue("TypoLineGap", naked.ttinfo.os2_s_typo_line_gap)
    writer.addLineWithKeyValue("winAscent", _roundInt(yMax))
    writer.addLineWithKeyValue("winDescent", _roundInt(yMin))
    writer.addLineWithKeyValue("XHeight", _roundInt(font.info.xHeight))
    writer.addLineWithKeyValue("CapHeight", _roundInt(font.info.capHeight))
    writer.addLineWithKeyValue("WeightClass", _roundInt(font.info.weightValue))
    widthName = font.info.widthName
    if widthName in widthNames:
        value = widthNames.index(widthName) + 1
        writer.addLineWithKeyValue("WidthClass", _roundInt(value))
    writer.addLineWithKeyValue("Vendor", '"%s"' % font.info.ttVendor)
    return writer.write()

def _roundInt(value):
    return int(round(value))
