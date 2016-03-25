from __future__ import print_function, division, absolute_import

from ufo2ft.kernFeatureWriter import KernFeatureWriter
from ufo2ft.makeotfParts import FeatureOTFCompiler
from ufo2ft.markFeatureWriter import MarkFeatureWriter
from ufo2ft.outlineOTF import OutlineOTFCompiler, OutlineTTFCompiler


def compileOTF(font, glyphOrder=None, outlineCompilerClass=OutlineOTFCompiler,
               featureCompilerClass=FeatureOTFCompiler, mtiFeaFiles=None,
               kernWriter=KernFeatureWriter, markWriter=MarkFeatureWriter):
    """Create FontTools CFF font from a UFO."""

    outlineCompiler = outlineCompilerClass(font, glyphOrder=glyphOrder)
    outline = outlineCompiler.compile()

    featureCompiler = featureCompilerClass(
        font, outline, kernWriter, markWriter, mtiFeaFiles=mtiFeaFiles)
    featureCompiler.compile()

    return outline


def compileTTF(font, outlineCompilerClass=OutlineTTFCompiler, **kwargs):
    """Create FontTools TrueType font from a UFO."""

    return compileOTF(font, outlineCompilerClass=outlineCompilerClass, **kwargs)
