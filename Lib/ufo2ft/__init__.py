from ufo2ft._compilers.interpolatableOTFCompiler import InterpolatableOTFCompiler
from ufo2ft._compilers.interpolatableTTFCompiler import InterpolatableTTFCompiler
from ufo2ft._compilers.otfCompiler import OTFCompiler
from ufo2ft._compilers.ttfCompiler import TTFCompiler
from ufo2ft._compilers.variableCFF2sCompiler import VariableCFF2sCompiler
from ufo2ft._compilers.variableTTFsCompiler import VariableTTFsCompiler
from ufo2ft.constants import CFFOptimization  # noqa: F401 (fontmake uses it)


def compileTTF(ufo, **kwargs):
    return TTFCompiler(**kwargs).compile(ufo)


def compileOTF(ufo, **kwargs):
    return OTFCompiler(**kwargs).compile(ufo)


def compileInterpolatableTTFs(ufos, **kwargs):
    return InterpolatableTTFCompiler(**kwargs).compile(ufos)


def compileVariableTTFs(designSpaceDoc, **kwargs):
    return VariableTTFsCompiler(**kwargs).compile_variable(designSpaceDoc)


def compileInterpolatableTTFsFromDS(designSpaceDoc, **kwargs):
    return InterpolatableTTFCompiler(**kwargs).compile_designspace(designSpaceDoc)


def compileInterpolatableOTFsFromDS(designSpaceDoc, **kwargs):
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
    return VariableCFF2sCompiler(**kwargs).compile_variable(designSpaceDoc)
