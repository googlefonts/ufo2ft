from __future__ import print_function, division, absolute_import, unicode_literals


class MarkFeatureWriter(object):
    """Generates a mark or mkmk feature based on glyph anchors.

    Takes in a list of <anchorName, accentAnchorName> tuples, which may
    additionally include boolean parameters indicating whether to only include
    combining accents and whether to expand the rule to aliased glyphs.

    Takes in a list of aliases as tuples, each typically a base glyph and a
    composite including the base glyph.
    """

    def __init__(self, font, anchorList, mkmkAnchorList=(), ligaAnchorList=(),
                 aliases=()):
        self.font = font
        self.anchorList = anchorList
        self.mkmkAnchorList = mkmkAnchorList
        self.ligaAnchorList = ligaAnchorList
        self.aliases = aliases
        self.accentGlyphNames = set()

    def _generateClassName(self, accentAnchorName):
        """Generate a mark class name shared by class definition and positioning
        statements.
        """

        return "@MC%s" % accentAnchorName

    def _getAlias(self, name):
        """Return an alias for a given glyph, if it exists."""

        for base, alias in self.aliases:
            if name == base:
                return alias
        return None

    def _createAccentGlyphList(self, accentAnchorName, combAccentOnly):
        """Return a list of <name, x, y> tuples for glyphs containing an anchor
        with the given accent anchor name. If combAccentOnly is True, only
        combining glyphs are returned.
        """

        glyphList = []
        for glyph in self.font:
            if combAccentOnly and glyph.width != 0:
                continue
            for anchor in glyph.anchors:
                if accentAnchorName == anchor.name:
                    glyphList.append((glyph.name, anchor.x, anchor.y))
                    break
        return glyphList

    def _createBaseGlyphList(self, anchorName, isMkmk):
        """Return a list of <name, x, y> tuples for glyphs containing an anchor
        with the given anchor name. Mark glyphs are included iff this is a
        mark-to-mark rule.
        """

        glyphList = []
        for glyph in self.font:
            if isMkmk != (glyph.name in self.accentGlyphNames):
                continue
            for anchor in glyph.anchors:
                if anchorName == anchor.name:
                    glyphList.append((glyph.name, anchor.x, anchor.y))
                    break
        return glyphList

    def _createLigaGlyphList(self, anchorNames):
        """Return a list of (name, ((x, y), (x, y), ...)) tuples for glyphs
        containing anchors with given anchor names.
        """

        glyphList = []
        for glyph in self.font:
            points = []
            for anchorName in anchorNames:
                found = False
                for anchor in glyph.anchors:
                    if anchorName == anchor.name:
                        points.append((anchor.x, anchor.y))
                        found = True
                        break
                if not found:
                    break
            if points:
                glyphList.append((glyph.name, tuple(points)))
        return glyphList

    def _addClasses(self, lines, doMark, doMkmk):
        """Write class definitions for anchors used in mark and/or mkmk."""

        anchorList = []
        if doMark:
            anchorList.extend(self.anchorList)
            anchorList.extend(self.ligaAnchorList)
        if doMkmk:
            anchorList.extend(self.mkmkAnchorList)
        for anchorPair in sorted(set(anchorList)):
            self._addClass(lines, *anchorPair[1:])

    def _addClass(self, lines, accentAnchorName, combAccentOnly=False,
                  checkAliases=False):
        """Write class definition statements for one accent anchor. Remembers
        the accent glyph names, for use when generating base glyph lists.
        """

        accentGlyphs = self._createAccentGlyphList(
            accentAnchorName, combAccentOnly)
        className = self._generateClassName(accentAnchorName)

        for accentName, x, y in accentGlyphs:
            self.accentGlyphNames.add(accentName)
            lines.append(
                "markClass %s <anchor %d %d> %s;" %
                (accentName, x, y, className))
        lines.append("")

    def _addMarkLookup(self, lines, lookupName, isMkmk, anchorName, accentAnchorName,
                       combAccentOnly=False, checkAliases=False):
        """Add a mark lookup for one tuple in the writer's anchor list."""

        baseGlyphs = self._createBaseGlyphList(anchorName, isMkmk)
        if not baseGlyphs:
            return
        className = self._generateClassName(accentAnchorName)
        ruleType = "mark" if isMkmk else "base"

        lines.append("  lookup %s {" % lookupName)

        for baseName, x, y in baseGlyphs:
            lines.append(
                "    pos %s %s <anchor %d %d> mark %s;" %
                (ruleType, baseName, x, y, className))

            if checkAliases:
                alias = self._getAlias(baseName)
                if alias:
                    lines.append(
                        "    pos %s %s <anchor %d %d> mark %s;" %
                        (ruleType, alias, x, y, className))

        lines.append("  } %s;" % lookupName)

    def _addMarkToLigaLookup(self, lines, lookupName, anchorNames,
                             accentAnchorName):
        """Add a mark lookup containing mark-to-ligature position rules."""

        baseGlyphs = self._createLigaGlyphList(anchorNames)
        if not baseGlyphs:
            return
        className = self._generateClassName(accentAnchorName)

        lines.append("  lookup %s {" % lookupName)

        for baseName, points in baseGlyphs:
            lines.append("    pos ligature %s" % baseName)
            for x, y in points:
                lines.append("      <anchor %d %d> mark %s" % (x, y, className))
                lines.append("      ligComponent")
            # don't need last ligComponent statement
            lines.pop()
            lines.append("      ;")

        lines.append("  } %s;" % lookupName)

    def _addFeature(self, lines, isMkmk=False):
        """Write a single feature."""

        anchorList = self.mkmkAnchorList if isMkmk else self.anchorList
        if not anchorList and (isMkmk or not self.ligaAnchorList):
            # nothing to do, don't write empty feature
            return
        featureName = "mkmk" if isMkmk else "mark"

        lines.append("feature %s {" % featureName)

        for i, anchorPair in enumerate(anchorList):
            lookupName = "%s%d" % (featureName, i + 1)
            self._addMarkLookup(lines, lookupName, isMkmk, *anchorPair)

        if not isMkmk:
            for i, anchorPairs in enumerate(self.ligaAnchorList):
                lookupName = "mark2liga%d" % (i + 1)
                self._addMarkToLigaLookup(lines, lookupName, *anchorPairs)

        lines.append("} %s;\n" % featureName)

    def write(self, doMark=True, doMkmk=True):
        """Write mark and mkmk features, and mark class definitions."""

        if not (doMark or doMkmk):
            return ""

        lines = []
        accentGlyphs = self._addClasses(lines, doMark, doMkmk)
        if doMark:
            self._addFeature(lines, isMkmk=False)
        if doMkmk:
            self._addFeature(lines, isMkmk=True)
        return "\n".join(lines)
