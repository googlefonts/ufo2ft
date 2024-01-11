from dataclasses import dataclass
from typing import Optional, Type

from ufo2ft.constants import CFFOptimization
from ufo2ft.outlineCompiler import OutlineOTFCompiler
from ufo2ft.preProcessor import OTFPreProcessor

from .interpolatableOTFCompiler import InterpolatableOTFCompiler


@dataclass
class VariableCFF2sCompiler(InterpolatableOTFCompiler):
    preProcessorClass: Type = OTFPreProcessor
    outlineCompilerClass: Type = OutlineOTFCompiler
    roundTolerance: Optional[float] = None
    colrAutoClipBoxes: bool = False
    cffVersion: int = 2
    optimizeCFF: CFFOptimization = CFFOptimization.SPECIALIZE
    excludeVariationTables: tuple = ()
    variableFeatures: bool = True
