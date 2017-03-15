from __future__ import print_function, division, absolute_import, unicode_literals
import logging

from ufo2ft.kernFeatureWriter import liststr

logger = logging.getLogger(__name__)


class MarkFeatureWriter(object):
    """Generates a mark or mkmk feature based on glyph anchors.

    setupAnchorPairs() produces lists of (anchorName, accentAnchorName) tuples
    for mark and mkmk features, and optionally a list of ((anchorName, ...), accentAnchorName)
    tuples for a liga2mark feature.
    """

    def __init__(self, font):
        self.font = font
        self.accentGlyphNames = set()
        self.setupAnchorPairs()

    def _generateClassName(self, accentAnchorName):
        """Generate a mark class name shared by class definition and positioning
        statements.
        """

        return "@MC%s" % accentAnchorName

    def _createAccentGlyphList(self, accentAnchorName):
        """Return a list of <name, x, y> tuples for glyphs containing an anchor
        with the given accent anchor name.
        """

        glyphList = []
        for glyph in self.font:
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

        added = set()
        for accentAnchorName in sorted(set(n for _, n in anchorList)):
            added.add(accentAnchorName)
            self._addClass(lines, accentAnchorName)

    def _addClass(self, lines, accentAnchorName):
        """Write class definition statements for one accent anchor. Remembers
        the accent glyph names, for use when generating base glyph lists.
        """

        accentGlyphs = self._createAccentGlyphList(accentAnchorName)
        className = self._generateClassName(accentAnchorName)

        for accentName, x, y in accentGlyphs:
            self.accentGlyphNames.add(accentName)
            lines.append(
                "markClass %s <anchor %d %d> %s;" %
                (accentName, x, y, className))
        lines.append("")

    def _addMarkLookup(self, lines, lookupName, isMkmk, anchorPair):
        """Add a mark lookup for one tuple in the writer's anchor list."""

        anchorName, accentAnchorName = anchorPair
        baseGlyphs = self._createBaseGlyphList(anchorName, isMkmk)
        if not baseGlyphs:
            return
        className = self._generateClassName(accentAnchorName)
        ruleType = "mark" if isMkmk else "base"

        lines.append("  lookup %s {" % lookupName)
        if isMkmk:
            mkAttachCls = "@%sMkAttach" % lookupName
            lines.append("    %s = %s;" % (
                mkAttachCls, liststr([className] + [g[0] for g in baseGlyphs])))
            lines.append("    lookupflag UseMarkFilteringSet %s;" % mkAttachCls)

        for baseName, x, y in baseGlyphs:
            lines.append(
                "    pos %s %s <anchor %d %d> mark %s;" %
                (ruleType, baseName, x, y, className))

        lines.append("  } %s;" % lookupName)

    def _addMarkToLigaLookup(self, lines, lookupName, anchorPairs):
        """Add a mark lookup containing mark-to-ligature position rules."""

        anchorNames, accentAnchorName = anchorPairs
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
            self._addMarkLookup(lines, lookupName, isMkmk, anchorPair)

        if not isMkmk:
            for i, anchorPairs in enumerate(self.ligaAnchorList):
                lookupName = "mark2liga%d" % (i + 1)
                self._addMarkToLigaLookup(lines, lookupName, anchorPairs)

        lines.append("} %s;\n" % featureName)

    def setupAnchorPairs(self):
        """
        Try to determine the base-accent anchor pairs to use in building the
        mark and mkmk features.

        **This should not be called externally.** Subclasses
        may override this method to set up the anchor pairs
        in a different way if desired.
        """

        self.anchorList = []
        self.ligaAnchorList = []

        anchorNames = set()
        for glyph in self.font:
            for anchor in glyph.anchors:
                if anchor.name is None:
                    logger.warning("Unnamed anchor discarded in %s", glyph.name)
                    continue
                anchorNames.add(anchor.name)

        for baseName in sorted(anchorNames):
            accentName = "_" + baseName
            if accentName in anchorNames:
                self.anchorList.append((baseName, accentName))

                ligaNames = []
                i = 1
                while True:
                    ligaName = "%s_%d" % (baseName, i)
                    if ligaName not in anchorNames:
                        break
                    ligaNames.append(ligaName)
                    i += 1
                if ligaNames:
                    self.ligaAnchorList.append((tuple(ligaNames), accentName))

        self.mkmkAnchorList = self.anchorList

    def write(self, doMark=True, doMkmk=True):
        """Write mark and mkmk features, and mark class definitions."""

        if not (doMark or doMkmk):
            return ""

        lines = []
        self._addClasses(lines, doMark, doMkmk)
        if doMark:
            self._addFeature(lines, isMkmk=False)
        if doMkmk:
            self._addFeature(lines, isMkmk=True)
        return "\n".join(lines)
