from ufo2ft.constants import OPENTYPE_CATEGORIES_KEY
from ufo2ft.featureWriters import BaseFeatureWriter, ast


class GdefFeatureWriter(BaseFeatureWriter):
    """Generates a GDEF table based on OpenType Category and glyph anchors.

    There are a few use cases:
        1. There is no GDEF data in the UFO.
        2. There is some GDEF data in the UFO, in the UFO lib
           'public.openTypeCategories' or with ligature caret anchors
           'caret_<number>'.
        3. There is a GDEF in the features, and some GDEF data.

    This first generates a GDEF from the features, from the GDEF table
    definition if present or from the lookups.
    Then it updates the GDEF with the public.openTypeCategories and the
    ligature anchors for glyphs that are not already in GlyphClassDefs or
    do not have ligature carets.
    """

    tableTag = "GDEF"

    def setContext(self, font, feaFile, compiler=None):
        ctx = super().setContext(font, feaFile, compiler=compiler)
        ctx.orderedGlyphSet = self.getOrderedGlyphSet()
        ctx.skipExportGlyphs = set(font.lib.get("public.skipExportGlyphs", []))

        gdefFea = None
        for statement in feaFile.statements:
            if isinstance(statement, ast.TableBlock) and statement.name == "GDEF":
                gdefFea = statement
                break

        if gdefFea:
            ctx.gdefFea = gdefFea
            ctx.gdefTable = self.compileGDEF()
        else:
            ctx.gdefFea = ctx.gdefTable = None

        (
            ctx.bases,
            ctx.marks,
            ctx.ligatures,
            ctx.components,
        ) = self.getGDEFGlyphClasses(feaFile)

        ctx.ligatureCarets = self._getLigatureCarets()
        ctx.todo = [True]

        return ctx

    def getGDEFGlyphClasses(self, feaFile):
        """Return GDEF GlyphClassDef base/mark/ligature/component glyphs, or
        None if no GDEF table is defined in the feature file or generated from
        the lookups in the feature file.
        """
        font = self.context.font
        bases, ligatures, marks, components = set(), set(), set(), set()
        gdefTable = self.context.gdefTable
        if gdefTable:
            classDefs = gdefTable.table.GlyphClassDef.classDefs
        else:
            classDefs = {}
        openTypeCategories = font.lib.get(OPENTYPE_CATEGORIES_KEY, {})

        for glyphName in self.context.orderedGlyphSet.keys():
            category = openTypeCategories.get(glyphName)
            classDef = classDefs.get(glyphName)

            if classDef is None and category is None:
                continue
            elif classDef == 1 or (classDef is None and category == "base"):
                bases.add(glyphName)
            elif classDef == 2 or (classDef is None and category == "ligature"):
                ligatures.add(glyphName)
            elif classDef == 3 or (classDef is None and category == "mark"):
                marks.add(glyphName)
            elif classDef == 4 or (classDef is None and category == "component"):
                components.add(glyphName)

        return (
            frozenset(bases),
            frozenset(ligatures),
            frozenset(marks),
            frozenset(components),
        )

    def compileGDEF(self):
        """Compile a temporary GDEF table from the current feature file
        or from a given GDEF Table Block object."""
        from ufo2ft.util import compileGDEF

        compiler = self.context.compiler
        if compiler is not None:
            # The result is cached in the compiler instance, so if another
            # writer requests one it is not compiled again.
            if hasattr(compiler, "_gdef"):
                return compiler._gdef

            glyphOrder = compiler.ttFont.getGlyphOrder()
        else:
            glyphOrder = sorted(self.context.font.keys())

        if self.context.gdefFea:
            feaFile = ast.FeatureFile()
            feaFile.statements.append(self.context.gdefFea)
            gdef = compileGDEF(feaFile, glyphOrder)
        else:
            gdef = compileGDEF(self.context.feaFile, glyphOrder)

        if compiler:
            compiler._gdef = gdef
        return gdef

    def _getLigatureCarets(self):
        carets = dict()
        if self.context.gdefTable:
            ligCaretList = self.context.gdefTable.table.LigCaretList
            for i, glyphName in enumerate(ligCaretList.Coverage.glyphs):
                carets[glyphName] = [
                    cv.Coordinate for cv in ligCaretList.LigGlyph[i].CaretValue
                ]
        for glyphName, glyph in self.context.orderedGlyphSet.items():
            # skip glyphs that already have ligatureCarets defined inGDEF
            if glyphName in carets:
                continue

            glyphCarets = set()
            for anchor in glyph.anchors:
                if (
                    anchor.name
                    and anchor.name.startswith("caret_")
                    and anchor.x is not None
                ):
                    glyphCarets.add(round(anchor.x))
                if (
                    anchor.name
                    and anchor.name.startswith("vcaret_")
                    and anchor.y is not None
                ):
                    glyphCarets.add(round(anchor.y))

            if glyphCarets:
                carets[glyphName] = sorted(glyphCarets)

        if self.context.gdefTable:
            return {
                glyphName: carets[glyphName]
                for glyphName in self.context.orderedGlyphSet
                if glyphName in carets
            }
        else:
            return carets

    def _sortedGlyphClass(self, glyphNames):
        return sorted(n for n in self.context.orderedGlyphSet if n in glyphNames)

    def _makeGDEF(self):
        fea = ast.TableBlock("GDEF")

        bases, ligatures, marks, components = (
            self._sortedGlyphClass(self.context.bases),
            self._sortedGlyphClass(self.context.ligatures),
            self._sortedGlyphClass(self.context.marks),
            self._sortedGlyphClass(self.context.components),
        )
        if bases or ligatures or marks or components:
            glyphClassDefs = ast.GlyphClassDefStatement(
                ast.GlyphClass(bases),
                ast.GlyphClass(ligatures),
                ast.GlyphClass(marks),
                ast.GlyphClass(components),
            )
            fea.statements.append(glyphClassDefs)

        if self.context.ligatureCarets:
            ligatureCarets = [
                ast.LigatureCaretByPosStatement(ast.GlyphName(glyphName), carets)
                for glyphName, carets in self.context.ligatureCarets.items()
            ]
            fea.statements.extend(ligatureCarets)

        if fea.statements:
            return fea

    def _write(self):
        feaFile = self.context.feaFile
        newGdef = self._makeGDEF()
        if newGdef and self.context.gdefFea:
            index = feaFile.statements.index(self.context.gdefFea)
            del feaFile.statements[index]
            feaFile.statements.insert(index, newGdef)
            return True
        elif newGdef:
            feaFile.statements.append(newGdef)
            return True
