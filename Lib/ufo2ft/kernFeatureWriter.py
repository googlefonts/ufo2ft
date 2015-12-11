from __future__ import print_function, division, absolute_import, unicode_literals

import re

from feaTools import parser
from feaTools.writers.baseWriter import AbstractFeatureWriter


class KernFeatureWriter(AbstractFeatureWriter):
    """Generates a kerning feature based on glyph class definitions.

    Uses the kerning rules contained in an RFont's kerning attribute, as well as
    glyph classes from parsed OTF text. Class-based rules are set based on the
    existing rules for their key glyphs.

    Uses class attributes to match UFO glyph group names and feature syntax
    glyph class names as kerning classes, which can be overridden.
    """

    leftUfoGroupRe = r"^public\.kern1\.(.+)"
    rightUfoGroupRe = r"^public\.kern2\.(.+)"
    leftFeaClassRe = r"@MMK_L_(.+)"
    rightFeaClassRe = r"@MMK_R_(.+)"

    def __init__(self, font):
        self.kerning = font.kerning
        self.groups = font.groups
        self.leftClasses = []
        self.rightClasses = []
        parser.parseFeatures(self, font.features.text)

    def _isGlyphClass(self, name, nameRe):
        return re.match(nameRe, name) is not None

    def classDefinition(self, name, contents):
        """Store a class definition as either a left- or right-hand class."""

        info = (name, contents)
        if self._isGlyphClass(self.leftFeaClassRe, name):
            self.leftClasses.append(info)
        elif self._isGlyphClass(self.rightFeaClassRe, name):
            self.rightClasses.append(info)

    def _addGlyphClasses(self, lines):
        """Add glyph classes for the input font's groups."""

        for key, members in self.groups.items():
            lines.append("%s = [%s];" % (key, " ".join(members)))

    def _addKerning(self, lines, kerning=None, enum=False):
        """Add kerning rules for a mapping of pairs to values."""

        usingFontKerning = False
        if kerning is None:
            usingFontKerning = True
            kerning = self.kerning

        enum = "enum " if enum else ""

        for (left, right), val in sorted(kerning.items()):
            if usingFontKerning:
                leftIsClass = self._isGlyphClass(self.leftUfoGroupRe, left)
                rightIsClass = self._isGlyphClass(self.rightUfoGroupRe, right)
                if leftIsClass:
                    if rightIsClass:
                        self.classPairKerning[left, right] = val
                    else:
                        self.leftClassKerning[left, right] = val
                    continue
                elif rightIsClass:
                    self.rightClassKerning[left, right] = val
                    continue

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
                self.classPairKerning[leftName, rightName] = kerningVal
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
        lines.append("feature kern {")
        self._addKerning(lines)
        lines.append("    subtable;")
        self._addKerning(lines, self.leftClassKerning, enum=True)
        lines.append("    subtable;")
        self._addKerning(lines, self.rightClassKerning, enum=True)
        lines.append("    subtable;")
        self._addKerning(lines, self.classPairKerning)
        lines.append("} kern;")

        # return the feature, unless it's empty
        return "" if len([ln for ln in lines if ln]) == 5 else linesep.join(lines)
