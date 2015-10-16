class MarkFeatureWriter:
    """Generates a mark or mkmk feature based on glyph anchors.

    Takes in a list of <anchorName, accentAnchorName> tuples, which may
    additionally include boolean parameters indicating whether to only include
    combining accents and whether to expand the rule to aliased glyphs.

    Takes in a list of aliases as tuples, each typically a base glyph and a
    composite including the base glyph.
    """

    def __init__(self, font, anchorList, aliases=(), mkmk=False):
        self.font = font
        self.anchorList = anchorList
        self.aliases = aliases
        self.mkmk = mkmk

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

    def _createBaseGlyphList(self, anchorName, accentGlyphs):
        """Return a list of <name, x, y> tuples for glyphs containing an anchor
        with the given anchor name. Glyphs included in accentGlyphs (a similar
        list of tuples) are excluded if this is a mark-to-base rule.
        """

        accentGlyphNames = set(glyphName for glyphName, _, _ in accentGlyphs)
        glyphList = []
        for glyph in self.font:
            if (not self.mkmk) and glyph.name in accentGlyphNames:
                continue
            for anchor in glyph.anchors:
                if anchorName == anchor.name:
                    glyphList.append((glyph.name, anchor.x, anchor.y))
                    break
        return glyphList

    def _addMarkLookup(self, lines, lookupName, anchorName, accentAnchorName,
                       combAccentOnly=False, checkAliases=False):
        """Add a mark lookup for one tuple in the writer's anchor list."""

        lines.append("  lookup %s {" % lookupName)

        className = "@MC_%s_%s" % ("mkmk" if self.mkmk else "mark", anchorName)
        ruleType = "mark" if self.mkmk else "base"
        accentGlyphs = self._createAccentGlyphList(
            accentAnchorName, combAccentOnly)
        baseGlyphs = self._createBaseGlyphList(anchorName, accentGlyphs)

        for accentName, x, y in accentGlyphs:
            lines.append(
                "    markClass %s <anchor %d %d> %s;" %
                (accentName, x, y, className))

        for accentName, x, y in baseGlyphs:
            lines.append(
                "    pos %s %s <anchor %d %d> mark %s;" %
                (ruleType, accentName, x, y, className))

            if checkAliases:
                alias = self._getAlias(accentName)
                if alias:
                    lines.append(
                        "    pos %s %s <anchor %d %d> mark %s;" %
                        (ruleType, alias, x, y, className))

        lines.append("  } %s;" % lookupName)

    def write(self):
        """Write the feature."""

        featureName = "mkmk" if self.mkmk else "mark"
        lines = ["feature %s {" % featureName]

        for i, anchorPair in enumerate(self.anchorList):
            lookupName = "%s%d" % (featureName, i + 1)
            self._addMarkLookup(lines, lookupName, *anchorPair)

        lines.append("} %s;" % featureName)
        return "\n".join(lines)
