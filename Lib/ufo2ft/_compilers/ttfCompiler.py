from dataclasses import dataclass
from typing import Optional, Type

from ufo2ft.outlineCompiler import OutlineTTFCompiler
from ufo2ft.preProcessor import TTFPreProcessor
from ufo2ft.util import prune_unknown_kwargs

from .baseCompiler import BaseCompiler


@dataclass
class TTFCompiler(BaseCompiler):
    preProcessorClass: Type = TTFPreProcessor
    outlineCompilerClass: Type = OutlineTTFCompiler
    convertCubics: bool = True
    cubicConversionError: Optional[float] = None
    reverseDirection: bool = True
    rememberCurveType: bool = True
    flattenComponents: bool = False
    autoUseMyMetrics: bool = True
    dropImpliedOnCurves: bool = False
    allQuadratic: bool = True

    """Create FontTools TrueType font from a UFO.

    *removeOverlaps* performs a union operation on all the glyphs' contours.

    *flattenComponents* un-nests glyphs so that they have at most one level of
    components.

    *convertCubics* and *cubicConversionError* specify how the conversion from cubic
    to quadratic curves should be handled.

    *layerName* specifies which layer should be compiled. When compiling something
    other than the default layer, feature compilation is skipped.

    *skipExportGlyphs* is a list or set of glyph names to not be exported to the
    final font. If these glyphs are used as components in any other glyph, those
    components get decomposed. If the parameter is not passed in, the UFO's
    "public.skipExportGlyphs" lib key will be consulted. If it doesn't exist,
    all glyphs are exported. UFO groups and kerning will be pruned of skipped
    glyphs.

    *dropImpliedOnCurves* (bool) specifies whether on-curve points that are exactly
    in between two off-curves can be dropped when building glyphs (default: False).

    *allQuadratic* (bool) specifies whether to convert all curves to quadratic - True
    by default, builds traditional glyf v0 table. If False, quadratic curves or cubic
    curves are generated depending on which has fewer points; a glyf v1 is generated.
    """

    # @timer("compile a basic TTF")
    def compileOutlines(self, ufo, glyphSet, layerName=None):
        kwargs = prune_unknown_kwargs(self.__dict__, self.outlineCompilerClass)
        kwargs["glyphDataFormat"] = 0 if self.allQuadratic else 1
        outlineCompiler = self.outlineCompilerClass(ufo, glyphSet=glyphSet, **kwargs)
        return outlineCompiler.compile()
