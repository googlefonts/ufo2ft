from ufo2ft.featureWriters import MarkFeatureWriter
import math
from collections import OrderedDict

def quantize(number, degree):
    return degree * math.floor(number / degree)

class QuantizedMarkFeatureWriter(MarkFeatureWriter):
    options = dict(quantization=10)

    def _getAnchorLists(self):
        gdefClasses = self.context.gdefClasses
        if gdefClasses.base is not None:
            # only include the glyphs listed in the GDEF.GlyphClassDef groups
            include = gdefClasses.base | gdefClasses.ligature | gdefClasses.mark
        else:
            # no GDEF table defined in feature file, include all glyphs
            include = None
        result = OrderedDict()
        for glyphName, glyph in self.getOrderedGlyphSet().items():
            if include is not None and glyphName not in include:
                continue
            anchorDict = OrderedDict()
            for anchor in glyph.anchors:
                anchorName = anchor.name
                if not anchorName:
                    self.log.warning(
                        "unnamed anchor discarded in glyph '%s'", glyphName
                    )
                    continue
                if anchorName in anchorDict:
                    self.log.warning(
                        "duplicate anchor '%s' in glyph '%s'", anchorName, glyphName
                    )
                x = quantize(anchor.x, self.options.quantization)
                y = quantize(anchor.y, self.options.quantization)
                a = self.NamedAnchor(name=anchorName, x=x, y=y)
                anchorDict[anchorName] = a
            if anchorDict:
                result[glyphName] = list(anchorDict.values())
        return result
