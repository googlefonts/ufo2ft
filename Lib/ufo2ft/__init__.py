from __future__ import print_function, division, absolute_import
from .kernFeatureWriter import KernFeatureWriter
from .makeotfParts import FeatureOTFCompiler
from .markFeatureWriter import MarkFeatureWriter
from .outlineOTF import OutlineOTFCompiler, OutlineTTFCompiler


def compile(font, outlineCompilerClass, featureCompilerClass,
            kernWriter, markWriter):
    """Create FontTools TTFonts from a UFO."""

    outlineCompiler = outlineCompilerClass(font)
    outline = outlineCompiler.compile()

    featureCompiler = featureCompilerClass(
        font, outline, kernWriter=kernWriter, markWriter=markWriter)
    feasrc = featureCompiler.compile()
    for table in ['GPOS', 'GSUB']:
        if table in feasrc:
            outline[table] = feasrc[table]

    return outline


def compileOTF(font, outlineCompilerClass=OutlineOTFCompiler,
               featureCompilerClass=FeatureOTFCompiler,
               kernWriter=KernFeatureWriter, markWriter=MarkFeatureWriter):
    """Create FontTools CFF font from a UFO."""

    return compile(font, outlineCompilerClass, featureCompilerClass,
                   kernWriter, markWriter)


def compileTTF(font, outlineCompilerClass=OutlineTTFCompiler,
               featureCompilerClass=FeatureOTFCompiler,
               kernWriter=KernFeatureWriter, markWriter=MarkFeatureWriter):
    """Create FontTools TrueType font from a UFO."""

    return compile(font, outlineCompilerClass, featureCompilerClass,
                   kernWriter, markWriter)
