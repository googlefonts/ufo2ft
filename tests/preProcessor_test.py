from __future__ import (
    print_function,
    division,
    absolute_import,
    unicode_literals,
)
import os
import logging
from ufo2ft.preProcessor import (
    TTFPreProcessor,
    TTFInterpolatablePreProcessor,
)
from cu2qu.ufo import CURVE_TYPE_LIB_KEY


def getpath(filename):
    dirname = os.path.dirname(__file__)
    return os.path.join(dirname, "data", filename)


def glyph_has_qcurve(ufo, glyph_name):
    return any(
        s.segmentType == "qcurve"
        for contour in ufo[glyph_name]
        for s in contour
    )


class TTFPreProcessorTest(object):

    def test_no_inplace(self, FontClass):
        ufo = FontClass(getpath("TestFont.ufo"))

        glyphSet = TTFPreProcessor(ufo, inplace=False).process()

        assert not glyph_has_qcurve(ufo, "c")
        assert glyph_has_qcurve(glyphSet, "c")
        assert CURVE_TYPE_LIB_KEY not in ufo.lib

    def test_inplace_remember_curve_type(self, FontClass, caplog):
        caplog.set_level(logging.ERROR)

        ufo = FontClass(getpath("TestFont.ufo"))

        assert CURVE_TYPE_LIB_KEY not in ufo.lib
        assert not glyph_has_qcurve(ufo, "c")

        TTFPreProcessor(
            ufo, inplace=True, rememberCurveType=True
        ).process()

        assert ufo.lib[CURVE_TYPE_LIB_KEY] == "quadratic"
        assert glyph_has_qcurve(ufo, "c")

        logger = "ufo2ft.filters.cubicToQuadratic"
        with caplog.at_level(logging.INFO, logger=logger):
            TTFPreProcessor(
                ufo, inplace=True, rememberCurveType=True
            ).process()

        assert len(caplog.records) == 1
        assert "Curves already converted to quadratic" in caplog.text
        assert glyph_has_qcurve(ufo, "c")

    def test_inplace_no_remember_curve_type(self, FontClass):
        ufo = FontClass(getpath("TestFont.ufo"))

        assert CURVE_TYPE_LIB_KEY not in ufo.lib

        for _ in range(2):
            TTFPreProcessor(
                ufo, inplace=True, rememberCurveType=False
            ).process()

            assert CURVE_TYPE_LIB_KEY not in ufo.lib
            assert glyph_has_qcurve(ufo, "c")


class TTFInterpolatablePreProcessorTest(object):

    def test_no_inplace(self, FontClass):
        ufo1 = FontClass(getpath("TestFont.ufo"))
        ufo2 = FontClass(getpath("TestFont.ufo"))
        ufos = [ufo1, ufo2]

        assert CURVE_TYPE_LIB_KEY not in ufo1.lib
        assert not glyph_has_qcurve(ufo1, "c")

        glyphSets = TTFInterpolatablePreProcessor(
            ufos, inplace=False
        ).process()

        for i in range(2):
            assert glyph_has_qcurve(glyphSets[i], "c")
            assert CURVE_TYPE_LIB_KEY not in ufos[i].lib
            assert CURVE_TYPE_LIB_KEY not in ufos[i].lib

    def test_inplace_remember_curve_type(self, FontClass):
        ufo1 = FontClass(getpath("TestFont.ufo"))
        ufo2 = FontClass(getpath("TestFont.ufo"))
        ufos = [ufo1, ufo2]

        assert CURVE_TYPE_LIB_KEY not in ufo1.lib
        assert not glyph_has_qcurve(ufo1, "c")

        TTFInterpolatablePreProcessor(
            ufos, inplace=True, rememberCurveType=True
        ).process()

        assert ufo1.lib[CURVE_TYPE_LIB_KEY] == "quadratic"
        assert glyph_has_qcurve(ufo1, "c")
        assert ufo2.lib[CURVE_TYPE_LIB_KEY] == "quadratic"
        assert glyph_has_qcurve(ufo2, "c")

    def test_inplace_no_remember_curve_type(self, FontClass):
        ufo1 = FontClass(getpath("TestFont.ufo"))
        ufo2 = FontClass(getpath("TestFont.ufo"))
        ufos = [ufo1, ufo2]

        for _ in range(2):
            TTFInterpolatablePreProcessor(
                ufos, inplace=True, rememberCurveType=False
            ).process()

            assert CURVE_TYPE_LIB_KEY not in ufo1.lib
            assert CURVE_TYPE_LIB_KEY not in ufo2.lib
            assert glyph_has_qcurve(ufo1, "c")
            assert glyph_has_qcurve(ufo2, "c")
