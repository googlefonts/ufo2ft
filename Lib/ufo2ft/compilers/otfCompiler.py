from dataclasses import dataclass
from typing import Optional, Type

from ufo2ft.constants import CFFOptimization
from ufo2ft.outlineCompiler import OutlineOTFCompiler
from ufo2ft.preProcessor import OTFPreProcessor
from ufo2ft.util import prune_unknown_kwargs

from .baseCompiler import BaseCompiler


@dataclass
class OTFCompiler(BaseCompiler):
    preProcessorClass: Type = OTFPreProcessor
    outlineCompilerClass: Type = OutlineOTFCompiler
    optimizeCFF: CFFOptimization = CFFOptimization.SUBROUTINIZE
    roundTolerance: float = None
    cffVersion: int = 1
    subroutinizer: Optional[str] = None
    _tables: list = None
    extraSubstitutions: dict = None

    """Create FontTools CFF font from a UFO.

    *removeOverlaps* performs a union operation on all the glyphs' contours.

    *optimizeCFF* (int) defines whether the CFF charstrings should be
      specialized and subroutinized. By default both optimization are enabled.
      A value of 0 disables both; 1 only enables the specialization; 2 (default)
      does both specialization and subroutinization.

    *roundTolerance* (float) controls the rounding of point coordinates.
      It is defined as the maximum absolute difference between the original
      float and the rounded integer value.
      By default, all floats are rounded to integer (tolerance 0.5); a value
      of 0 completely disables rounding; values in between only round floats
      which are close to their integral part within the tolerated range.

    *featureWriters* argument is a list of BaseFeatureWriter subclasses or
      pre-initialized instances. Features will be written by each feature
      writer in the given order. If featureWriters is None, the default
      feature writers [KernFeatureWriter, MarkFeatureWriter] are used.

    *filters* argument is a list of BaseFilters subclasses or pre-initialized
      instances. Filters with 'pre' attribute set to True will be pre-filters
      called before the default filters, otherwise they will be post-filters,
      called after the default filters.
      Filters will modify glyphs or the glyph set. The default filters cannot
      be disabled.

    *useProductionNames* renames glyphs in TrueType 'post' or OpenType 'CFF '
      tables based on the 'public.postscriptNames' mapping in the UFO lib,
      if present. Otherwise, uniXXXX names are generated from the glyphs'
      unicode values. The default value (None) will first check if the UFO lib
      has the 'com.github.googlei18n.ufo2ft.useProductionNames' key. If this
      is missing or True (default), the glyphs are renamed. Set to False
      to keep the original names.

    **inplace** (bool) specifies whether the filters should modify the input
      UFO's glyphs, a copy should be made first.

    *layerName* specifies which layer should be compiled. When compiling something
    other than the default layer, feature compilation is skipped.

    *skipExportGlyphs* is a list or set of glyph names to not be exported to the
    final font. If these glyphs are used as components in any other glyph, those
    components get decomposed. If the parameter is not passed in, the UFO's
    "public.skipExportGlyphs" lib key will be consulted. If it doesn't exist,
    all glyphs are exported. UFO groups and kerning will be pruned of skipped
    glyphs.

    *cffVersion* (int) is the CFF format, choose between 1 (default) and 2.

    *subroutinizer* (Optional[str]) is the name of the library to use for
      compressing CFF charstrings, if subroutinization is enabled by optimizeCFF
      parameter. Choose between "cffsubr" or "compreffor".
      By default "cffsubr" is used for both CFF 1 and CFF 2.
      NOTE: cffsubr is required for subroutinizing CFF2 tables, as compreffor
      currently doesn't support it.
    """

    def compileOutlines(self, ufo, glyphSet):
        kwargs = prune_unknown_kwargs(self.__dict__, self.outlineCompilerClass)
        kwargs["optimizeCFF"] = self.optimizeCFF >= CFFOptimization.SPECIALIZE
        kwargs["tables"] = self._tables
        outlineCompiler = self.outlineCompilerClass(ufo, glyphSet=glyphSet, **kwargs)
        return outlineCompiler.compile()

    def postprocess(self, font, ufo, glyphSet):
        if self.postProcessorClass is not None:
            postProcessor = self.postProcessorClass(font, ufo, glyphSet=glyphSet)
            kwargs = prune_unknown_kwargs(self.__dict__, postProcessor.process)
            kwargs["optimizeCFF"] = self.optimizeCFF >= CFFOptimization.SUBROUTINIZE
            ttf = postProcessor.process(**kwargs)
        return ttf
