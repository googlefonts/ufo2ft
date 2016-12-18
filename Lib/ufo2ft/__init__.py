from __future__ import print_function, division, absolute_import

from ufo2ft.kernFeatureWriter import KernFeatureWriter
from ufo2ft.makeotfParts import FeatureOTFCompiler
from ufo2ft.markFeatureWriter import MarkFeatureWriter
from ufo2ft.otfPostProcessor import OTFPostProcessor
from ufo2ft.outlineOTF import OutlineOTFCompiler, OutlineTTFCompiler


__version__ = "0.3.1"


def compileOTF(ufo, outlineCompilerClass=OutlineOTFCompiler,
               featureCompilerClass=FeatureOTFCompiler, mtiFeaFiles=None,
               kernWriter=KernFeatureWriter, markWriter=MarkFeatureWriter,
               glyphOrder=None, convertCubics=True, cubicConversionError=2,
               useProductionNames=True, optimizeCff=True):
    """Create FontTools CFF font from a UFO.

    Some arguments are only used when generating CFF or TrueType outlines:
    `convertCubics` and `cubicConversionError` only apply to TrueType, and
    `optimizeCff` only applies to CFF.
    """

    outlineCompiler = outlineCompilerClass(
        ufo, glyphOrder, convertCubics, cubicConversionError)
    otf = outlineCompiler.compile()

    featureCompiler = featureCompilerClass(
        ufo, otf, kernWriter, markWriter, mtiFeaFiles=mtiFeaFiles)
    featureCompiler.compile()

    postProcessor = OTFPostProcessor(otf, ufo)
    otf = postProcessor.process(useProductionNames, optimizeCff)

    return otf


def compileTTF(ufo, outlineCompilerClass=OutlineTTFCompiler, **kwargs):
    """Create FontTools TrueType font from a UFO."""

    return compileOTF(ufo, outlineCompilerClass=outlineCompilerClass, **kwargs)
