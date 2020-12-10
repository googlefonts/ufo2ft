from ufo2ft.filters.decomposeTransformedComponents import (
    DecomposeTransformedComponentsFilter,
)


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
