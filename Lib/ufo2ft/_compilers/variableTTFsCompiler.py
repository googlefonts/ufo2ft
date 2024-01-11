from dataclasses import dataclass
from typing import Optional, Type

from ufo2ft.outlineCompiler import OutlineTTFCompiler
from ufo2ft.preProcessor import TTFInterpolatablePreProcessor

from .interpolatableTTFCompiler import InterpolatableTTFCompiler


@dataclass
class VariableTTFsCompiler(InterpolatableTTFCompiler):
    preProcessorClass: Type = TTFInterpolatablePreProcessor
    outlineCompilerClass: Type = OutlineTTFCompiler
    convertCubics: bool = True
    cubicConversionError: Optional[float] = None
    reverseDirection: bool = True
    flattenComponents: bool = False
    excludeVariationTables: tuple = ()
    optimizeGvar: bool = True
    colrAutoClipBoxes: bool = False
    autoUseMyMetrics: bool = True
    dropImpliedOnCurves: bool = False
    allQuadratic: bool = True
    variableFeatures: bool = True
