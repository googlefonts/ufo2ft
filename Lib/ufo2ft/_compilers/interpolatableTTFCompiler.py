from dataclasses import dataclass
from typing import Optional, Type

from fontTools import varLib

from ufo2ft.constants import SPARSE_TTF_MASTER_TABLES
from ufo2ft.outlineCompiler import OutlineTTFCompiler
from ufo2ft.preProcessor import TTFInterpolatablePreProcessor
from ufo2ft.util import prune_unknown_kwargs

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
    autoUseMyMetrics: bool = True
    allQuadratic: bool = True
    skipFeatureCompilation: bool = False

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
