from ufo2ft.filters.decomposeTransformedComponents import (
    DecomposeTransformedComponentsFilter,
)
from ufo2ft.preProcessor import TTFInterpolatablePreProcessor


class DecomposeTransformedComponentsFilterTest:
    def test_transformed_components(self, FontClass):
        ufo = FontClass()
        a = ufo.newGlyph("six.lf")
        a.width = 300
        pen = a.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((300, 0))
        pen.lineTo((150, 300))
        pen.closePath()

        # six has one component
        c = ufo.newGlyph("six")
        c.width = 300
        pen = c.getPen()
        pen.addComponent("six.lf", (1, 0, 0, 1, 0, 0))

        # nine.lf has one transformed component of a component
        b = ufo.newGlyph("nine.lf")
        b.width = 300
        pen = b.getPen()
        pen.addComponent("six.lf", (-1, 0, 0, -1, 0, 0))

        # nine has one transformed component
        c = ufo.newGlyph("nine")
        c.width = 300
        pen = c.getPen()
        pen.addComponent("six", (-1, 0, 0, -1, 0, 0))

        # nine.of has one component of a transformed component
        d = ufo.newGlyph("nine.of")
        d.width = 300
        pen = d.getPen()
        pen.addComponent("nine", (1, 0, 0, 1, 0, -80))

        filter_ = DecomposeTransformedComponentsFilter()

        assert filter_(ufo)
        # six.lf has one outline and no component
        assert len(ufo["six.lf"]) == 1
        assert not ufo["six.lf"].components
        # six has no outline and one component
        assert len(ufo["six"]) == 0
        assert len(ufo["six"].components) == 1
        # nine.lf has one outline and no component, it was decomposed
        assert len(ufo["nine.lf"]) == 1
        assert not ufo["nine.lf"].components
        # nine has one outline and no component, it was decomposed
        assert len(ufo["nine"]) == 1
        assert not ufo["nine"].components
        # nine.of has no outline and one component, it was not decomposed
        assert len(ufo["nine.of"]) == 0
        assert len(ufo["nine.of"].components) == 1

    def test_decompose_compatibly(self, FontClass):
        ufo1 = FontClass()
        c = ufo1.newGlyph("comp")
        c.width = 300
        pen = c.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((300, 0))
        pen.lineTo((150, 300))
        pen.closePath()

        b = ufo1.newGlyph("base")
        b.width = 300
        pen = b.getPen()
        pen.addComponent("comp", (0.5, 0, 0, 0.5, 0, 0))

        ufo2 = FontClass()
        c = ufo2.newGlyph("comp")
        c.width = 600
        pen = c.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((600, 0))
        pen.lineTo((300, 600))
        pen.closePath()

        b = ufo2.newGlyph("base")
        b.width = 600
        pen = b.getPen()
        pen.addComponent("comp", (1, 0, 0, 1, 0, 0))

        # Because ufo1.base needs decomposing, so should ufo2.base
        glyphsets = TTFInterpolatablePreProcessor(
            [ufo1, ufo2], filters=[DecomposeTransformedComponentsFilter(pre=True)]
        ).process()
        assert len(glyphsets[0]["base"]) == 1
        assert len(glyphsets[1]["base"]) == 1

    def test_decompose_compatibly_nested_transformed_components(self, FontClass):
        # This replicates three glyphs from the 'changa.zip' test fonts at
        # https://github.com/googlefonts/ufo2ft/issues/621
        # In both fonts, the "exclam" glyph is made of one simple contour and one
        # component ("period"); "exclamdown" in turn is made of one "exclam" component
        # that is flipped vertically and horizontally; "period" is a single contour.
        # But only in the Bold.ufo, the "exclam" contains a scaled down "period"; in
        # the Regular.ufo, the "period" component only has an offset.
        # This would previously trigger a situation whereby after "exclamdown" was
        # decomposed, its points were no longer interpolation compatible across masters
        # because the order in which the contours were decomposed was different.
        # This is because filters used to modify glyphs in-place in alphabetical order,
        # so 'exclam' comes before 'exclamdown', and in the Bold.ufo, 'exclam' has
        # a 2x3 transform so is decomposed (with the period appended at the end), but
        # then 'exclamdown' needs decomposing as well (for it's flipped) and the
        # already decomposed 'exclam' contours are drawn onto it in the same order;
        # whereas in Regular.ufo, the 'exclam' does not contain transformed components
        # so it's kept as composite (for the time being, it will be decomposed later on
        # because it's mixed), but when it's the turn of 'exclamdown', the period's
        # contour gets appended to it before the rest of the rest of the 'exclam'
        # (deepCopyContours follows a post-order depth-first traversal so the children
        # get decomposed before the parent) -- leading to cu2qu crashing... Pfew!
        regular_ufo = FontClass()
        period = regular_ufo.newGlyph("period")
        period.width = 230
        pen = period.getPen()
        pen.moveTo((50, 62))
        pen.curveTo((50, 13), (61, -6), (115, -6))
        pen.curveTo((168, -6), (180, 13), (180, 62))
        pen.curveTo((180, 110), (168, 131), (115, 131))
        pen.curveTo((61, 131), (50, 110), (50, 62))
        pen.closePath()

        exclam = regular_ufo.newGlyph("exclam")
        exclam.width = 250
        pen = exclam.getPen()
        pen.moveTo((93, 196))
        pen.lineTo((156, 196))
        pen.lineTo((186, 627))
        pen.curveTo((186, 637), (181, 645), (161, 645))
        pen.lineTo((87, 645))
        pen.curveTo((67, 645), (63, 637), (63, 627))
        pen.closePath()
        pen.addComponent("period", (1, 0, 0, 1, 10, 0))

        exclamdown = regular_ufo.newGlyph("exclamdown")
        exclamdown.width = 250
        pen = exclamdown.getPen()
        pen.addComponent("exclam", (-1, 0, 0, -1, 250, 509))

        bold_ufo = FontClass()
        period = bold_ufo.newGlyph("period")
        period.width = 277
        pen = period.getPen()
        pen.moveTo((30, 99))
        pen.curveTo((30, 23), (50, -6), (139, -6))
        pen.curveTo((227, -6), (247, 23), (247, 99))
        pen.curveTo((247, 175), (227, 206), (139, 206))
        pen.curveTo((50, 206), (30, 175), (30, 99))
        pen.closePath()

        exclam = bold_ufo.newGlyph("exclam")
        exclam.width = 297
        pen = exclam.getPen()
        pen.moveTo((84, 230))
        pen.lineTo((214, 230))
        pen.lineTo((254, 618))
        pen.curveTo((254, 633), (247, 645), (217, 645))
        pen.lineTo((81, 645))
        pen.curveTo((51, 645), (44, 633), (44, 618))
        pen.closePath()
        pen.addComponent("period", (0.87, 0, 0, 0.87, 28, -1))

        exclamdown = bold_ufo.newGlyph("exclamdown")
        exclamdown.width = 297
        pen = exclamdown.getPen()
        pen.addComponent("exclam", (-1, 0, 0, -1, 298, 509))

        # We test that, even with DecomposeTransformedComponentsFilter(pre=True) and
        # the above nested/transformed/mixed component setup, we don't crash cu2qu
        # with errors about masters with inconsistent contour order after decomposition
        # of "exclamdown".
        glyphsets = TTFInterpolatablePreProcessor(
            [regular_ufo, bold_ufo],
            filters=[DecomposeTransformedComponentsFilter(pre=True)],
        ).process()
        assert len(glyphsets[0]["exclam"]) == 2
        assert len(glyphsets[0]["exclamdown"]) == 2
        assert len(glyphsets[1]["exclam"]) == 2
        assert len(glyphsets[1]["exclamdown"]) == 2
