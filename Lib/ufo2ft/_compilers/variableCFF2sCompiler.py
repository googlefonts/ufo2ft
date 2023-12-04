from dataclasses import dataclass
from typing import Type

from ufo2ft.constants import CFFOptimization
from ufo2ft.outlineCompiler import OutlineOTFCompiler
from ufo2ft.preProcessor import OTFPreProcessor

from .interpolatableOTFCompiler import InterpolatableOTFCompiler


@dataclass
class VariableCFF2sCompiler(InterpolatableOTFCompiler):
    preProcessorClass: Type = OTFPreProcessor
    outlineCompilerClass: Type = OutlineOTFCompiler
    roundTolerance: float = None
    colrAutoClipBoxes: bool = False
    cffVersion: int = 2
    # This should probably be SPECIALIZE, but our tests expect no optimization!
    optimizeCFF: CFFOptimization = CFFOptimization.NONE
    excludeVariationTables: tuple = ()
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