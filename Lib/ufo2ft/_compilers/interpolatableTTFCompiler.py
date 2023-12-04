from dataclasses import dataclass
from typing import Type

from fontTools import varLib

from ufo2ft.constants import SPARSE_TTF_MASTER_TABLES
from ufo2ft.outlineCompiler import OutlineTTFCompiler
from ufo2ft.preProcessor import TTFInterpolatablePreProcessor
from ufo2ft.util import _LazyFontName, prune_unknown_kwargs

from .baseCompiler import DesignspaceCompiler


@dataclass
class InterpolatableTTFCompiler(DesignspaceCompiler):
    preProcessorClass: Type = TTFInterpolatablePreProcessor
    outlineCompilerClass: Type = OutlineTTFCompiler
    convertCubics: bool = True
    cubicConversionError: float = None
    reverseDirection: bool = True
    flattenComponents: bool = False
    layerNames: str = None
    colrLayerReuse: bool = False
    colrAutoClipBoxes: bool = False
    extraSubstitutions: bool = None
    autoUseMyMetrics: bool = True
    allQuadratic: bool = True
    skipFeatureCompilation: bool = False
    """Create FontTools TrueType fonts from a list of UFOs with interpolatable
    outlines. Cubic curves are converted compatibly to quadratic curves using
    the Cu2Qu conversion algorithm.

    Return an iterator object that yields a TTFont instance for each UFO.

    *layerNames* refers to the layer names to use glyphs from in the order of
    the UFOs in *ufos*. By default, this is a list of `[None]` times the number
    of UFOs, i.e. using the default layer from all the UFOs.

    When the layerName is not None for a given UFO, the corresponding TTFont object
    will contain only a minimum set of tables ("head", "hmtx", "glyf", "loca", "maxp",
    "post" and "vmtx"), and no OpenType layout tables.

    *skipExportGlyphs* is a list or set of glyph names to not be exported to the
    final font. If these glyphs are used as components in any other glyph, those
    components get decomposed. If the parameter is not passed in, the union of
    all UFO's "public.skipExportGlyphs" lib keys will be used. If they don't
    exist, all glyphs are exported. UFO groups and kerning will be pruned of
    skipped glyphs.
    """

    def compile(self, ufos):
        if self.layerNames is None:
            self.layerNames = [None] * len(ufos)
        assert len(ufos) == len(self.layerNames)
        glyphSets = self.preprocess(ufos)

        for ufo, glyphSet, layerName in zip(ufos, glyphSets, self.layerNames):
            yield self.compile_one(ufo, glyphSet, layerName)

    def compile_one(self, ufo, glyphSet, layerName):
        fontName = _LazyFontName(ufo)
        if layerName is not None:
            self.logger.info("Building OpenType tables for %s-%s", fontName, layerName)
        else:
            self.logger.info("Building OpenType tables for %s", fontName)

        ttf = self.compileOutlines(ufo, glyphSet, layerName)

        # Only the default layer is likely to have all glyphs used in feature
        # code.
        if layerName is None and not self.skipFeatureCompilation:
            if self.debugFeatureFile:
                self.debugFeatureFile.write("\n### %s ###\n" % fontName)
            self.compileFeatures(ufo, ttf, glyphSet=glyphSet)

        ttf = self.postprocess(ttf, ufo, glyphSet)

        if layerName is not None:
            # for sparse masters (i.e. containing only a subset of the glyphs), we
            # need to include the post table in order to store glyph names, so that
            # fontTools.varLib can interpolate glyphs with same name across masters.
            # However we want to prevent the underlinePosition/underlineThickness
            # fields in such sparse masters to be included when computing the deltas
            # for the MVAR table. Thus, we set them to this unlikely, limit value
            # (-36768) which is a signal varLib should ignore them when building MVAR.
            ttf["post"].underlinePosition = -0x8000
            ttf["post"].underlineThickness = -0x8000

        return ttf

    # @timer("compile a basic TTF")
    def compileOutlines(self, ufo, glyphSet, layerName=None):
        kwargs = prune_unknown_kwargs(self.__dict__, self.outlineCompilerClass)
        kwargs["glyphDataFormat"] = 0 if self.allQuadratic else 1
        kwargs["tables"] = SPARSE_TTF_MASTER_TABLES if layerName else None
        # we want to keep coordinates as floats in glyf masters so that fonttools
        # can compute impliable on-curve points from unrounded coordinates before
        # building the VF
        kwargs["roundCoordinates"] = False
        outlineCompiler = self.outlineCompilerClass(ufo, glyphSet=glyphSet, **kwargs)
        return outlineCompiler.compile()

    def compile_designspace(self, designSpaceDoc):
        ufos = self._pre_compile_designspace(designSpaceDoc)
        ttfs = self.compile(ufos)
        return self._post_compile_designspace(designSpaceDoc, ttfs)

    def _merge(self, designSpaceDoc, excludeVariationTables):
        return varLib.build_many(
            designSpaceDoc,
            exclude=excludeVariationTables,
            optimize=self.optimizeGvar,
            skip_vf=lambda vf_name: self.variableFontNames
            and vf_name not in self.variableFontNames,
            colr_layer_reuse=self.colrLayerReuse,
            drop_implied_oncurves=self.dropImpliedOnCurves,
        )
