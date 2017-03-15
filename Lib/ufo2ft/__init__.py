from __future__ import print_function, division, absolute_import

from ufo2ft.featuresCompiler import FeaturesCompiler
from ufo2ft.kernFeatureWriter import KernFeatureWriter
from ufo2ft.markFeatureWriter import MarkFeatureWriter
from ufo2ft.outlineCompiler import OutlineOTFCompiler, OutlineTTFCompiler
from ufo2ft.postProcessor import PostProcessor


__version__ = "0.3.5.dev0"


def compileOTF(ufo, outlineCompilerClass=OutlineOTFCompiler,
               featuresCompilerClass=FeaturesCompiler, mtiFeaFiles=None,
               kernWriterClass=KernFeatureWriter, markWriterClass=MarkFeatureWriter,
               glyphOrder=None, convertCubics=True, cubicConversionError=2,
               useProductionNames=True, optimizeCFF=True):
    """Create FontTools CFF font from a UFO.

    Some arguments are only used when generating CFF or TrueType outlines:
    `convertCubics` and `cubicConversionError` only apply to TrueType, and
    `optimizeCff` only applies to CFF.
    """

    outlineCompiler = outlineCompilerClass(
        ufo, glyphOrder, convertCubics, cubicConversionError)
    otf = outlineCompiler.compile()

    featuresCompiler = featuresCompilerClass(
        ufo, otf, kernWriterClass=kernWriterClass, markWriterClass=markWriterClass,
        mtiFeaFiles=mtiFeaFiles)
    featuresCompiler.compile()

    postProcessor = PostProcessor(otf, ufo)
    otf = postProcessor.process(useProductionNames, optimizeCFF)

    return otf


def compileTTF(ufo, outlineCompilerClass=OutlineTTFCompiler, **kwargs):
    """Create FontTools TrueType font from a UFO."""

    return compileOTF(ufo, outlineCompilerClass=outlineCompilerClass, **kwargs)
