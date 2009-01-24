import os
import shutil
import re
from fontInfoData import getAttrWithFallback, intListToNum
from outlineOTF import OutlineOTFCompiler
from featureTableWriter import FeatureTableWriter, winStr, macStr


class MakeOTFPartsCompiler(object):

    """
    This object will create the "parts" needed by the FDK.
    The only external method is :meth:`ufo2fdk.tools.makeotfParts.compile`.
    There is one attribute, :attr:`ufo2fdk.tools.makeotfParts.path`
    that may be referenced externally. That is a dictionary of
    paths to the various parts.

    When creating this object, you must provide a *font*
    object and a *path* indicating where the parts should
    be saved. Optionally, you can provide a *glyphOrder*
    list of glyph names indicating the order of the glyphs
    in the font. You may also provide an *outlineCompilerClass*
    argument that will serve as the outline source compiler.
    The class passed for this argument must be a subclass of
    :class:`ufo2fdk.tools.outlineOTF.OutlineOTFCompiler`.
    """

    def __init__(self, font, path, glyphOrder=None, outlineCompilerClass=OutlineOTFCompiler):
        self.font = font
        self.path = path
        self.outlineCompilerClass = outlineCompilerClass
        # store the glyph order
        if glyphOrder is None:
            glyphOrder = sorted(font.keys())
        self.glyphOrder = glyphOrder
        # make the paths for all files
        self.paths = dict(
            outlineSource=os.path.join(path, "font.otf"),
            menuName=os.path.join(path, "menuname"),
            glyphOrder=os.path.join(path, "glyphOrder"),
            fontInfo=os.path.join(path, "fontinfo"),
            features=os.path.join(path, "features")
        )

    def compile(self):
        """
        Compile the parts.
        """
        # set up the parts directory removing
        # an existing directory if necessary.
        if os.path.exists(self.path):
            shutil.rmtree(self.path)
        os.mkdir(self.path)
        # build the parts
        self.setupFile_outlineSource(self.paths["outlineSource"])
        self.setupFile_menuName(self.paths["menuName"])
        self.setupFile_glyphOrder(self.paths["glyphOrder"])
        self.setupFile_fontInfo(self.paths["fontInfo"])
        self.setupFile_features(self.paths["features"])

    def setupFile_outlineSource(self, path):
        """
        Make the outline source file.

        **This should not be called externally.** Subclasses
        may override this method to handle the file creation
        in a different way if desired.
        """
        c = OutlineOTFCompiler(self.font, path, self.glyphOrder)
        c.compile()

    def setupFile_menuName(self, path):
        """
        Make the menu name source file.

        **This should not be called externally.** Subclasses
        may override this method to handle the file creation
        in a different way if desired.
        """
        psName = getAttrWithFallback(self.font.info,"postscriptFontName")
        familyName = getAttrWithFallback(self.font.info,"openTypeNamePreferredFamilyName")
        styleName = getAttrWithFallback(self.font.info,"openTypeNamePreferredSubfamilyName")
        winCompatible = getAttrWithFallback(self.font.info,"styleMapFamilyName")
        macCompatible = getAttrWithFallback(self.font.info,"openTypeNameCompatibleFullName")
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

    def setupFile_glyphOrder(self, path):
        """
        Make the glyph order source file.

        **This should not be called externally.** Subclasses
        may override this method to handle the file creation
        in a different way if desired.
        """
        lines = []
        for glyphName in self.glyphOrder:
            if glyphName in self.font and self.font[glyphName].unicode is not None:
                code = self.font[glyphName].unicode
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

    def setupFile_fontInfo(self, path):
        lines = []
        # style mapping
        styleMapStyleName = getAttrWithFallback(self.font.info,"styleMapStyleName")
        if styleMapStyleName in ("italic", "bold italic"):
            lines.append("IsItalicStyle true")
        else:
            lines.append("IsItalicStyle false")
        if styleMapStyleName in ("bold", "bold italic"):
            lines.append("IsBoldStyle true")
        else:
            lines.append("IsBoldStyle false")
        # fsSelection bits
        selection = getAttrWithFallback(self.font.info,"openTypeOS2Selection")
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

    def setupFile_features(self, path):
        """
        Make the features source file.

        **This should not be called externally.** Subclasses
        may override this method to handle the file creation
        in a different way if desired.
        """
        # force absolute includes into the features
        existing = forceAbsoluteIncludesInFeatures(self.font.features.text, self.font.path)
        # break the features into parts
        initialText, features, tables = breakFeaturesAndTables(existing)
        # extract the relevant parts from the features and tables
        gsubGpos = [initialText]
        kernFeature = None
        for name, text in features:
            if name == "kern":
                kernFeature = text
            else:
                gsubGpos.append(text)
        gsubGpos = "\n".join(gsubGpos).strip()
        if not gsubGpos:
            gsubGpos = None
        unknownTables = []
        headTable = None
        hheaTable = None
        os2Table = None
        nameTable = None
        for name, text in tables:
            if name == "head":
                headTable = text
            elif name == "hhea":
                hheaTable = text
            elif name == "OS/2":
                os2Table = text
            elif name == "name":
                nameTable = text
            else:
                unknownTables.append(text)
        unknownTables = "\n".join(unknownTables)
        # compile the new features
        features = [
            self.writeFeatures_basic(gsubGpos),
            "",
            self.writeFeatures_kern(kernFeature),
            "",
            self.writeFeatures_head(headTable),
            "",
            self.writeFeatures_hhea(hheaTable),
            "",
            self.writeFeatures_OS2(os2Table),
            "",
            self.writeFeatures_name(nameTable),
            "",
            unknownTables
        ]
        features = "\n".join(features)
        # write the result
        f = open(path, "wb")
        f.write(features)
        f.close()

    def writeFeatures_basic(self, existing):
        """
        Write the GSUB and GPOS features, excluding kern,
        to a string and return it. *existing* will be
        the existing GSUB and GPOS features in the font
        excluding kern.

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        if existing is None:
            return ""
        return existing

    def writeFeatures_kern(self, existing):
        """
        Write the kern feature to a string and return it.
        *existing* will be the existing kern feature in the font.

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        if existing is not None:
            return existing
        font = self.font
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

    def writeFeatures_head(self, existing):
        """
        Write the head to a string and return it.
        *existing* will be the existing head table in the font.

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        if existing is not None:
            return existing
        versionMajor = getattr(self.font.info, "versionMajor")
        versionMinor = getattr(self.font.info, "versionMinor")
        value = "%d.%s" % (versionMajor, str(versionMinor).zfill(3))
        writer = FeatureTableWriter("head")
        writer.addLineWithKeyValue("FontRevision", value)
        return writer.write()

    def writeFeatures_hhea(self, existing):
        """
        Write the hhea to a string and return it.
        *existing* will be the existing hhea table in the font.

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        if existing is not None:
            return existing
        ascender = getAttrWithFallback(self.font.info, "openTypeHheaAscender")
        descender = getAttrWithFallback(self.font.info, "openTypeHheaDescender")
        lineGap = getAttrWithFallback(self.font.info, "openTypeHheaLineGap")
        caret = getAttrWithFallback(self.font.info, "openTypeHheaCaretOffset")
        writer = FeatureTableWriter("hhea")
        writer.addLineWithKeyValue("Ascender", _roundInt(ascender))
        writer.addLineWithKeyValue("Descender", _roundInt(descender))
        writer.addLineWithKeyValue("LineGap", _roundInt(lineGap))
        writer.addLineWithKeyValue("CaretOffset", _roundInt(caret))
        return writer.write()

    def writeFeatures_name(self, existing):
        """
        Write the name to a string and return it.
        *existing* will be the existing name table in the font.

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        if existing is not None:
            return existing
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
            value = getAttrWithFallback(self.font.info, attr)
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

    def writeFeatures_OS2(self, existing):
        """
        Write the OS/2 to a string and return it.
        *existing* will be the existing OS/2 table in the font.

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        if existing is not None:
            return existing
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
        # writer
        writer = FeatureTableWriter("OS/2")
        # type
        writer.addLineWithKeyValue("FSType", intListToNum(getAttrWithFallback(self.font.info, "openTypeOS2Type"), 0, 16))
        # panose
        panose = [str(i) for i in getAttrWithFallback(self.font.info, "openTypeOS2Panose")]
        writer.addLineWithKeyValue("Panose", " ".join(panose))
        # unicode ranges
        unicodeRange = [str(i) for i in getAttrWithFallback(self.font.info, "openTypeOS2UnicodeRanges")]
        if unicodeRange:
            writer.addLineWithKeyValue("UnicodeRange", " ".join(unicodeRange))
        # code page ranges
        codePageRange = [codePageBitTranslation[i] for i in getAttrWithFallback(self.font.info, "openTypeOS2CodePageRanges") if i in codePageBitTranslation]
        if codePageRange:
            writer.addLineWithKeyValue("CodePageRange", " ".join(codePageRange))
        # vertical metrics
        writer.addLineWithKeyValue("TypoAscender", _roundInt(getAttrWithFallback(self.font.info, "openTypeOS2TypoAscender")))
        writer.addLineWithKeyValue("TypoDescender", _roundInt(getAttrWithFallback(self.font.info, "openTypeOS2TypoDescender")))
        writer.addLineWithKeyValue("TypoLineGap", _roundInt(getAttrWithFallback(self.font.info, "openTypeOS2TypoLineGap")))
        writer.addLineWithKeyValue("winAscent", _roundInt(getAttrWithFallback(self.font.info, "openTypeOS2WinAscent")))
        writer.addLineWithKeyValue("winDescent", _roundInt(getAttrWithFallback(self.font.info, "openTypeOS2WinDescent")))
        writer.addLineWithKeyValue("XHeight", _roundInt(getAttrWithFallback(self.font.info, "xHeight")))
        writer.addLineWithKeyValue("CapHeight", _roundInt(getAttrWithFallback(self.font.info, "capHeight")))
        writer.addLineWithKeyValue("WeightClass", getAttrWithFallback(self.font.info, "openTypeOS2WeightClass"))
        writer.addLineWithKeyValue("WidthClass", getAttrWithFallback(self.font.info, "openTypeOS2WidthClass"))
        writer.addLineWithKeyValue("Vendor", '"%s"' % getAttrWithFallback(self.font.info, "openTypeOS2VendorID"))
        return writer.write()


def forceAbsoluteIncludesInFeatures(text, directory):
    """
    Convert relative includes in the *text*
    to absolute includes.
    """
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

def _roundInt(value):
    return int(round(value))

# ----------------------
# Basic Feature Splitter
# ----------------------

stringRE = re.compile(
    "(\"[^$\"]*\")"
)
featureTableStartRE = re.compile(
    "("
    "feature"
    "\s+"
    "\S{4}"
    "\s*"
    "\{"
    "|"
    "table"
    "\s+"
    "\S{4}"
    "\s*"
    "\{"
    ")",
    re.MULTILINE
)
featureNameRE = re.compile(
    "feature"
    "\s+"
    "(\S{4})"
    "\s*"
    "\{"
)
tableNameRE = re.compile(
    "table"
    "\s+"
    "(\S{4})"
    "\s*"
    "\{"
)

def breakFeaturesAndTables(text):
    # strip all comments
    decommentedLines = [line.split("#")[0] for line in text.splitlines()]
    text = "\n".join(decommentedLines)
    # replace all strings with temporary placeholders.
    destringedLines = []
    stringReplacements = {}
    for line in text.splitlines():
        if "\"" in line:
            line = line.replace("\\\"", "__ufo2fdk_temp_escaped_quote__")
            for found in stringRE.findall(line):
                temp = "__ufo2fdk_temp_string_%d__" % len(stringReplacements)
                line = line.replace(found, temp, 1)
                stringReplacements[temp] = found.replace("__ufo2fdk_temp_escaped_quote__", "\\\"")
            line = line.replace("__ufo2fdk_temp_escaped_quote__", "\\\"")
        destringedLines.append(line)
    text = "\n".join(destringedLines)
    # slice off the text that comes before
    # the first feature/table definition
    precedingText = ""
    startMatch = featureTableStartRE.search(text)
    if startMatch is not None:
        start, end = startMatch.span()
        precedingText = text[:start].strip()
        text = text[start:]
    # break the features
    broken = _textBreakRecurse(text)
    # organize into tables and features
    features = []
    tables = []
    for text in broken:
        text = text.strip()
        if not text:
            continue
        # replace the strings
        finalText = text
        for temp, original in stringReplacements.items():
            if temp in finalText:
                del stringReplacements[temp]
                finalText = finalText.replace(temp, original, 1)
        finalText = finalText.strip()
        # grab feature or table names and store
        featureMatch = featureNameRE.search(text)
        if featureMatch is not None:
            features.append((featureMatch.group(1), finalText))
        else:
            tableMatch = tableNameRE.search(text)
            tables.append((tableMatch.group(1), finalText))
    return precedingText, features, tables

def _textBreakRecurse(text):
    matched = []
    match = featureTableStartRE.search(text)
    if match is None:
        matched.append(text)
    else:
        start, end = match.span()
        # add any preceding text to the previous item
        if start != 0:
            precedingText = matched.pop(0)
            precedingText += text[:start]
            matched.insert(0, precedingText)
        # look ahead to see if there is another feature
        next = text[end:]
        nextMatch = featureTableStartRE.search(next)
        if nextMatch is None:
            # if nothing has been found, add
            # the remaining text to the feature
            matchedText = text[start:]
            matched.append(matchedText)
        else:
            # if one has been found, grab all text
            # from before the feature start and add
            # it to the current feature.
            nextStart, nextEnd = nextMatch.span()
            matchedText = text[:end + nextStart]
            matched.append(matchedText)
            # recurse through the remaining text
            matched += _textBreakRecurse(next[nextStart:])
    return matched


breakFeaturesAndTablesTestText = """
@foo = [bar];

# test commented item
#feature fts1 {
#    sub foo by bar;
#} fts1;

feature fts2 {
    sub foo by bar;
} fts2;

table tts1 {
    nameid 1 "feature this { is not really a \\\"feature that { other thing is";
} tts1;feature fts3 { sub a by b;} fts3;
"""

breakFeaturesAndTablesTestResult = ('@foo = [bar];',
 [('fts2', 'feature fts2 {\n    sub foo by bar;\n} fts2;'),
  ('fts3', 'feature fts3 { sub a by b;} fts3;')],
 [('tts1',
   'table tts1 {\n    nameid 1 "feature this { is not really a \\"feature that { other thing is";\n} tts1;')])

def testBreakFeaturesAndTables():
    """
    >>> r = breakFeaturesAndTables(breakFeaturesAndTablesTestText)
    >>> r == breakFeaturesAndTablesTestResult
    True
    """

if __name__ == "__main__":
    import doctest
    doctest.testmod()
