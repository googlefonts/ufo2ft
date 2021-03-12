from ufo2ft.constants import OPENTYPE_CATEGORIES_KEY
from ufo2ft.featureWriters import BaseFeatureWriter, ast


class GdefFeatureWriter(BaseFeatureWriter):
    """Generates a GDEF table based on OpenType Category and glyph anchors.

    It skips generating the GDEF if a GDEF is defined in the features.

    It uses the 'public.openTypeCategories' values to create the GDEF ClassDefs
    and the ligature caret anchors to create the GDEF ligature carets.

    """

    tableTag = "GDEF"

    def setContext(self, font, feaFile, compiler=None):
        ctx = super().setContext(font, feaFile, compiler=compiler)
        ctx.orderedGlyphSet = self.getOrderedGlyphSet()
        ctx.ligatureCarets = self._getLigatureCarets()
        (
            ctx.bases,
            ctx.ligatures,
            ctx.marks,
            ctx.components,
        ) = self._getOpenTypeCategories()
        ctx.todo = {"GlyphClassDefs", "LigatureCarets"}

        return ctx

    def shouldContinue(self):
        # skip if a GDEF is in the features
        for statement in self.context.feaFile.statements:
            if isinstance(statement, ast.TableBlock) and statement.name == "GDEF":
                self.context.todo.clear()
                return super().shouldContinue()

        if not self.context.ligatureCarets:
            self.context.todo.remove("LigatureCarets")

        if not self.context.font.lib.get(OPENTYPE_CATEGORIES_KEY):
            self.context.todo.remove("GlyphClassDefs")

        return super().shouldContinue()

    def _getOpenTypeCategories(self):
        """Return GDEF GlyphClassDef base/ligature/mark/component glyphs based
        on 'public.openTypeCategories' values.
        """
        font = self.context.font
        bases, ligatures, marks, components = list(), list(), list(), list()
        openTypeCategories = font.lib.get(OPENTYPE_CATEGORIES_KEY, {})

        for glyphName in self.context.orderedGlyphSet.keys():
            category = openTypeCategories.get(glyphName)

            if category is None or category == "unassigned":
                continue
            elif category == "base":
                bases.append(glyphName)
            elif category == "ligature":
                ligatures.append(glyphName)
            elif category == "mark":
                marks.append(glyphName)
            elif category == "component":
                components.append(glyphName)

        return (bases, ligatures, marks, components)

    def _getLigatureCarets(self):
        carets = dict()

        for glyphName, glyph in self.context.orderedGlyphSet.items():
            glyphCarets = set()
            for anchor in glyph.anchors:
                if (
                    anchor.name
                    and anchor.name.startswith("caret_")
                    and anchor.x is not None
                ):
                    glyphCarets.add(round(anchor.x))
                elif (
                    anchor.name
                    and anchor.name.startswith("vcaret_")
                    and anchor.y is not None
                ):
                    glyphCarets.add(round(anchor.y))

            if glyphCarets:
                carets[glyphName] = sorted(glyphCarets)

        return carets

    def _makeGDEF(self):
        fea = ast.TableBlock("GDEF")

        if "GlyphClassDefs" in self.context.todo:
            glyphClassDefs = ast.GlyphClassDefStatement(
                ast.GlyphClass(self.context.bases),
                ast.GlyphClass(self.context.marks),
                ast.GlyphClass(self.context.ligatures),
                ast.GlyphClass(self.context.components),
            )
            fea.statements.append(glyphClassDefs)

        if "LigatureCarets" in self.context.todo:
            ligatureCarets = [
                ast.LigatureCaretByPosStatement(ast.GlyphName(glyphName), carets)
                for glyphName, carets in self.context.ligatureCarets.items()
            ]
            fea.statements.extend(ligatureCarets)

        return fea

    def _write(self):
        feaFile = self.context.feaFile
        feaFile.statements.append(self._makeGDEF())

        return True
