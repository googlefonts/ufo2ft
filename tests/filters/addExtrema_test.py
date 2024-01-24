from ufo2ft.filters.addExtrema import AddExtremaFilter


class AddExtremaFilterTest:
    def test_add_extrema_O(self, FontClass):
        ufo = FontClass()
        a = ufo.newGlyph("O")
        a.width = 300
        pen = a.getPen()
        pen.moveTo((150, 0))
        pen.curveTo((249, 0), (249, 150), (150, 150))
        pen.curveTo((52, 150), (52, 0), (150, 0))
        pen.closePath()

        contour = ufo["O"][0]
        assert len(contour) == 6

        filter_ = AddExtremaFilter()

        assert filter_(ufo)

        contour = ufo["O"][0]
        assert len(contour) == 12
