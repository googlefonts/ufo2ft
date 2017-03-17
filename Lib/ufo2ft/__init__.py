from __future__ import print_function, division, absolute_import

from ufo2ft.featureCompiler import FeatureCompiler
from ufo2ft.kernFeatureWriter import KernFeatureWriter
from ufo2ft.markFeatureWriter import MarkFeatureWriter
from ufo2ft.outlineCompiler import OutlineOTFCompiler, OutlineTTFCompiler
from ufo2ft.postProcessor import PostProcessor


__version__ = "0.4.0"


def compileOTF(ufo, outlineCompilerClass=OutlineOTFCompiler,
               featureCompilerClass=FeatureCompiler, mtiFeaFiles=None,
               kernWriterClass=KernFeatureWriter, markWriterClass=MarkFeatureWriter,
               glyphOrder=None, useProductionNames=True, optimizeCFF=True,
               roundTolerance=None):
    """Create FontTools CFF font from a UFO.

    *optimizeCFF* sets whether the CFF table should be subroutinized.

    *roundTolerance* (float) controls the rounding of point coordinates.
      It is defined as the maximum absolute difference between the original
      float and the rounded integer value.
      By default, all floats are rounded to integer (tolerance 0.5); a value
      of 0 completely disables rounding; values in between only round floats
      which are close to their integral part within the tolerated range.
    """

    outlineCompiler = outlineCompilerClass(
        ufo, glyphOrder, roundTolerance=roundTolerance)
    otf = outlineCompiler.compile()

    featureCompiler = featureCompilerClass(
        ufo, otf, kernWriterClass=kernWriterClass, markWriterClass=markWriterClass,
        mtiFeaFiles=mtiFeaFiles)
    featureCompiler.compile()

    postProcessor = PostProcessor(otf, ufo)
    otf = postProcessor.process(useProductionNames, optimizeCFF)

    return otf


def compileTTF(ufo, outlineCompilerClass=OutlineTTFCompiler,
               featureCompilerClass=FeatureCompiler, mtiFeaFiles=None,
               kernWriterClass=KernFeatureWriter, markWriterClass=MarkFeatureWriter,
               glyphOrder=None, useProductionNames=True,
               convertCubics=True, cubicConversionError=2):
    """Create FontTools TrueType font from a UFO.

    *convertCubics* and *cubicConversionError* specify how the conversion from cubic
    to quadratic curves should be handled.
    """

    outlineCompiler = outlineCompilerClass(
        ufo, glyphOrder, convertCubics, cubicConversionError)
    otf = outlineCompiler.compile()

    featureCompiler = featureCompilerClass(
        ufo, otf, kernWriterClass=kernWriterClass, markWriterClass=markWriterClass,
        mtiFeaFiles=mtiFeaFiles)
    featureCompiler.compile()

    postProcessor = PostProcessor(otf, ufo)
    otf = postProcessor.process(useProductionNames)

    return otf
