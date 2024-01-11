import dataclasses
from dataclasses import dataclass
from typing import Optional, Type

from fontTools import varLib

from ufo2ft.constants import SPARSE_OTF_MASTER_TABLES, CFFOptimization
from ufo2ft.outlineCompiler import OutlineOTFCompiler
from ufo2ft.preProcessor import OTFPreProcessor
from ufo2ft.util import prune_unknown_kwargs

from .baseCompiler import BaseInterpolatableCompiler
from .otfCompiler import OTFCompiler


# We want the designspace handling of BaseInterpolatableCompiler but
# we also need to pick up the OTF-specific compileOutlines/postprocess
# methods from OTFCompiler.
@dataclass
class InterpolatableOTFCompiler(OTFCompiler, BaseInterpolatableCompiler):
    preProcessorClass: Type = OTFPreProcessor
    outlineCompilerClass: Type = OutlineOTFCompiler
    featureCompilerClass: Optional[Type] = None
    roundTolerance: Optional[float] = None
    optimizeCFF: CFFOptimization = CFFOptimization.NONE
    colrLayerReuse: bool = False
    colrAutoClipBoxes: bool = False
    extraSubstitutions: Optional[dict] = None
    skipFeatureCompilation: bool = False
    excludeVariationTables: tuple = ()

    # We can't use the same compile method as interpolatableTTFCompiler
    # because that has a TTFInterpolatablePreProcessor which preprocesses
    # all UFOs together, whereas we need to do the preprocessing one at
    # at a time.
    def compile(self, ufos):
        otfs = []
        for ufo, layerName in zip(ufos, self.layerNames):
            # There's a Python bug where dataclasses.asdict() doesn't work with
            # dataclasses that contain a defaultdict.
            save_extraSubstitutions = self.extraSubstitutions
            self.extraSubstitutions = None
            args = {
                **dataclasses.asdict(self),
                **dict(
                    layerName=layerName,
                    removeOverlaps=False,
                    overlapsBackend=None,
                    optimizeCFF=CFFOptimization.NONE,
                    _tables=SPARSE_OTF_MASTER_TABLES if layerName else None,
                ),
            }
            # Remove interpolatable-specific args
            args = prune_unknown_kwargs(args, OTFCompiler)
            compiler = OTFCompiler(**args)
            self.extraSubstitutions = save_extraSubstitutions
            otfs.append(compiler.compile(ufo))
            self.glyphSets.append(compiler._glyphSet)
        return otfs

    def _merge(self, designSpaceDoc, excludeVariationTables):
        return varLib.build_many(
            designSpaceDoc,
            exclude=excludeVariationTables,
            optimize=self.optimizeCFF >= CFFOptimization.SPECIALIZE,
            skip_vf=lambda vf_name: self.variableFontNames
            and vf_name not in self.variableFontNames,
            colr_layer_reuse=self.colrLayerReuse,
        )
