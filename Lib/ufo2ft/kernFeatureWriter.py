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
        self.featxt = font.features.text

        # kerning classes found in existing OTF syntax and UFO groups
        self.leftFeaClasses = {}
        self.rightFeaClasses = {}
        self.leftUfoClasses = {}
        self.rightUfoClasses = {}

        # kerning rule collections, mapping pairs to values
        self.glyphPairKerning = {}
        self.leftClassKerning = {}
        self.rightClassKerning = {}
        self.classPairKerning = {}

    def classDefinition(self, name, contents):
        """Store a class definition as either a left- or right-hand class."""

        if self._isClassName(self.leftFeaClassRe, name):
            self.leftFeaClasses[name] = contents
        elif self._isClassName(self.rightFeaClassRe, name):
            self.rightFeaClasses[name] = contents

    def write(self, linesep="\n"):
        """Write kern feature."""

        self._collectFeaClasses()
        self._collectFeaClassKerning()
        self._collectUfoClasses()
        self._collectUfoKerning()
        self._removeConflictingKerningRules()

        if not any([self.glyphPairKerning, self.leftClassKerning,
                    self.rightClassKerning, self.classPairKerning]):
            # no kerning pairs, don't write empty feature
            return ""

        # write the glyph classes
        lines = []
        self._addGlyphClasses(lines)
        lines.append("")

        # write the feature
        lines.append("feature kern {")
        self._addKerning(lines, self.glyphPairKerning)
        if self.leftClassKerning:
            lines.append("    subtable;")
            self._addKerning(lines, self.leftClassKerning, enum=True)
        if self.rightClassKerning:
            lines.append("    subtable;")
            self._addKerning(lines, self.rightClassKerning, enum=True)
        if self.classPairKerning:
            lines.append("    subtable;")
            self._addKerning(lines, self.classPairKerning)
        lines.append("} kern;")

        return linesep.join(lines)

    def _collectFeaClasses(self):
        """Parse glyph classes from existing OTF syntax."""

        parser.parseFeatures(self, self.featxt)

    def _collectFeaClassKerning(self):
        """Set up class kerning rules from OTF glyph class definitions.

        The first glyph from each class (called it's "key") is used to determine
        the kerning values associated with that class.
        """

        for leftName, leftContents in self.leftFeaClasses.items():
            leftKey = leftContents[0]

            # collect rules with two classes
            for rightName, rightContents in self.rightFeaClasses.items():
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
        for rightName, rightContents in self.rightFeaClasses.items():
            rightKey = rightContents[0]
            for pair, kerningVal in self.kerning.getRight(rightKey):
                self.rightClassKerning[pair[0], rightName] = kerningVal
                self.kerning.remove(pair)

    def _collectUfoClasses(self):
        """Sort UFO groups into left or right glyph classes."""

        for name, contents in self.groups.items():
            if self._isClassName(self.leftUfoGroupRe, name):
                self.leftUfoClasses[self._makeFeaClassName(name)] = contents
            if self._isClassName(self.rightUfoGroupRe, name):
                self.rightUfoClasses[self._makeFeaClassName(name)] = contents

    def _collectUfoKerning(self):
        """Sort UFO kerning rules into glyph pair or class rules."""

        for glyphPair, val in sorted(self.kerning.items()):
            left, right = glyphPair
            leftIsClass = self._isClassName(self.leftUfoGroupRe, left)
            rightIsClass = self._isClassName(self.rightUfoGroupRe, right)
            if leftIsClass:
                if rightIsClass:
                    self.classPairKerning[glyphPair] = val
                else:
                    self.leftClassKerning[glyphPair] = val
            elif rightIsClass:
                self.rightClassKerning[glyphPair] = val
            else:
                self.glyphPairKerning[glyphPair] = val

    def _removeConflictingKerningRules(self):
        """Remove any conflicting pair and class rules.

        If conflicts are detected in a class rule, the offending class members
        are removed from the rule and the class name is replaced with a list of
        glyphs (the class members minus the offending members).
        """

        leftClasses = dict(
            self.leftFeaClasses.items() + self.leftUfoClasses.items())
        rightClasses = dict(
            self.rightFeaClasses.items() + self.rightUfoClasses.items())

        # maintain list of glyph pair rules seen
        seen = dict(self.glyphPairKerning)

        # remove conflicts in left class / right glyph rules
        for (lClass, rGlyph), val in self.leftClassKerning.items():
            lGlyphs = leftClasses[lClass]
            nlGlyphs = []
            for lGlyph in lGlyphs:
                pair = lGlyph, rGlyph
                if pair not in seen:
                    nlGlyphs.append(lGlyph)
                    seen[pair] = val
            if nlGlyphs != lGlyphs:
                self.leftClassKerning[self._liststr(nlGlyphs), rGlyph] = val
                del self.leftClassKerning[lClass, rGlyph]

        # remove conflicts in left glyph / right class rules
        for (lGlyph, rClass), val in self.rightClassKerning.items():
            rGlyphs = rightClasses[rClass]
            nrGlyphs = []
            for rGlyph in rGlyphs:
                pair = lGlyph, rGlyph
                if pair not in seen:
                    nrGlyphs.append(rGlyph)
                    seen[pair] = val
            if nrGlyphs != rGlyphs:
                self.rightClassKerning[lGlyph, self._liststr(nrGlyphs)] = val
                del self.rightClassKerning[lGlyph, rClass]

        # remove conflicts in class / class rules
        for (lClass, rClass), val in self.classPairKerning.items():
            lGlyphs = leftClasses[lClass]
            rGlyphs = rightClasses[rClass]
            nlGlyphs, nrGlyphs = set(), set()
            for lGlyph in lGlyphs:
                for rGlyph in rGlyphs:
                    pair = lGlyph, rGlyph
                    if pair not in seen:
                        nlGlyphs.add(lGlyph)
                        nrGlyphs.add(rGlyph)
                        seen[pair] = val
            nlClass, nrClass = lClass, rClass
            if nlGlyphs != set(lGlyphs):
                nlClass = self._liststr(sorted(nlGlyphs))
            if nrGlyphs != set(rGlyphs):
                nrClass = self._liststr(sorted(nrGlyphs))
            if nlClass != lClass or nrClass != rClass:
                self.classPairKerning[nlClass, nrClass] = val
                del self.classPairKerning[lClass, rClass]

    def _addGlyphClasses(self, lines):
        """Add glyph classes for the input font's groups."""

        for key, members in sorted(self.leftUfoClasses.items() +
                                   self.rightUfoClasses.items()):
            lines.append("%s = [%s];" % (key, " ".join(members)))

    def _addKerning(self, lines, kerning, enum=False):
        """Add kerning rules for a mapping of pairs to values."""

        enum = "enum " if enum else ""
        for (left, right), val in sorted(kerning.items()):
            lines.append("    %spos %s %s %d;" % (enum, left, right, val))

    def _liststr(self, glyphs):
        """Return string representation of a list of glyph names."""

        return "[%s]" % " ".join(glyphs)

    def _isClassName(self, nameRe, name):
        """Return whether a given name matches a given class name regex."""

        return re.match(nameRe, name) is not None

    def _makeFeaClassName(self, name):
        """Make a glyph class name which is legal to use in OTF syntax.

        Ensures the name starts with "@" and only includes characters in
        "A-Za-z0-9._", and isn't already defined.
        """

        if not name.startswith("@"):
            name = "@" + name
        name = re.sub(r"[^A-Za-z0-9._]", r"", name)
        existingClassNames = (
            self.leftFeaClasses.keys() + self.rightFeaClasses.keys() +
            self.leftUfoClasses.keys() + self.rightUfoClasses.keys())
        if name in existingClassNames:
            raise ValueError('New glyph class name "%s" (from UFO groups) '
                             'is the name of an existing class.')
        return name
