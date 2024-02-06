from dataclasses import dataclass
from typing import Optional, Type

from fontTools import varLib

from ufo2ft.constants import SPARSE_TTF_MASTER_TABLES
from ufo2ft.outlineCompiler import OutlineTTFCompiler
from ufo2ft.preProcessor import TTFInterpolatablePreProcessor
from ufo2ft.util import _LazyFontName, prune_unknown_kwargs

from .baseCompiler import BaseInterpolatableCompiler


@dataclass
class InterpolatableTTFCompiler(BaseInterpolatableCompiler):
    preProcessorClass: Type = TTFInterpolatablePreProcessor
    outlineCompilerClass: Type = OutlineTTFCompiler
    convertCubics: bool = True
    cubicConversionError: Optional[float] = None
    reverseDirection: bool = True
    flattenComponents: bool = False
    layerNames: Optional[str] = None
    colrLayerReuse: bool = False
    colrAutoClipBoxes: bool = False
    extraSubstitutions: Optional[bool] = None
    autoUseMyMetrics: bool = True
    allQuadratic: bool = True
    skipFeatureCompilation: bool = False

    def compile(self, ufos):
        if self.layerNames is None:
            self.layerNames = [None] * len(ufos)
        assert len(ufos) == len(self.layerNames)
        self.glyphSets = self.preprocess(ufos)

        for ufo, glyphSet, layerName in zip(ufos, self.glyphSets, self.layerNames):
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

    def compileOutlines(self, ufo, glyphSet, layerName=None):
        kwargs = prune_unknown_kwargs(self.__dict__, self.outlineCompilerClass)
        kwargs["glyphDataFormat"] = 0 if self.allQuadratic else 1
        kwargs["tables"] = SPARSE_TTF_MASTER_TABLES if layerName else None
        # we want to keep coordinates as floats in glyf masters so that fonttools
        # can compute impliable on-curve points from unrounded coordinates before
        # building the VF
        kwargs["roundCoordinates"] = False
        # keep impliable oncurve points in the interpolatable master TTFs, they will
        # be pruned at the end by varLib in the final VF.
        kwargs["dropImpliedOnCurves"] = False
        outlineCompiler = self.outlineCompilerClass(ufo, glyphSet=glyphSet, **kwargs)
        return outlineCompiler.compile()

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
