import logging
import os

import pytest
from cu2qu.ufo import CURVE_TYPE_LIB_KEY
from fontTools import designspaceLib

import ufo2ft
from ufo2ft.constants import (
    COLOR_LAYER_MAPPING_KEY,
    COLOR_LAYERS_KEY,
    COLOR_PALETTES_KEY,
)
from ufo2ft.filters import FILTERS_KEY, loadFilterFromString
from ufo2ft.filters.explodeColorLayerGlyphs import ExplodeColorLayerGlyphsFilter
from ufo2ft.preProcessor import (
    TTFInterpolatablePreProcessor,
    TTFPreProcessor,
    _init_explode_color_layer_glyphs_filter,
)


def getpath(filename):
    dirname = os.path.dirname(__file__)
    return os.path.join(dirname, "data", filename)


def glyph_has_qcurve(ufo, glyph_name):
    return any(
        s.segmentType == "qcurve" for contour in ufo[glyph_name] for s in contour
    )


class TTFPreProcessorTest:
    def test_no_inplace(self, FontClass):
        ufo = FontClass(getpath("TestFont.ufo"))

        glyphSet = TTFPreProcessor(ufo, inplace=False).process()

        assert not glyph_has_qcurve(ufo, "c")
        assert glyph_has_qcurve(glyphSet, "c")
        assert CURVE_TYPE_LIB_KEY not in ufo.layers.defaultLayer.lib

    def test_inplace_remember_curve_type(self, FontClass, caplog):
        caplog.set_level(logging.ERROR)

        ufo = FontClass(getpath("TestFont.ufo"))

        assert CURVE_TYPE_LIB_KEY not in ufo.lib
        assert CURVE_TYPE_LIB_KEY not in ufo.layers.defaultLayer.lib
        assert not glyph_has_qcurve(ufo, "c")

        TTFPreProcessor(ufo, inplace=True, rememberCurveType=True).process()

        assert CURVE_TYPE_LIB_KEY not in ufo.lib
        assert ufo.layers.defaultLayer.lib[CURVE_TYPE_LIB_KEY] == "quadratic"
        assert glyph_has_qcurve(ufo, "c")

        logger = "ufo2ft.filters.cubicToQuadratic"
        with caplog.at_level(logging.INFO, logger=logger):
            TTFPreProcessor(ufo, inplace=True, rememberCurveType=True).process()

        assert len(caplog.records) == 1
        assert "Curves already converted to quadratic" in caplog.text
        assert glyph_has_qcurve(ufo, "c")

    def test_inplace_no_remember_curve_type(self, FontClass):
        ufo = FontClass(getpath("TestFont.ufo"))

        assert CURVE_TYPE_LIB_KEY not in ufo.lib
        assert CURVE_TYPE_LIB_KEY not in ufo.layers.defaultLayer.lib

        for _ in range(2):
            TTFPreProcessor(ufo, inplace=True, rememberCurveType=False).process()

            assert CURVE_TYPE_LIB_KEY not in ufo.lib
            assert CURVE_TYPE_LIB_KEY not in ufo.layers.defaultLayer.lib
            assert glyph_has_qcurve(ufo, "c")

    def test_custom_filters(self, FontClass):
        ufo1 = FontClass(getpath("TestFont.ufo"))
        ufo1.lib[FILTERS_KEY] = [
            {"name": "transformations", "kwargs": {"OffsetX": -40}, "pre": True}
        ]
        ufo2 = FontClass(getpath("TestFont.ufo"))
        ufo2.lib[FILTERS_KEY] = [{"name": "transformations", "kwargs": {"OffsetY": 10}}]

        glyphSets0 = TTFPreProcessor(ufo1).process()
        glyphSets1 = TTFPreProcessor(ufo2).process()

        assert (glyphSets0["a"][0][0].x - glyphSets1["a"][0][0].x) == -40
        assert (glyphSets1["a"][0][0].y - glyphSets0["a"][0][0].y) == 10

    def test_custom_filters_as_argument(self, FontClass):
        from ufo2ft.filters import RemoveOverlapsFilter, TransformationsFilter

        ufo1 = FontClass(getpath("TestFont.ufo"))
        ufo2 = FontClass(getpath("TestFont.ufo"))
        filter1 = RemoveOverlapsFilter(backend="pathops")
        filter2 = TransformationsFilter(include=["d"], pre=True, OffsetY=-200)
        filter3 = TransformationsFilter(OffsetX=10)

        glyphSets0 = TTFPreProcessor(
            ufo1, filters=[filter1, filter2, filter3]
        ).process()
        glyphSets1 = TTFPreProcessor(
            ufo2, filters=[filter1, filter2, filter3]
        ).process()

        # Both UFOs have the same filters applied
        assert (glyphSets0["a"][0][0].x - glyphSets1["a"][0][0].x) == 0
        # "a" has initially its starting point at (66, 0)
        assert (glyphSets0["a"][0][0].x, glyphSets0["a"][0][0].y) == (76, 0)
        assert (glyphSets1["a"][0][0].x, glyphSets1["a"][0][0].y) == (76, 0)
        # A component was shifted to overlap with another in a pre-filter
        # filter2, before overlaps were removed in a post-filter filter1
        assert len(glyphSets0["d"].components) == 0


class TTFInterpolatablePreProcessorTest:
    def test_no_inplace(self, FontClass):
        ufo1 = FontClass(getpath("TestFont.ufo"))
        ufo2 = FontClass(getpath("TestFont.ufo"))
        ufos = [ufo1, ufo2]

        assert CURVE_TYPE_LIB_KEY not in ufo1.lib
        assert CURVE_TYPE_LIB_KEY not in ufo1.layers.defaultLayer.lib
        assert not glyph_has_qcurve(ufo1, "c")

        glyphSets = TTFInterpolatablePreProcessor(ufos, inplace=False).process()

        for i in range(2):
            assert glyph_has_qcurve(glyphSets[i], "c")
            assert CURVE_TYPE_LIB_KEY not in ufos[i].lib
            assert CURVE_TYPE_LIB_KEY not in ufos[i].layers.defaultLayer.lib

    def test_inplace_remember_curve_type(self, FontClass):
        ufo1 = FontClass(getpath("TestFont.ufo"))
        ufo2 = FontClass(getpath("TestFont.ufo"))
        ufos = [ufo1, ufo2]

        assert CURVE_TYPE_LIB_KEY not in ufo1.lib
        assert CURVE_TYPE_LIB_KEY not in ufo1.layers.defaultLayer.lib
        assert not glyph_has_qcurve(ufo1, "c")

        TTFInterpolatablePreProcessor(
            ufos, inplace=True, rememberCurveType=True
        ).process()

        assert ufo1.layers.defaultLayer.lib[CURVE_TYPE_LIB_KEY] == "quadratic"
        assert glyph_has_qcurve(ufo1, "c")
        assert ufo2.layers.defaultLayer.lib[CURVE_TYPE_LIB_KEY] == "quadratic"
        assert glyph_has_qcurve(ufo2, "c")

    def test_inplace_no_remember_curve_type(self, FontClass):
        ufo1 = FontClass(getpath("TestFont.ufo"))
        ufo2 = FontClass(getpath("TestFont.ufo"))
        ufos = [ufo1, ufo2]

        for _ in range(2):
            TTFInterpolatablePreProcessor(
                ufos, inplace=True, rememberCurveType=False
            ).process()

            assert CURVE_TYPE_LIB_KEY not in ufo1.layers.defaultLayer.lib
            assert CURVE_TYPE_LIB_KEY not in ufo2.layers.defaultLayer.lib
            assert glyph_has_qcurve(ufo1, "c")
            assert glyph_has_qcurve(ufo2, "c")

    def test_custom_filters(self, FontClass):
        ufo1 = FontClass(getpath("TestFont.ufo"))
        ufo1.lib[FILTERS_KEY] = [
            {"name": "transformations", "kwargs": {"OffsetX": -40}, "pre": True}
        ]
        ufo2 = FontClass(getpath("TestFont.ufo"))
        ufo2.lib[FILTERS_KEY] = [{"name": "transformations", "kwargs": {"OffsetY": 10}}]
        ufos = [ufo1, ufo2]

        glyphSets = TTFInterpolatablePreProcessor(ufos).process()

        assert (glyphSets[0]["a"][0][0].x - glyphSets[1]["a"][0][0].x) == -40
        assert (glyphSets[1]["a"][0][0].y - glyphSets[0]["a"][0][0].y) == 10

    def test_custom_filters_as_argument(self, FontClass):
        ufo1 = FontClass(getpath("TestFont.ufo"))
        ufo2 = FontClass(getpath("TestFont.ufo"))
        filter1 = loadFilterFromString("RemoveOverlapsFilter(backend='pathops')")
        filter2 = loadFilterFromString(
            "TransformationsFilter(OffsetY=-200, include=['d'], pre=True)"
        )
        filter3 = loadFilterFromString("TransformationsFilter(OffsetX=10)")
        ufos = [ufo1, ufo2]

        glyphSets = TTFInterpolatablePreProcessor(
            ufos,
            filters=[filter1, filter2, filter3],
        ).process()

        # Both UFOs have the same filters applied
        assert (glyphSets[0]["a"][0][0].x - glyphSets[1]["a"][0][0].x) == 0
        # "a" has initially its starting point at (66, 0)
        assert (glyphSets[0]["a"][0][0].x, glyphSets[0]["a"][0][0].y) == (76, 0)
        assert (glyphSets[1]["a"][0][0].x, glyphSets[1]["a"][0][0].y) == (76, 0)
        # A component was shifted to overlap with another in a pre-filter
        # filter2, before overlaps were removed in a post-filter filter1
        assert len(glyphSets[0]["d"].components) == 0


class SkipExportGlyphsTest:
    def test_skip_export_glyphs_filter(self, FontClass):
        from ufo2ft.util import _GlyphSet

        ufo = FontClass(getpath("IncompatibleMasters/NewFont-Regular.ufo"))
        skipExportGlyphs = ["b", "d"]
        glyphSet = _GlyphSet.from_layer(ufo, skipExportGlyphs=skipExportGlyphs)

        assert set(glyphSet.keys()) == {"a", "c", "e", "f"}
        assert len(glyphSet["a"]) == 1
        assert not glyphSet["a"].components
        assert len(glyphSet["c"]) == 5  # 4 "d" components decomposed plus 1 outline
        assert list(c.baseGlyph for c in glyphSet["c"].components) == ["a"]
        assert len(glyphSet["e"]) == 1
        assert list(c.baseGlyph for c in glyphSet["e"].components) == ["c", "c"]
        assert not glyphSet["f"]
        assert list(c.baseGlyph for c in glyphSet["f"].components) == ["a", "a"]

    def test_skip_export_glyphs_filter_nested(self, FontClass):
        from ufo2ft.util import _GlyphSet

        ufo = FontClass()
        glyph_N = ufo.newGlyph("N")
        glyph_N.width = 100
        pen = glyph_N.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((300, 0))
        pen.lineTo((300, 400))
        pen.lineTo((0, 400))
        pen.closePath()

        glyph_o = ufo.newGlyph("o")
        glyph_o.width = 100
        pen = glyph_o.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((300, 0))
        pen.lineTo((300, 300))
        pen.lineTo((0, 300))
        pen.closePath()

        glyph_onumero = ufo.newGlyph("_o.numero")
        glyph_onumero.width = 100
        pen = glyph_onumero.getPen()
        pen.addComponent("o", (-1, 0, 0, -1, 0, 100))
        pen.moveTo((0, 0))
        pen.lineTo((300, 0))
        pen.lineTo((300, 50))
        pen.lineTo((0, 50))
        pen.closePath()

        glyph_numero = ufo.newGlyph("numero")
        glyph_numero.width = 200
        pen = glyph_numero.getPen()
        pen.addComponent("N", (1, 0, 0, 1, 0, 0))
        pen.addComponent("_o.numero", (1, 0, 0, 1, 400, 0))

        skipExportGlyphs = ["_o.numero"]
        glyphSet = _GlyphSet.from_layer(ufo, skipExportGlyphs=skipExportGlyphs)

        assert len(glyphSet["numero"].components) == 1  # The "N" component
        assert len(glyphSet["numero"]) == 2  # The two contours of "o" and "_o.numero"

    def test_skip_export_glyphs_designspace(self, FontClass):
        # Designspace has a public.skipExportGlyphs lib key excluding "b" and "d".
        designspace = designspaceLib.DesignSpaceDocument.fromfile(
            getpath("IncompatibleMasters/IncompatibleMasters.designspace")
        )
        for source in designspace.sources:
            source.font = FontClass(
                getpath(os.path.join("IncompatibleMasters", source.filename))
            )
        ufo2ft.compileInterpolatableTTFsFromDS(designspace, inplace=True)

        for source in designspace.sources:
            assert source.font.getGlyphOrder() == [".notdef", "a", "c", "e", "f"]
            gpos_table = source.font["GPOS"].table
            assert gpos_table.LookupList.Lookup[0].SubTable[0].Coverage.glyphs == [
                "a",
                "e",
                "f",
            ]
            glyphs = source.font["glyf"].glyphs
            for g in glyphs.values():
                g.expand(source.font["glyf"])
            assert glyphs["a"].numberOfContours == 1
            assert not hasattr(glyphs["a"], "components")
            assert glyphs["c"].numberOfContours == 6
            assert not hasattr(glyphs["c"], "components")
            assert glyphs["e"].numberOfContours == 13
            assert not hasattr(glyphs["e"], "components")
            assert glyphs["f"].isComposite()

    def test_skip_export_glyphs_multi_ufo(self, FontClass):
        # Bold has a public.skipExportGlyphs lib key excluding "b", "d" and "f".
        ufo1 = FontClass(getpath("IncompatibleMasters/NewFont-Regular.ufo"))
        ufo2 = FontClass(getpath("IncompatibleMasters/NewFont-Bold.ufo"))
        fonts = ufo2ft.compileInterpolatableTTFs([ufo1, ufo2], inplace=True)

        for font in fonts:
            assert set(font.getGlyphOrder()) == {".notdef", "a", "c", "e"}
            gpos_table = font["GPOS"].table
            assert gpos_table.LookupList.Lookup[0].SubTable[0].Coverage.glyphs == ["a"]
            glyphs = font["glyf"].glyphs
            for g in glyphs.values():
                g.expand(font["glyf"])
            assert glyphs["a"].numberOfContours == 1
            assert not hasattr(glyphs["a"], "components")
            assert glyphs["c"].numberOfContours == 6
            assert not hasattr(glyphs["c"], "components")
            assert glyphs["e"].numberOfContours == 13
            assert not hasattr(glyphs["e"], "components")

    def test_skip_export_glyphs_single_ufo(self, FontClass):
        # UFO has a public.skipExportGlyphs lib key excluding "b", "d" and "f".
        ufo = FontClass(getpath("IncompatibleMasters/NewFont-Bold.ufo"))
        font = ufo2ft.compileTTF(ufo, inplace=True)

        assert set(font.getGlyphOrder()) == {".notdef", "a", "c", "e"}
        gpos_table = font["GPOS"].table
        assert gpos_table.LookupList.Lookup[0].SubTable[0].Coverage.glyphs == ["a"]
        glyphs = font["glyf"].glyphs
        for g in glyphs.values():
            g.expand(font["glyf"])
        assert glyphs["a"].numberOfContours == 1
        assert not hasattr(glyphs["a"], "components")
        assert glyphs["c"].numberOfContours == 6
        assert not hasattr(glyphs["c"], "components")
        assert glyphs["e"].numberOfContours == 13
        assert not hasattr(glyphs["e"], "components")


@pytest.fixture
def color_ufo(FontClass):
    ufo = FontClass()
    ufo.lib[COLOR_PALETTES_KEY] = [[(1, 0.3, 0.1, 1), (0, 0.4, 0.8, 1)]]
    return ufo


class InitExplodeColorLayerGlyphsFilterTest:
    def test_no_color_palettes(self, FontClass):
        ufo = FontClass()
        filters = []
        _init_explode_color_layer_glyphs_filter(ufo, filters)
        assert not filters

    def test_no_color_layer_mapping(self, color_ufo):
        filters = []
        _init_explode_color_layer_glyphs_filter(color_ufo, filters)
        assert not filters

    def test_explicit_color_layers(self, color_ufo):
        color_ufo.lib[COLOR_LAYERS_KEY] = {"a": [("a.z_0", 1), ("a.z_1", 0)]}
        filters = []
        _init_explode_color_layer_glyphs_filter(color_ufo, filters)
        assert not filters

    def test_font_color_layer_mapping(self, color_ufo):
        color_ufo.lib[COLOR_LAYER_MAPPING_KEY] = [("z_0", 1), ("z_1", 0)]
        filters = []
        _init_explode_color_layer_glyphs_filter(color_ufo, filters)
        assert isinstance(filters[0], ExplodeColorLayerGlyphsFilter)

    def test_glyph_color_layer_mapping(self, color_ufo):
        color_ufo.newGlyph("a").lib[COLOR_LAYER_MAPPING_KEY] = [("z_0", 0), ("z_1", 1)]
        filters = []
        _init_explode_color_layer_glyphs_filter(color_ufo, filters)
        assert isinstance(filters[0], ExplodeColorLayerGlyphsFilter)
