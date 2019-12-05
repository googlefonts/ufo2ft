from ufo2ft.filters import BaseFilter
from ufo2ft.util import _GlyphSet


COLOR_LAYER_MAPPING_KEY = "com.github.googlei18n.ufo2ft.colorLayerMapping"
COLOR_LAYERS_KEY = "com.github.googlei18n.ufo2ft.colorLayers"


class ExplodeColorLayerGlyphsFilter(BaseFilter):

    def start(self):
        self._layerGlyphSets = {}

    def set_context(self, font, glyphSet):
        self.globalColorLayerMapping = font.lib.get(COLOR_LAYER_MAPPING_KEY)
        font.lib[COLOR_LAYERS_KEY] = {}
        return super().set_context(font, glyphSet)
        
    def _getLayer(self, font, layerName):
        layer = self._layerGlyphSets.get(layerName)
        if layer is None:
            layer = _GlyphSet.from_layer(font, layerName)
            self._layerGlyphSets[layerName] = layer
        return layer

    def filter(self, glyph):
        """ This doesn't really filter glyphs, but copies glyphs from UFO layers
        to alternate glyphs, for use in the COLR table.
        """
        font = self.context.font
        glyphSet = self.context.glyphSet
        colorLayers = font.lib[COLOR_LAYERS_KEY]
        colorLayerMapping = glyph.lib.get(COLOR_LAYER_MAPPING_KEY)
        if colorLayerMapping is None:
            colorLayerMapping = self.globalColorLayerMapping
        if colorLayerMapping is None:
            # No color layer info for this glyph
            return
        layers = []
        for layerName, colorID in colorLayerMapping:
            layerGlyphSet = self._getLayer(font, layerName)
            layerGlyph = layerGlyphSet[glyph.name]
            if layerGlyph:
                layerGlyphName = f"{glyph.name}.{layerName}"
                assert layerGlyphName not in glyphSet
                glyphSet[layerGlyphName] = layerGlyph
                layers.append((layerGlyphName, colorID))
        if layers:
            colorLayers[glyph.name] = layers
