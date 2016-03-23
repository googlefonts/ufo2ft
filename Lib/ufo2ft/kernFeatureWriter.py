from __future__ import print_function, division, absolute_import, unicode_literals

import re


class KernFeatureWriter(object):
    """Generates a kerning feature based on glyph class definitions.

    Uses the kerning rules contained in an UFO's kerning data, as well as glyph
    classes from parsed feature text. Class-based rules are set based on the
    existing rules for their key glyphs.

    Uses class attributes to match glyph class names in feature text as kerning
    classes, which can be overridden.
    """

    leftFeaClassRe = r"@MMK_L_(.+)"
    rightFeaClassRe = r"@MMK_R_(.+)"

    def __init__(self, font):
        self.kerning = dict(font.kerning)
        self.groups = dict(font.groups)
        self.featxt = font.features.text or ""

        # kerning classes found in existing feature text and UFO groups
        self.leftFeaClasses = {}
        self.rightFeaClasses = {}
        self.leftUfoClasses = {}
        self.rightUfoClasses = {}

        # kerning rule collections, mapping pairs to values
        self.glyphPairKerning = {}
        self.leftClassKerning = {}
        self.rightClassKerning = {}
        self.classPairKerning = {}

    def write(self, linesep="\n"):
        """Write kern feature."""

        self._collectFeaClasses()
        self._collectFeaClassKerning()

        self._correctUfoClassNames()
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
            self._addKerning(lines, self.leftClassKerning, enum=True)
        if self.rightClassKerning:
            self._addKerning(lines, self.rightClassKerning, enum=True)
        if self.classPairKerning:
            self._addKerning(lines, self.classPairKerning)
        lines.append("} kern;")

        return linesep.join(lines)

    def _collectFeaClasses(self):
        """Parse glyph classes from existing feature text."""

        for name, contents in re.findall(
                r'(@[\w.]+)\s*=\s*\[([\s\w.@-]*)\]\s*;', self.featxt, re.M):
            if re.match(self.leftFeaClassRe, name):
                self.leftFeaClasses[name] = contents.split()
            elif re.match(self.rightFeaClassRe, name):
                self.rightFeaClasses[name] = contents.split()

    def _collectFeaClassKerning(self):
        """Set up class kerning rules from class definitions in feature text.

        The first glyph from each class (called it's "key") is used to determine
        the kerning values associated with that class.
        """

        for leftName, leftContents in self.leftFeaClasses.items():
            leftKey = leftContents[0]

            # collect rules with two classes
            for rightName, rightContents in self.rightFeaClasses.items():
                rightKey = rightContents[0]
                pair = leftKey, rightKey
                kerningVal = self.kerning.get(pair)
                if kerningVal is None:
                    continue
                self.classPairKerning[leftName, rightName] = kerningVal
                del self.kerning[pair]

            # collect rules with left class and right glyph
            for pair, kerningVal in self._getGlyphKerning(leftKey, 0):
                self.leftClassKerning[leftName, pair[1]] = kerningVal
                del self.kerning[pair]

        # collect rules with left glyph and right class
        for rightName, rightContents in self.rightFeaClasses.items():
            rightKey = rightContents[0]
            for pair, kerningVal in self._getGlyphKerning(rightKey, 1):
                self.rightClassKerning[pair[0], rightName] = kerningVal
                del self.kerning[pair]

    def _correctUfoClassNames(self):
        """Detect and replace illegal class names found in UFO kerning."""

        for oldName, members in self.groups.items():
            newName = self._makeFeaClassName(oldName)
            if oldName == newName:
                continue
            self.groups[newName] = members
            del self.groups[oldName]
            for oldPair, kerningVal in self._getGlyphKerning(oldName):
                left, right = oldPair
                newPair = (newName, right) if left == oldName else (left, newName)
                self.kerning[newPair] = kerningVal
                del self.kerning[oldPair]

    def _collectUfoKerning(self):
        """Sort UFO kerning rules into glyph pair or class rules."""

        for glyphPair, val in sorted(self.kerning.items()):
            left, right = glyphPair
            leftIsClass = left in self.groups
            rightIsClass = right in self.groups
            if leftIsClass:
                self.leftUfoClasses[left] = self.groups[left]
                if rightIsClass:
                    self.classPairKerning[glyphPair] = val
                else:
                    self.leftClassKerning[glyphPair] = val
            elif rightIsClass:
                self.rightUfoClasses[right] = self.groups[right]
                self.rightClassKerning[glyphPair] = val
            else:
                self.glyphPairKerning[glyphPair] = val

    def _removeConflictingKerningRules(self):
        """Remove any conflicting pair and class rules.

        If conflicts are detected in a class rule, the offending class members
        are removed from the rule and the class name is replaced with a list of
        glyphs (the class members minus the offending members).
        """

        leftClasses = dict(self.leftFeaClasses)
        leftClasses.update(self.leftUfoClasses)
        rightClasses = dict(self.rightFeaClasses)
        rightClasses.update(self.rightUfoClasses)

        # maintain list of glyph pair rules seen
        seen = dict(self.glyphPairKerning)

        # remove conflicts in left class / right glyph rules
        for (lClass, rGlyph), val in list(self.leftClassKerning.items()):
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
        for (lGlyph, rClass), val in list(self.rightClassKerning.items()):
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

    def _addGlyphClasses(self, lines):
        """Add glyph classes for the input font's groups."""

        for key, members in sorted(self.groups.items()):
            lines.append("%s = [%s];" % (key, " ".join(members)))

    def _addKerning(self, lines, kerning, enum=False):
        """Add kerning rules for a mapping of pairs to values."""

        enum = "enum " if enum else ""
        for (left, right), val in sorted(kerning.items()):
            lines.append("    %spos %s %s %d;" % (enum, left, right, val))

    def _liststr(self, glyphs):
        """Return string representation of a list of glyph names."""

        return "[%s]" % " ".join(glyphs)

    def _makeFeaClassName(self, name):
        """Make a glyph class name which is legal to use in feature text.

        Ensures the name starts with "@" and only includes characters in
        "A-Za-z0-9._", and isn't already defined.
        """

        name = "@%s" % re.sub(r"[^A-Za-z0-9._]", r"", name)
        existingClassNames = (
            list(self.leftFeaClasses.keys()) + list(self.rightFeaClasses.keys()) +
            list(self.groups.keys()))
        i = 1
        origName = name
        while name in existingClassNames:
            name = "%s_%d" % (origName, i)
            i += 1
        return name

    def _getGlyphKerning(self, glyphName, i=None):
        """Return the kerning rules which include glyphName, optionally only
        checking one side of each pair if index `i` is provided.
        """

        hits = []
        for pair, value in self.kerning.items():
            if (glyphName in pair) if i is None else (pair[i] == glyphName):
                hits.append((pair, value))
        return hits
