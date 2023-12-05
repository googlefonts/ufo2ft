import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Optional, Type

from fontTools import varLib
from fontTools.designspaceLib.split import splitInterpolable, splitVariableFonts
from fontTools.misc.loggingTools import Timer
from fontTools.otlLib.optimize.gpos import GPOS_COMPACT_MODE_ENV_KEY

from ufo2ft.constants import MTI_FEATURES_PREFIX
from ufo2ft.errors import InvalidDesignSpaceData
from ufo2ft.featureCompiler import (
    FeatureCompiler,
    MtiFeatureCompiler,
    VariableFeatureCompiler,
    _featuresCompatible,
)
from ufo2ft.postProcessor import PostProcessor
from ufo2ft.util import (
    _notdefGlyphFallback,
    colrClipBoxQuantization,
    ensure_all_sources_have_names,
    location_to_string,
    prune_unknown_kwargs,
)


@dataclass
class BaseCompiler:
    postProcessorClass: Type = PostProcessor
    featureCompilerClass: Optional[Type] = None
    featureWriters: Optional[list] = None
    filters: Optional[list] = None
    glyphOrder: Optional[list] = None
    useProductionNames: Optional[bool] = None
    removeOverlaps: bool = False
    overlapsBackend: Optional[str] = None
    inplace: bool = False
    layerName: Optional[str] = None
    skipExportGlyphs: Optional[bool] = None
    debugFeatureFile: Optional[str] = None
    notdefGlyph: Optional[str] = None
    colrLayerReuse: bool = True
    colrAutoClipBoxes: bool = True
    colrClipBoxQuantization: Callable[[object], int] = colrClipBoxQuantization
    feaIncludeDir: Optional[str] = None
    skipFeatureCompilation: bool = False
    _tables: Optional[list] = None

    def __post_init__(self):
        self.logger = logging.getLogger("ufo2ft")
        self.timer = Timer(logging.getLogger("ufo2ft.timer"), level=logging.DEBUG)

    def compile(self, ufo):
        with self.timer("preprocess UFO"):
            glyphSet = self.preprocess(ufo)
        with self.timer("compile a basic TTF"):
            font = self.compileOutlines(ufo, glyphSet)
        if self.layerName is None and not self.skipFeatureCompilation:
            self.compileFeatures(ufo, font, glyphSet=glyphSet)
        with self.timer("postprocess TTF"):
            font = self.postprocess(font, ufo, glyphSet)
        return font

    def preprocess(self, ufo_or_ufos):
        self.logger.info("Pre-processing glyphs")
        if self.skipExportGlyphs is None:
            if isinstance(ufo_or_ufos, (list, tuple)):
                self.skipExportGlyphs = set()
                for ufo in ufo_or_ufos:
                    self.skipExportGlyphs.update(
                        ufo.lib.get("public.skipExportGlyphs", [])
                    )
            else:
                self.skipExportGlyphs = ufo_or_ufos.lib.get(
                    "public.skipExportGlyphs", []
                )

        callables = [self.preProcessorClass]
        if hasattr(self.preProcessorClass, "initDefaultFilters"):
            callables.append(self.preProcessorClass.initDefaultFilters)

        preprocessor_args = prune_unknown_kwargs(self.__dict__, *callables)
        # Preprocessors expect this parameter under a different name.
        if hasattr(self, "cubicConversionError"):
            preprocessor_args["conversionError"] = self.cubicConversionError
        preProcessor = self.preProcessorClass(ufo_or_ufos, **preprocessor_args)
        return preProcessor.process()

    def compileOutlines(self, ufo, glyphSet):
        kwargs = prune_unknown_kwargs(self.__dict__, self.outlineCompilerClass)
        kwargs["tables"] = self._tables
        outlineCompiler = self.outlineCompilerClass(ufo, glyphSet=glyphSet, **kwargs)
        return outlineCompiler.compile()

    def postprocess(self, ttf, ufo, glyphSet):
        if self.postProcessorClass is not None:
            postProcessor = self.postProcessorClass(ttf, ufo, glyphSet=glyphSet)
            kwargs = prune_unknown_kwargs(self.__dict__, postProcessor.process)
            ttf = postProcessor.process(**kwargs)
        return ttf

    def compileFeatures(
        self,
        ufo,
        ttFont=None,
        glyphSet=None,
    ):
        """Compile OpenType Layout features from `ufo` into FontTools OTL tables.
        If `ttFont` is None, a new TTFont object is created containing the new
        tables, else the provided `ttFont` is updated with the new tables.

        If no explicit `featureCompilerClass` is provided, the one used will
        depend on whether the ufo contains any MTI feature files in its 'data'
        directory (thus the `MTIFeatureCompiler` is used) or not (then the
        default FeatureCompiler for Adobe FDK features is used).

        If skipExportGlyphs is provided (see description in the ``compile*``
        functions), the feature compiler will prune groups (removing them if empty)
        and kerning of the UFO of these glyphs. The feature file is left untouched.

        `debugFeatureFile` can be a file or file-like object opened in text mode,
        in which to dump the text content of the feature file, useful for debugging
        auto-generated OpenType features like kern, mark, mkmk etc.
        """
        if self.featureCompilerClass is None:
            if any(
                fn.startswith(MTI_FEATURES_PREFIX) and fn.endswith(".mti")
                for fn in ufo.data.fileNames
            ):
                self.featureCompilerClass = MtiFeatureCompiler
            else:
                self.featureCompilerClass = FeatureCompiler

        kwargs = prune_unknown_kwargs(self.__dict__, self.featureCompilerClass)
        featureCompiler = self.featureCompilerClass(
            ufo, ttFont, glyphSet=glyphSet, **kwargs
        )
        otFont = featureCompiler.compile()

        if self.debugFeatureFile:
            if hasattr(featureCompiler, "writeFeatures"):
                featureCompiler.writeFeatures(self.debugFeatureFile)

        return otFont


@dataclass
class BaseInterpolatableCompiler(BaseCompiler):
    variableFontNames: Optional[list] = None
    """Create FontTools TrueType fonts from the DesignSpaceDocument UFO sources
    with interpolatable outlines. Cubic curves are converted compatibly to
    quadratic curves using the Cu2Qu conversion algorithm.

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
    object will contain only a minimum set of tables ("head", "hmtx", "glyf", "loca",
    "maxp", "post" and "vmtx"), and no OpenType layout tables.
    """

    def compile_designspace(self, designSpaceDoc):
        ufos = self._pre_compile_designspace(designSpaceDoc)
        ttfs = self.compile(ufos)
        return self._post_compile_designspace(designSpaceDoc, ttfs)

    def _pre_compile_designspace(self, designSpaceDoc):
        ufos, self.layerNames = [], []
        for source in designSpaceDoc.sources:
            if source.font is None:
                raise AttributeError(
                    "designspace source '%s' is missing required 'font' attribute"
                    % getattr(source, "name", "<Unknown>")
                )
            ufos.append(source.font)
            # 'layerName' is None for the default layer
            self.layerNames.append(source.layerName)

        self.skipExportGlyphs = designSpaceDoc.lib.get("public.skipExportGlyphs", [])

        if self.notdefGlyph is None:
            self.notdefGlyph = _notdefGlyphFallback(designSpaceDoc)

        self.extraSubstitutions = defaultdict(set)
        for rule in designSpaceDoc.rules:
            for left, right in rule.subs:
                self.extraSubstitutions[left].add(right)

        return ufos

    def _post_compile_designspace(self, designSpaceDoc, fonts):
        if self.inplace:
            result = designSpaceDoc
        else:
            result = designSpaceDoc.deepcopyExceptFonts()
        for source, font in zip(result.sources, fonts):
            source.font = font
        return result

    def _compileNeededSources(self, designSpaceDoc):
        # We'll need to map <source> elements to TTFonts, to do so make sure that
        # each <source> has a name.
        ensure_all_sources_have_names(designSpaceDoc)

        # Go through VFs to build and gather list of needed sources to compile
        interpolableSubDocs = [
            subDoc for _location, subDoc in splitInterpolable(designSpaceDoc)
        ]
        vfNameToBaseUfo = {}
        sourcesToCompile = set()
        for subDoc in interpolableSubDocs:
            for vfName, vfDoc in splitVariableFonts(subDoc):
                if (
                    self.variableFontNames is not None
                    and vfName not in self.variableFontNames
                ):
                    # This VF is not needed so we don't need to compile its sources
                    continue
                default_source = vfDoc.findDefault()
                if default_source is None:
                    default_location = location_to_string(vfDoc.newDefaultLocation())
                    master_locations = []
                    for sourceDescriptor in vfDoc.sources:
                        master_location = sourceDescriptor.name + " at "
                        master_location += location_to_string(
                            sourceDescriptor.getFullDesignLocation(vfDoc)
                        )
                        master_locations.append(master_location)
                    master_location_descriptions = "\n".join(master_locations)
                    raise InvalidDesignSpaceData(
                        f"No default source; expected default master at {default_location}."
                        f" Found master locations:\n{master_location_descriptions}"
                    )
                vfNameToBaseUfo[vfName] = default_source.font
                for source in vfDoc.sources:
                    sourcesToCompile.add(source.name)

        # Match sources to compile to their Descriptor in the original designspace
        sourcesByName = {}
        for source in designSpaceDoc.sources:
            if source.name in sourcesToCompile:
                sourcesByName[source.name] = source

        originalSources = {}

        # If the feature files are compatible between the sources, we can save
        # time by building a variable feature file right at the end.
        can_optimize_features = _featuresCompatible(designSpaceDoc)
        if can_optimize_features:
            self.logger.info("Features are compatible across masters; building later")

        originalSources = {}

        # Compile all needed sources in each interpolable subspace to make sure
        # they're all compatible; that also ensures that sub-vfs within the same
        # interpolable sub-space are compatible too.
        for subDoc in interpolableSubDocs:
            # Only keep the sources that we've identified earlier as need-to-compile
            subDoc.sources = [s for s in subDoc.sources if s.name in sourcesToCompile]
            if not subDoc.sources:
                continue

            # FIXME: Hack until we get a fontTools config module. Disable GPOS
            # compaction while building masters because the compaction will be undone
            # anyway by varLib merge and then done again on the VF
            gpos_compact_value = os.environ.pop(GPOS_COMPACT_MODE_ENV_KEY, None)
            save_production_names = self.useProductionNames
            self.useProductionNames = False
            save_postprocessor = self.postProcessorClass
            self.postProcessorClass = None
            self.skipFeatureCompilation = can_optimize_features
            try:
                ttfDesignSpace = self.compile_designspace(subDoc)
            finally:
                if gpos_compact_value is not None:
                    os.environ[GPOS_COMPACT_MODE_ENV_KEY] = gpos_compact_value
            self.postProcessorClass = save_postprocessor
            self.useProductionNames = save_production_names

            # Stick TTFs back into original big DS
            for ttfSource in ttfDesignSpace.sources:
                if can_optimize_features:
                    originalSources[ttfSource.name] = sourcesByName[ttfSource.name].font
                sourcesByName[ttfSource.name].font = ttfSource.font

        return vfNameToBaseUfo, can_optimize_features, originalSources

    def compile_variable(self, designSpaceDoc):
        if not self.inplace:
            designSpaceDoc = designSpaceDoc.deepcopyExceptFonts()

        (
            vfNameToBaseUfo,
            buildVariableFeatures,
            originalSources,
        ) = self._compileNeededSources(designSpaceDoc)

        if not vfNameToBaseUfo:
            return {}

        self.logger.info("Building variable TTF fonts: %s", ", ".join(vfNameToBaseUfo))

        excludeVariationTables = self.excludeVariationTables
        if buildVariableFeatures:
            # Skip generating feature variations in varLib; we are handling
            # the feature variations as part of compiling variable features,
            # which we'll do later, so we don't need to produce them here.
            excludeVariationTables = set(excludeVariationTables) | {"GSUB"}

        with self.timer("merge fonts to variable"):
            vfNameToTTFont = self._merge(designSpaceDoc, excludeVariationTables)

        if buildVariableFeatures:
            self.compile_all_variable_features(
                designSpaceDoc, vfNameToTTFont, originalSources
            )
        for vfName, varfont in list(vfNameToTTFont.items()):
            vfNameToTTFont[vfName] = self.postprocess(
                varfont, vfNameToBaseUfo[vfName], glyphSet=None
            )

        return vfNameToTTFont

    def compile_all_variable_features(
        self, designSpaceDoc, vfNameToTTFont, originalSources, debugFeatureFile=False
    ):
        interpolableSubDocs = [
            subDoc for _location, subDoc in splitInterpolable(designSpaceDoc)
        ]
        for subDoc in interpolableSubDocs:
            for vfName, vfDoc in splitVariableFonts(subDoc):
                if vfName not in vfNameToTTFont:
                    continue
                ttFont = vfNameToTTFont[vfName]
                # vfDoc is now full of TTFs, create a UFO-sourced equivalent
                ufoDoc = vfDoc.deepcopyExceptFonts()
                for ttfSource, ufoSource in zip(vfDoc.sources, ufoDoc.sources):
                    ufoSource.font = originalSources[ttfSource.name]
                self.compile_variable_features(ufoDoc, ttFont)

    def compile_variable_features(self, designSpaceDoc, ttFont):
        default_ufo = designSpaceDoc.findDefault().font

        # Delete anything from the UFO glyphset which didn't make it into the font.
        fontglyphs = ttFont.getGlyphOrder()
        glyphSet = {g.name: g for g in default_ufo if g.name in fontglyphs}

        # Add anything we added to the TTF without telling the UFO
        if ".notdef" not in glyphSet:
            glyphSet[".notdef"] = StubGlyph(".notdef", 0, 0, 0, 0)

        featureCompiler = VariableFeatureCompiler(
            default_ufo, designSpaceDoc, ttFont=ttFont, glyphSet=glyphSet
        )
        featureCompiler.compile()

        if self.debugFeatureFile:
            if hasattr(featureCompiler, "writeFeatures"):
                featureCompiler.writeFeatures(self.debugFeatureFile)

        # Add back feature variations, as the code above would overwrite them.
        designSpaceData = varLib.load_designspace(designSpaceDoc)
        featureTag = designSpaceData.lib.get(
            varLib.FEAVAR_FEATURETAG_LIB_KEY,
            "rclt" if designSpaceData.rulesProcessingLast else "rvrn",
        )
        if designSpaceData.rules:
            varLib._add_GSUB_feature_variations(
                ttFont,
                designSpaceData.axes,
                designSpaceData.internal_axis_supports,
                designSpaceData.rules,
                featureTag,
            )
