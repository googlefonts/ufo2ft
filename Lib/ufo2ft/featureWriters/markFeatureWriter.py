from __future__ import (
    print_function,
    division,
    absolute_import,
    unicode_literals,
)
import logging
from collections import OrderedDict

from fontTools.misc.py23 import round
from ufo2ft.featureWriters import BaseFeatureWriter, ast


logger = logging.getLogger(__name__)


class MarkFeatureWriter(BaseFeatureWriter):
    """Generates a mark or mkmk feature based on glyph anchors.

    setupAnchorPairs() produces lists of (anchorName, accentAnchorName) tuples
    for mark and mkmk features, and optionally a list of
    ((anchorName, ...), accentAnchorName) tuples for a liga2mark feature.
    """

    tableTag = "GPOS"
    features = frozenset(["mark", "mkmk"])
    _SUPPORTED_MODES = frozenset(["skip"])

    def setContext(self, font, feaFile, compiler=None):
        ctx = super(MarkFeatureWriter, self).setContext(
            font, feaFile, compiler=compiler
        )
        ctx.glyphSet = self._makeOrderedGlyphSet(font, compiler)
        ctx.accentGlyphNames = set()
        ctx.usedMarkClasses = set()

        self.setupAnchorPairs()

    @staticmethod
    def _makeOrderedGlyphSet(font, compiler=None):
        """ Return glyph set as an OrderedDict sorted by glyphOrder to write
        mark/mkmk classes and rules in a deterministic order.
        """
        if compiler is not None:
            glyphSet = compiler.glyphSet
            glyphOrder = compiler.ttFont.getGlyphOrder()
        else:
            from ufo2ft.util import makeOfficialGlyphOrder

            glyphSet = font
            glyphOrder = makeOfficialGlyphOrder(font)
        return OrderedDict((gn, glyphSet[gn]) for gn in glyphOrder)

    @staticmethod
    def _generateClassName(accentAnchorName):
        """ Generate a mark class name used by mark class definitions and
        positioning statements.
        """
        return "MC%s" % accentAnchorName

    def _makeMarkClassDefinitions(self, markClasses):
        """ Return list of MarkClassDefinition statements for all the anchors
        used in mark and/or mkmk.
        """
        anchorList = []
        if "mark" in self.context.todo:
            anchorList.extend(self.context.anchorList)
            anchorList.extend(self.context.ligaAnchorList)
        if "mkmk" in self.context.todo:
            anchorList.extend(self.context.mkmkAnchorList)

        mcdefs = []
        for accentAnchorName in sorted(set(n for _, n in anchorList)):
            mcdefs.extend(self._makeMarkClasses(markClasses, accentAnchorName))
        return mcdefs

    def _makeMarkClasses(self, markClasses, accentAnchorName):
        """ Create MarkClassDefinition statements for one accent anchor, and
        return an iterator.
        Remembers the accent glyph names, for use when generating base glyph
        lists.
        """
        accentGlyphs = self._createAccentGlyphList(accentAnchorName)
        className = self._generateClassName(accentAnchorName)

        accentGlyphNames = self.context.accentGlyphNames
        for accentName, x, y in sorted(accentGlyphs):
            accentGlyphNames.add(accentName)
            mc = self._makeMarkClass(markClasses, accentName, x, y, className)
            if mc is not None:
                yield mc

    @classmethod
    def _makeMarkClass(cls, markClasses, accentName, x, y, className):
        """ Make a MarkClassDefinition statement given the accent name,
        position, class name, and pre-existing mark classes.
        Return None if a mark class with the same name and anchor already
        exists. Or create new mark class with unique name when different.
        """
        glyphs = ast.GlyphName(accentName)
        anchor = cls._makeAnchorFormatA(x, y)
        className = ast.makeFeaClassName(className)
        markClass = markClasses.get(className)
        if markClass is None:
            markClass = ast.MarkClass(className)
            markClasses[className] = markClass
        else:
            if accentName in markClass.glyphs:
                mcdef = markClass.glyphs[accentName]
                if cls._anchorsAreEqual(anchor, mcdef.anchor):
                    logger.debug(
                        "Glyph %s already defined in markClass @%s",
                        accentName,
                        className,
                    )
                    return None
                else:
                    # same accent glyph defined with different anchors for the
                    # same markClass; make a new unique markClass definition
                    newClassName = ast.makeFeaClassName(className, markClasses)
                    markClass = ast.MarkClass(newClassName)
                    markClasses[newClassName] = markClass
        mcdef = ast.MarkClassDefinition(markClass, anchor, glyphs)
        markClass.addDefinition(mcdef)
        return mcdef

    @staticmethod
    def _anchorsAreEqual(a1, a2):
        # TODO add __eq__ to feaLib AST objects
        for attr in ("x", "y", "contourpoint", "xDeviceTable", "yDeviceTable"):
            if getattr(a1, attr) != getattr(a2, attr):
                return False
        return True

    @staticmethod
    def _makeAnchorFormatA(x, y):
        return ast.Anchor(x=round(x), y=round(y))

    def _createAccentGlyphList(self, accentAnchorName):
        """ Return a list of <name, x, y> tuples for glyphs containing an anchor
        with the given accent anchor name.
        """
        glyphList = []
        for glyphName, glyph in self.context.glyphSet.items():
            for anchor in glyph.anchors:
                if accentAnchorName == anchor.name:
                    glyphList.append((glyphName, anchor.x, anchor.y))
                    break
        return glyphList

    def _createBaseGlyphList(self, anchorName, isMkmk):
        """ Return a list of <name, x, y> tuples for glyphs containing an anchor
        with the given anchor name. Mark glyphs are included iff this is a
        mark-to-mark rule.
        """
        glyphList = []
        accentGlyphNames = self.context.accentGlyphNames
        for glyphName, glyph in self.context.glyphSet.items():
            if isMkmk ^ (glyphName in accentGlyphNames):
                continue
            for anchor in glyph.anchors:
                if anchorName == anchor.name:
                    glyphList.append((glyphName, anchor.x, anchor.y))
                    break
        return glyphList

    def _createLigaGlyphList(self, anchorNames):
        """Return a list of (name, ((x, y), (x, y), ...)) tuples for glyphs
        containing anchors with given anchor names.
        """
        glyphList = []
        for glyphName, glyph in self.context.glyphSet.items():
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
                glyphList.append((glyphName, tuple(points)))
        return glyphList

    def _makeMarkFeature(self, markClasses, isMkmk=False):
        """ Return a mark or mkmk FeatureBlock statement, or None if there is
        nothing to generate.
        """
        anchorList = (
            self.context.mkmkAnchorList if isMkmk else self.context.anchorList
        )
        if not anchorList and (isMkmk or not self.context.ligaAnchorList):
            # nothing to do, don't write empty feature
            return

        featureName = "mkmk" if isMkmk else "mark"
        lookups = []

        used = self.context.usedMarkClasses
        for i, (anchorName, accentAnchorName) in enumerate(anchorList, 1):
            className = self._generateClassName(accentAnchorName)
            markClass = markClasses[className]
            lookup = self._makeMarkLookup(
                "%s%d" % (featureName, i),
                isMkmk,
                anchorName,
                accentAnchorName,
                markClass,
            )
            if lookup:
                lookups.append(lookup)
                used.add(className)

        if not isMkmk:
            ligaAnchors = self.context.ligaAnchorList
            for i, (anchorName, accentAnchorName) in enumerate(ligaAnchors, 1):
                className = self._generateClassName(accentAnchorName)
                markClass = markClasses[className]
                lookup = self._makeMarkToLigaLookup(
                    "mark2liga%d" % i, anchorName, accentAnchorName, markClass
                )
                if lookup:
                    lookups.append(lookup)
                    used.add(className)

        if lookups:
            feature = ast.FeatureBlock(featureName)
            feature.statements.extend(lookups)
            return feature

    def _makeMarkLookup(
        self, lookupName, isMkmk, anchorName, accentAnchorName, markClass
    ):
        """ Create a mark (or mkmk) lookup for one anchor pair in the writer's
        anchor list, or None if there are no glyphs with given anchor.
        """
        baseGlyphs = self._createBaseGlyphList(anchorName, isMkmk)
        if not baseGlyphs:
            return

        ruleType = "mark" if isMkmk else "base"

        statements = []
        if isMkmk:
            mkAttachMembers = list(markClass.glyphs)
            mkAttachMembers.extend(
                g[0] for g in baseGlyphs if g[0] not in mkAttachMembers
            )
            mkAttachCls = ast.makeGlyphClassDefinition(
                lookupName + "MkAttach", mkAttachMembers
            )
            statements.append(mkAttachCls)
            statements.append(ast.makeLookupFlag(markFilteringSet=mkAttachCls))

        for baseName, x, y in baseGlyphs:
            statements.append(
                self._makeMarkPosRule(ruleType, baseName, x, y, markClass)
            )

        if statements:
            lookup = ast.LookupBlock(lookupName)
            lookup.statements.extend(statements)
            return lookup

    @classmethod
    def _makeMarkPosRule(cls, ruleType, baseName, x, y, markClass):
        """ Return a MarkBasePosStatement for given rule type (either "base" or
        "mark"), glyph name, anchor and markClass name.
        """
        base = ast.GlyphName(baseName)
        anchor = cls._makeAnchorFormatA(x, y)
        marks = [(anchor, markClass)]
        if ruleType == "base":
            return ast.MarkBasePosStatement(base, marks)
        elif ruleType == "mark":
            return ast.MarkMarkPosStatement(base, marks)
        else:
            raise AssertionError(ruleType)

    def _makeMarkToLigaLookup(
        self, lookupName, anchorNames, accentAnchorName, markClass
    ):
        """ Return a mark lookup containing mark-to-ligature position rules
        for the given anchor pairs, or None if there are no glyphs with
        those anchors.
        """
        baseGlyphs = self._createLigaGlyphList(anchorNames)
        if not baseGlyphs:
            return

        statements = []
        for baseName, points in baseGlyphs:
            statements.append(
                self._makeMarkLigPosRule(baseName, points, markClass)
            )

        if statements:
            lookup = ast.LookupBlock(lookupName)
            lookup.statements.extend(statements)
            return lookup

    @classmethod
    def _makeMarkLigPosRule(cls, baseName, points, markClass):
        """ Return a MarkLigPosStatement for given ligature glyph, list of
        anchor points, and a markClass.
        """
        ligature = ast.GlyphName(baseName)
        marks = []
        for x, y in points:
            anchor = cls._makeAnchorFormatA(x, y)
            marks.append([(anchor, markClass)])
        return ast.MarkLigPosStatement(ligature, marks)

    def setupAnchorPairs(self):
        """ Try to determine the base-accent anchor pairs to use in building
        the mark and mkmk features.

        **This should not be called externally.** Subclasses
        may override this method to set up the anchor pairs
        in a different way if desired.
        """
        self.context.anchorList = anchorList = []
        self.context.ligaAnchorList = ligaAnchorList = []

        anchorNames = set()
        for glyphName, glyph in self.context.glyphSet.items():
            for anchor in glyph.anchors:
                if anchor.name is None:
                    logger.warning(
                        "Unnamed anchor discarded in %s", glyph.name
                    )
                    continue
                anchorNames.add(anchor.name)

        for baseName in sorted(anchorNames):
            accentName = "_" + baseName
            if accentName in anchorNames:
                anchorList.append((baseName, accentName))

                ligaNames = []
                i = 1
                while True:
                    ligaName = "%s_%d" % (baseName, i)
                    if ligaName not in anchorNames:
                        break
                    ligaNames.append(ligaName)
                    i += 1
                if ligaNames:
                    ligaAnchorList.append((tuple(ligaNames), accentName))

        self.context.mkmkAnchorList = anchorList

    def _write(self):
        """Write mark and mkmk features, and mark class definitions.
        """
        feaFile = self.context.feaFile
        # dict of mark classes defined in the feature file keyed by name
        markClasses = feaFile.markClasses
        markClassDefs = self._makeMarkClassDefinitions(markClasses)

        features = {}
        for tag in ("mark", "mkmk"):
            if tag in self.context.todo:
                f = self._makeMarkFeature(markClasses, isMkmk=(tag == "mkmk"))
                if f is not None:
                    features[tag] = f
        if not features:
            return False

        # only write new definitions for the classes that were actually used
        feaFile.statements.extend(
            [
                definition
                for definition in markClassDefs
                if definition.markClass.name in self.context.usedMarkClasses
            ]
        )
        for _, feature in sorted(features.items()):
            feaFile.statements.append(feature)
        return True
