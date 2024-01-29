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
    roundTolerance: Optional[float] = None
    cffVersion: int = 1
    subroutinizer: Optional[str] = None
    _tables: Optional[list] = None
    extraSubstitutions: Optional[dict] = None

    def compileOutlines(self, ufo, glyphSet):
        kwargs = prune_unknown_kwargs(self.__dict__, self.outlineCompilerClass)
        kwargs["optimizeCFF"] = self.optimizeCFF >= CFFOptimization.SPECIALIZE
        kwargs["tables"] = self._tables
        outlineCompiler = self.outlineCompilerClass(ufo, glyphSet=glyphSet, **kwargs)
        return outlineCompiler.compile()

    def postprocess(self, font, ufo, glyphSet, info=None):
        if self.postProcessorClass is not None:
            postProcessor = self.postProcessorClass(
                font, ufo, glyphSet=glyphSet, info=info
            )
            kwargs = prune_unknown_kwargs(self.__dict__, postProcessor.process)
            kwargs["optimizeCFF"] = self.optimizeCFF >= CFFOptimization.SUBROUTINIZE
            font = postProcessor.process(**kwargs)
        self._glyphSet = glyphSet
        return font
