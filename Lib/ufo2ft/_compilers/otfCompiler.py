from dataclasses import dataclass
from typing import Optional, Type

from ufo2ft.constants import CFFOptimization
from ufo2ft.outlineCompiler import OutlineOTFCompiler
from ufo2ft.preProcessor import OTFPreProcessor

from .baseCompiler import BaseCompiler


@dataclass
class OTFCompiler(BaseCompiler):
    preProcessorClass: Type = OTFPreProcessor
    outlineCompilerClass: Type = OutlineOTFCompiler
    optimizeCFF: CFFOptimization = CFFOptimization.SUBROUTINIZE
    roundTolerance: Optional[float] = None
    cffVersion: int = 1
    subroutinizer: Optional[str] = None
