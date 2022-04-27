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

        # nine.lf has one transformed component of a componenent
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
