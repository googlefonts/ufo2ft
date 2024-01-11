from ufo2ft._compilers.interpolatableOTFCompiler import InterpolatableOTFCompiler
from ufo2ft._compilers.interpolatableTTFCompiler import InterpolatableTTFCompiler
from ufo2ft._compilers.otfCompiler import OTFCompiler
from ufo2ft._compilers.ttfCompiler import TTFCompiler
from ufo2ft._compilers.variableCFF2sCompiler import VariableCFF2sCompiler
from ufo2ft._compilers.variableTTFsCompiler import VariableTTFsCompiler
from ufo2ft.constants import CFFOptimization  # noqa: F401 (fontmake uses it)

__all__ = [
    "compileTTF",
    "compileOTF",
    "compileInterpolatableTTFs",
    "compileVariableTTFs",
    "compileInterpolatableTTFsFromDS",
    "compileInterpolatableOTFsFromDS",
    "compileVariableTTF",
    "compileVariableCFF2",
    "compileVariableCFF2s",
]

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "0.0.0+unknown"


def compileTTF(ufo, **kwargs):
    """Create FontTools TrueType font from a UFO.

    *removeOverlaps* performs a union operation on all the glyphs' contours.

    *flattenComponents* un-nests glyphs so that they have at most one level of
    components.

    *convertCubics* and *cubicConversionError* specify how the conversion from cubic
    to quadratic curves should be handled.

    *layerName* specifies which layer should be compiled. When compiling something
    other than the default layer, feature compilation is skipped.

    *skipExportGlyphs* is a list or set of glyph names to not be exported to the
    final font. If these glyphs are used as components in any other glyph, those
    components get decomposed. If the parameter is not passed in, the UFO's
    "public.skipExportGlyphs" lib key will be consulted. If it doesn't exist,
    all glyphs are exported. UFO groups and kerning will be pruned of skipped
    glyphs.

    *dropImpliedOnCurves* (bool) specifies whether on-curve points that are exactly
    in between two off-curves can be dropped when building glyphs (default: False).

    *allQuadratic* (bool) specifies whether to convert all curves to quadratic - True
    by default, builds traditional glyf v0 table. If False, quadratic curves or cubic
    curves are generated depending on which has fewer points; a glyf v1 is generated.
    """
    return TTFCompiler(**kwargs).compile(ufo)


def compileOTF(ufo, **kwargs):
    """Create FontTools CFF font from a UFO.

    *removeOverlaps* performs a union operation on all the glyphs' contours.

    *optimizeCFF* (int) defines whether the CFF charstrings should be
      specialized and subroutinized. By default both optimization are enabled.
      A value of 0 disables both; 1 only enables the specialization; 2 (default)
      does both specialization and subroutinization.

    *roundTolerance* (float) controls the rounding of point coordinates.
      It is defined as the maximum absolute difference between the original
      float and the rounded integer value.
      By default, all floats are rounded to integer (tolerance 0.5); a value
      of 0 completely disables rounding; values in between only round floats
      which are close to their integral part within the tolerated range.

    *featureWriters* argument is a list of BaseFeatureWriter subclasses or
      pre-initialized instances. Features will be written by each feature
      writer in the given order. If featureWriters is None, the default
      feature writers [KernFeatureWriter, MarkFeatureWriter] are used.

    *filters* argument is a list of BaseFilters subclasses or pre-initialized
      instances. Filters with 'pre' attribute set to True will be pre-filters
      called before the default filters, otherwise they will be post-filters,
      called after the default filters.
      Filters will modify glyphs or the glyph set. The default filters cannot
      be disabled.

    *useProductionNames* renames glyphs in TrueType 'post' or OpenType 'CFF '
      tables based on the 'public.postscriptNames' mapping in the UFO lib,
      if present. Otherwise, uniXXXX names are generated from the glyphs'
      unicode values. The default value (None) will first check if the UFO lib
      has the 'com.github.googlei18n.ufo2ft.useProductionNames' key. If this
      is missing or True (default), the glyphs are renamed. Set to False
      to keep the original names.

    **inplace** (bool) specifies whether the filters should modify the input
      UFO's glyphs, a copy should be made first.

    *layerName* specifies which layer should be compiled. When compiling something
    other than the default layer, feature compilation is skipped.

    *skipExportGlyphs* is a list or set of glyph names to not be exported to the
    final font. If these glyphs are used as components in any other glyph, those
    components get decomposed. If the parameter is not passed in, the UFO's
    "public.skipExportGlyphs" lib key will be consulted. If it doesn't exist,
    all glyphs are exported. UFO groups and kerning will be pruned of skipped
    glyphs.

    *cffVersion* (int) is the CFF format, choose between 1 (default) and 2.

    *subroutinizer* (Optional[str]) is the name of the library to use for
      compressing CFF charstrings, if subroutinization is enabled by optimizeCFF
      parameter. Choose between "cffsubr" or "compreffor".
      By default "cffsubr" is used for both CFF 1 and CFF 2.
      NOTE: cffsubr is required for subroutinizing CFF2 tables, as compreffor
      currently doesn't support it.
    """
    return OTFCompiler(**kwargs).compile(ufo)


def compileInterpolatableTTFs(ufos, **kwargs):
    """Create FontTools TrueType fonts from a list of UFOs with interpolatable
    outlines. Cubic curves are converted compatibly to quadratic curves using
    the Cu2Qu conversion algorithm.

    Return an iterator object that yields a TTFont instance for each UFO.

    *layerNames* refers to the layer names to use glyphs from in the order of
    the UFOs in *ufos*. By default, this is a list of `[None]` times the number
    of UFOs, i.e. using the default layer from all the UFOs.

    When the layerName is not None for a given UFO, the corresponding TTFont object
    will contain only a minimum set of tables ("head", "hmtx", "glyf", "loca", "maxp",
    "post" and "vmtx"), and no OpenType layout tables.

    *skipExportGlyphs* is a list or set of glyph names to not be exported to the
    final font. If these glyphs are used as components in any other glyph, those
    components get decomposed. If the parameter is not passed in, the union of
    all UFO's "public.skipExportGlyphs" lib keys will be used. If they don't
    exist, all glyphs are exported. UFO groups and kerning will be pruned of
    skipped glyphs.
    """
    return InterpolatableTTFCompiler(**kwargs).compile(ufos)


def compileVariableTTFs(designSpaceDoc, **kwargs):
    """Create FontTools TrueType variable fonts for each variable font defined
    in the given DesignSpaceDocument, using their UFO sources
    with interpolatable outlines, using fontTools.varLib.build.

    *optimizeGvar*, if set to False, will not perform IUP optimization on the
      generated 'gvar' table.

    *excludeVariationTables* is a list of sfnt table tags (str) that is passed on
      to fontTools.varLib.build, to skip building some variation tables.

    *variableFontNames* is an optional list of names of variable fonts
      to build. If not provided, all variable fonts listed in the given
      designspace will by built.

    *allQuadratic* (bool) specifies whether to convert all curves to quadratic - True
      by default, builds traditional glyf v0 table. If False, quadratic curves or cubic
      curves are generated depending on which has fewer points; a glyf v1 is generated.

    The rest of the arguments works the same as in the other compile functions.

    Returns a dictionary that maps each variable font filename to a new variable
    TTFont object. If no variable fonts are defined in the Designspace, returns
    an empty dictionary.

    .. versionadded:: 2.28.0
    """
    return VariableTTFsCompiler(**kwargs).compile_variable(designSpaceDoc)


def compileInterpolatableTTFsFromDS(designSpaceDoc, **kwargs):
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
    return InterpolatableTTFCompiler(**kwargs).compile_designspace(designSpaceDoc)


def compileInterpolatableOTFsFromDS(designSpaceDoc, **kwargs):
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
    return InterpolatableOTFCompiler(**kwargs).compile_designspace(designSpaceDoc)


def compileVariableTTF(designSpaceDoc, **kwargs):
    """Create FontTools TrueType variable font from the DesignSpaceDocument UFO sources
    with interpolatable outlines, using fontTools.varLib.build.

    *optimizeGvar*, if set to False, will not perform IUP optimization on the
      generated 'gvar' table.

    *excludeVariationTables* is a list of sfnt table tags (str) that is passed on
      to fontTools.varLib.build, to skip building some variation tables.

    The rest of the arguments works the same as in the other compile functions.

    Returns a new variable TTFont object.
    """
    fonts = VariableTTFsCompiler(**kwargs).compile_variable(designSpaceDoc)
    if len(fonts) != 1:
        raise ValueError(
            "Tried to build a DesignSpace version 5 with multiple variable "
            "fonts using the old ufo2ft API `compileVariableTTF`. "
            "Use the new API instead `compileVariableTTFs`"
        )
    return next(iter(fonts.values()))


def compileVariableCFF2(designSpaceDoc, **kwargs):
    fonts = VariableCFF2sCompiler(**kwargs).compile_variable(designSpaceDoc)
    if len(fonts) != 1:
        raise ValueError(
            "Tried to build a DesignSpace version 5 with multiple variable "
            "fonts using the old ufo2ft API `compileVariableCFF2`. "
            "Use the new API instead `compileVariableCFF2s`"
        )
    return next(iter(fonts.values()))


def compileVariableCFF2s(designSpaceDoc, **kwargs):
    """Create FontTools TrueType variable fonts for each variable font defined
    in the given DesignSpaceDocument, using their UFO sources
    with interpolatable outlines, using fontTools.varLib.build.

    *optimizeGvar*, if set to False, will not perform IUP optimization on the
      generated 'gvar' table.

    *excludeVariationTables* is a list of sfnt table tags (str) that is passed on
      to fontTools.varLib.build, to skip building some variation tables.

    *variableFontNames* is an optional list of names of variable fonts
      to build. If not provided, all variable fonts listed in the given
      designspace will by built.

    *allQuadratic* (bool) specifies whether to convert all curves to quadratic - True
      by default, builds traditional glyf v0 table. If False, quadratic curves or cubic
      curves are generated depending on which has fewer points; a glyf v1 is generated.

    The rest of the arguments works the same as in the other compile functions.

    Returns a dictionary that maps each variable font filename to a new variable
    TTFont object. If no variable fonts are defined in the Designspace, returns
    an empty dictionary.

    .. versionadded:: 2.28.0
    """
    return VariableCFF2sCompiler(**kwargs).compile_variable(designSpaceDoc)
