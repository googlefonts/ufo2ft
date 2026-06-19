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

    def compileOutlines(self, ufo, glyphSet):
        kwargs = prune_unknown_kwargs(self.__dict__, self.outlineCompilerClass)
        kwargs["allowCubic"] = not self.allQuadratic
        outlineCompiler = self.outlineCompilerClass(ufo, glyphSet=glyphSet, **kwargs)
        return outlineCompiler.compile()
