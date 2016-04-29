from __future__ import print_function, division, absolute_import

from ufo2ft.kernFeatureWriter import KernFeatureWriter
from ufo2ft.makeotfParts import FeatureOTFCompiler
from ufo2ft.markFeatureWriter import MarkFeatureWriter
from ufo2ft.otfPostProcessor import OTFPostProcessor
from ufo2ft.outlineOTF import OutlineOTFCompiler, OutlineTTFCompiler


def compileOTF(ufo, outlineCompilerClass=OutlineOTFCompiler,
               featureCompilerClass=FeatureOTFCompiler, mtiFeaFiles=None,
               kernWriter=KernFeatureWriter, markWriter=MarkFeatureWriter,
               glyphOrder=None, useProductionNames=True, optimizeCff=True):
    """Create FontTools CFF font from a UFO."""

    outlineCompiler = outlineCompilerClass(ufo, glyphOrder=glyphOrder)
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
