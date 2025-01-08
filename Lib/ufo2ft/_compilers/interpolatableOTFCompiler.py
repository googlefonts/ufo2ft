from dataclasses import dataclass
from typing import Optional, Type

from fontTools import varLib

from ufo2ft.constants import SPARSE_OTF_MASTER_TABLES, CFFOptimization
from ufo2ft.outlineCompiler import OutlineOTFCompiler
from ufo2ft.preProcessor import OTFInterpolatablePreProcessor
from ufo2ft.util import prune_unknown_kwargs

from .baseCompiler import BaseInterpolatableCompiler


@dataclass
class InterpolatableOTFCompiler(BaseInterpolatableCompiler):
    preProcessorClass: Type = OTFInterpolatablePreProcessor
    outlineCompilerClass: Type = OutlineOTFCompiler
    roundTolerance: Optional[float] = None
    optimizeCFF: CFFOptimization = CFFOptimization.NONE
    colrLayerReuse: bool = False
    colrAutoClipBoxes: bool = False
    skipFeatureCompilation: bool = False

    def compileOutlines(self, ufo, glyphSet, layerName=None):
        kwargs = prune_unknown_kwargs(self.__dict__, self.outlineCompilerClass)
        kwargs["tables"] = SPARSE_OTF_MASTER_TABLES if layerName is not None else None
        kwargs["optimizeCFF"] = CFFOptimization.NONE
        outlineCompiler = self.outlineCompilerClass(ufo, glyphSet=glyphSet, **kwargs)
        return outlineCompiler.compile()

    def _merge(self, designSpaceDoc, excludeVariationTables):
        return varLib.build_many(
            designSpaceDoc,
            exclude=excludeVariationTables,
            optimize=self.optimizeCFF >= CFFOptimization.SPECIALIZE,
            skip_vf=lambda vf_name: self.variableFontNames
            and vf_name not in self.variableFontNames,
            colr_layer_reuse=self.colrLayerReuse,
        )
