from feaTools import parser
from feaTools.writers.baseWriter import AbstractFeatureWriter


class KernFeatureWriter(AbstractFeatureWriter):
    """Generates a kerning feature based on glyph class definitions.

    Uses the kerning rules contained in an RFont's kerning attribute, as well as
    glyph classes from parsed OTF text. Class-based rules are set based on the
    existing rules for their key glyphs.
    """

    def __init__(self, font):
        self.kerning = font.kerning
        self.groups = font.groups
        self.leftClasses = []
        self.rightClasses = []
        self.classSizes = {}
        parser.parseFeatures(self, font.features.text)

    def classDefinition(self, name, contents):
        """Store a class definition as either a left- or right-hand class."""

        if not name.startswith("@_"):
            return
        info = (name, contents)
        if name.endswith("_L"):
            self.leftClasses.append(info)
        elif name.endswith("_R"):
            self.rightClasses.append(info)
        self.classSizes[name] = len(contents)

    def _addGlyphClasses(self, lines):
        """Add glyph classes for the input font's groups."""

        for key, members in self.groups.iteritems():
            lines.append("%s = [%s];" % (key, " ".join(members)))

    def _addKerning(self, lines, kerning=None, enum=False):
        """Add kerning rules for a mapping of pairs to values."""

        usingFontKerning = False
        if kerning is None:
            usingFontKerning = True
            kerning = self.kerning

        enum = "enum " if enum else ""
        pairs = kerning.items()
        pairs.sort()

        for (left, right), val in pairs:
            if usingFontKerning:
                leftIsClass = left.startswith("@")
                rightIsClass = right.startswith("@")
                if leftIsClass:
                    if rightIsClass:
                        self.classPairKerning[left, right] = val
                    else:
                        self.leftClassKerning[left, right] = val
                    continue
                elif rightIsClass:
                    self.rightClassKerning[left, right] = val
                    continue

            if enum:
                rulesAdded = (self.classSizes.get(left, 1) *
                              self.classSizes.get(right, 1))
            else:
                rulesAdded = 1
            self.ruleCount += rulesAdded
            if self.ruleCount > 1024:
                lines.append("    subtable;")
                self.ruleCount = rulesAdded

            lines.append("    %spos %s %s %d;" % (enum, left, right, val))

    def _collectClassKerning(self):
        """Set up collections of different rule types."""

        self.leftClassKerning = {}
        self.rightClassKerning = {}
        self.classPairKerning = {}

        for leftName, leftContents in self.leftClasses:
            leftKey = leftContents[0]

            # collect rules with two classes
            for rightName, rightContents in self.rightClasses:
                rightKey = rightContents[0]
                pair = leftKey, rightKey
                kerningVal = self.kerning[pair]
                if kerningVal is None:
                    continue
                classPairKerning[leftName, rightName] = kerningVal
                self.kerning.remove(pair)

            # collect rules with left class and right glyph
            for pair, kerningVal in self.kerning.getLeft(leftKey):
                self.leftClassKerning[leftName, pair[1]] = kerningVal
                self.kerning.remove(pair)

        # collect rules with left glyph and right class
        for rightName, rightContents in self.rightClasses:
            rightKey = rightContents[0]
            for pair, kerningVal in self.kerning.getRight(rightKey):
                self.rightClassKerning[pair[0], rightName] = kerningVal
                self.kerning.remove(pair)

    def write(self, linesep="\n"):
        """Write kern feature."""

        self._collectClassKerning()

        # write the glyph classes
        lines = []
        self._addGlyphClasses(lines)
        lines.append("")

        # write the feature
        self.ruleCount = 0
        lines.append("feature kern {")
        self._addKerning(lines)
        self._addKerning(lines, self.leftClassKerning, enum=True)
        self._addKerning(lines, self.rightClassKerning, enum=True)
        self._addKerning(lines, self.classPairKerning)
        lines.append("} kern;")
        return linesep.join(lines)
