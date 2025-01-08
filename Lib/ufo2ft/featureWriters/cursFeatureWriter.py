from ufo2ft.featureWriters import BaseFeatureWriter, ast
from ufo2ft.util import classifyGlyphs, otRoundIgnoringVariable, unicodeScriptDirection


class CursFeatureWriter(BaseFeatureWriter):
    """Generate a curs feature base on glyph anchors.

    The default mode is 'skip': i.e. if the 'curs' feature is already present in
    the feature file, it is not generated again.

    The optional 'append' mode will add extra lookups to an already existing
    features, if any.

    By default, anchors names 'entry' and 'exit' will be used to connect the
    'entry' anchor of a glyph with the 'exit' anchor of the preceding glyph.
    """

    tableTag = "GPOS"
    features = frozenset(["curs"])

    @staticmethod
    def _getCursiveAnchorPairs(glyphs):
        anchors = set()
        for _, glyph in glyphs:
            anchors.update(a.name for a in glyph.anchors)

        anchorPairs = []
        if "entry" in anchors and "exit" in anchors:
            anchorPairs.append(("entry", "exit"))
        for anchor in anchors:
            if anchor.startswith("entry.") and f"exit.{anchor[6:]}" in anchors:
                anchorPairs.append((anchor, f"exit.{anchor[6:]}"))

        return sorted(anchorPairs)

    @staticmethod
    def _hasAnchor(glyph, anchorName):
        return any(a.name == anchorName for a in glyph.anchors)

    def _makeCursiveFeature(self):
        cmap = self.makeUnicodeToGlyphNameMapping()
        if any(unicodeScriptDirection(uv) == "LTR" for uv in cmap):
            gsub = self.compileGSUB()
            extras = self.extraSubstitutions()
            dirGlyphs = classifyGlyphs(unicodeScriptDirection, cmap, gsub, extras)
            shouldSplit = "LTR" in dirGlyphs
        else:
            shouldSplit = False

        lookups = []
        orderedGlyphSet = self.getOrderedGlyphSet().items()
        cursiveAnchorsPairs = self._getCursiveAnchorPairs(orderedGlyphSet)
        for entryName, exitName in cursiveAnchorsPairs:
            # If the anchors have an explicit direction suffix, don’t set
            # direction based on the script of the glyphs.
            if not entryName.endswith((".LTR", ".RTL")) and shouldSplit:
                # Make LTR lookup
                LTRlookup = self._makeCursiveLookup(
                    (
                        glyph
                        for (glyphName, glyph) in orderedGlyphSet
                        if glyphName in dirGlyphs["LTR"]
                    ),
                    entryName,
                    exitName,
                    direction="LTR",
                )
                if LTRlookup:
                    lookups.append(LTRlookup)

                # Make RTL lookup with other glyphs
                RTLlookup = self._makeCursiveLookup(
                    (
                        glyph
                        for (glyphName, glyph) in orderedGlyphSet
                        if glyphName not in dirGlyphs["LTR"]
                    ),
                    entryName,
                    exitName,
                    direction="RTL",
                )
                if RTLlookup:
                    lookups.append(RTLlookup)
            else:
                lookup = self._makeCursiveLookup(
                    (glyph for (glyphName, glyph) in orderedGlyphSet),
                    entryName,
                    exitName,
                )
                if lookup:
                    lookups.append(lookup)

        if lookups:
            feature = ast.FeatureBlock("curs")
            feature.statements.extend(lookups)
            return feature

    def _makeCursiveLookup(self, glyphs, entryName, exitName, direction=None):
        statements = self._makeCursiveStatements(glyphs, entryName, exitName)

        if not statements:
            return

        suffix = ""
        if entryName != "entry":
            suffix = f"_{entryName[6:]}"
        if direction == "LTR":
            suffix += "_ltr"
        elif direction == "RTL":
            suffix += "_rtl"
        lookup = ast.LookupBlock(name=f"curs{suffix}")

        if entryName.endswith(".RTL"):
            direction = "RTL"
        elif entryName.endswith(".LTR"):
            direction = "LTR"

        if direction != "LTR":
            lookup.statements.append(ast.makeLookupFlag(("IgnoreMarks", "RightToLeft")))
        else:
            lookup.statements.append(ast.makeLookupFlag("IgnoreMarks"))

        lookup.statements.extend(statements)

        return lookup

    def _getAnchors(self, glyphName, entryName, exitName):
        entryAnchor = None
        exitAnchor = None
        entryAnchorXY = self._getAnchor(glyphName, entryName)
        exitAnchorXY = self._getAnchor(glyphName, exitName)
        if entryAnchorXY:
            entryAnchor = ast.Anchor(
                x=otRoundIgnoringVariable(entryAnchorXY[0]),
                y=otRoundIgnoringVariable(entryAnchorXY[1]),
            )
        if exitAnchorXY:
            exitAnchor = ast.Anchor(
                x=otRoundIgnoringVariable(exitAnchorXY[0]),
                y=otRoundIgnoringVariable(exitAnchorXY[1]),
            )
        return entryAnchor, exitAnchor

    def _makeCursiveStatements(self, glyphs, entryName, exitName):
        cursiveAnchors = dict()
        statements = []
        for glyph in glyphs:
            entryAnchor, exitAnchor = self._getAnchors(glyph.name, entryName, exitName)
            # A glyph can have only one of the cursive anchors (e.g. if it
            # attaches on one side only)
            if entryAnchor or exitAnchor:
                cursiveAnchors[ast.GlyphName(glyph.name)] = (entryAnchor, exitAnchor)

        if cursiveAnchors:
            for glyphName, anchors in cursiveAnchors.items():
                statement = ast.CursivePosStatement(glyphName, *anchors)
                statements.append(statement)

        return statements

    def _write(self):
        feaFile = self.context.feaFile
        feature = self._makeCursiveFeature()

        if not feature:
            return False

        self._insert(feaFile=feaFile, features=[feature])
        return True
