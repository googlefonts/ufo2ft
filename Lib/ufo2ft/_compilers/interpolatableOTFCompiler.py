import dataclasses
from dataclasses import dataclass
from typing import Type, Optional

from fontTools import varLib

from ufo2ft.constants import SPARSE_OTF_MASTER_TABLES, CFFOptimization
from ufo2ft.outlineCompiler import OutlineOTFCompiler
from ufo2ft.preProcessor import OTFPreProcessor

from .baseCompiler import BaseInterpolatableCompiler
from .otfCompiler import OTFCompiler


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
    """Create FontTools CFF fonts from the DesignSpaceDocument UFO sources
    with interpolatable outlines.

    Interpolatable means without subroutinization and specializer optimizations
    and no removal of overlaps.

    If the Designspace contains a "public.skipExportGlyphs" lib key, these
    glyphs will not be exported to the final font. If these glyphs are used as
    components in any other glyph, those components get decomposed. If the lib
    key doesn't exist in the Designspace, all glyphs are exported (keys in
    individual UFOs are ignored). UFO groups and kerning will be pruned of
    skipped glyphs.

    The DesignSpaceDocument should contain SourceDescriptor objects with 'font'
    attribute set to an already loaded defcon.Font object (or compatible UFO
    Font class). If 'font' attribute is unset or None, an AttributeError exception
    is thrown.

    Return a copy of the DesignSpaceDocument object (or the same one if
    inplace=True) with the source's 'font' attribute set to the corresponding
    TTFont instance.

    For sources that have the 'layerName' attribute defined, the corresponding TTFont
    object will contain only a minimum set of tables ("head", "hmtx", "CFF ", "maxp",
    "vmtx" and "VORG"), and no OpenType layout tables.
    """

    def compile_designspace(self, designSpaceDoc):
        self._pre_compile_designspace(designSpaceDoc)
        otfs = []
        for source in designSpaceDoc.sources:
            # There's a Python bug where dataclasses.asdict() doesn't work with
            # dataclasses that contain a defaultdict.
            save_extraSubstitutions = self.extraSubstitutions
            self.extraSubstitutions = None
            args = {
                **dataclasses.asdict(self),
                **dict(
                    layerName=source.layerName,
                    removeOverlaps=False,
                    overlapsBackend=None,
                    optimizeCFF=CFFOptimization.NONE,
                    _tables=SPARSE_OTF_MASTER_TABLES if source.layerName else None,
                ),
            }
            compiler = InterpolatableOTFCompiler(**args)
            self.extraSubstitutions = save_extraSubstitutions
            otfs.append(compiler.compile(source.font))
        return self._post_compile_designspace(designSpaceDoc, otfs)

    def _merge(self, designSpaceDoc, excludeVariationTables):
        return varLib.build_many(
            designSpaceDoc,
            exclude=excludeVariationTables,
            optimize=self.optimizeCFF >= CFFOptimization.SPECIALIZE,
            skip_vf=lambda vf_name: self.variableFontNames
            and vf_name not in self.variableFontNames,
            colr_layer_reuse=self.colrLayerReuse,
        )
