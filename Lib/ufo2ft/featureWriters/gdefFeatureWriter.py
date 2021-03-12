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
        ctx.openTypeCategories = self.getOpenTypeCategories()
        ctx.todo = {"GlyphClassDefs", "LigatureCarets"}

        return ctx

    def shouldContinue(self):
        # skip if a GDEF is in the features
        if ast.findTable(self.context.feaFile, "GDEF") is not None:
            self.context.todo.clear()
            return super().shouldContinue()

        if not self.context.ligatureCarets:
            self.context.todo.remove("LigatureCarets")

        if not any(self.context.openTypeCategories):
            self.context.todo.remove("GlyphClassDefs")

        return super().shouldContinue()

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

    def _sortedGlyphClass(self, glyphNames):
        return sorted(n for n in self.context.orderedGlyphSet if n in glyphNames)

    def _makeGDEF(self):
        fea = ast.TableBlock("GDEF")
        categories = self.context.openTypeCategories

        if "GlyphClassDefs" in self.context.todo:
            glyphClassDefs = ast.GlyphClassDefStatement(
                ast.GlyphClass(self._sortedGlyphClass(categories.base)),
                ast.GlyphClass(self._sortedGlyphClass(categories.mark)),
                ast.GlyphClass(self._sortedGlyphClass(categories.ligature)),
                ast.GlyphClass(self._sortedGlyphClass(categories.component)),
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
