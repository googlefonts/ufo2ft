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

    def _addKerning(self, lines, kerning, enum=False):
        """Add kerning rules for a mapping of pairs to values."""

        enum = "enum " if enum else ""
        pairs = kerning.items()
        pairs.sort()
        for (left, right), val in pairs:
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

    def write(self, linesep="\n"):
        """Write kern feature."""

        # maintain collections of different rule types
        leftClassKerning, rightClassKerning, classPairKerning = {}, {}, {}
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
                leftClassKerning[leftName, pair[1]] = kerningVal
                self.kerning.remove(pair)

        # collect rules with left glyph and right class
        for rightName, rightContents in self.rightClasses:
            rightKey = rightContents[0]
            for pair, kerningVal in self.kerning.getRight(rightKey):
                rightClassKerning[pair[0], rightName] = kerningVal
                self.kerning.remove(pair)

        # write the feature
        self.ruleCount = 0
        lines = ["feature kern {"]
        self._addKerning(lines, self.kerning)
        self._addKerning(lines, leftClassKerning, enum=True)
        self._addKerning(lines, rightClassKerning, enum=True)
        self._addKerning(lines, classPairKerning)
        lines.append("} kern;")
        return linesep.join(lines)
