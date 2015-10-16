from makeotfParts import FeatureOTFCompiler
from outlineOTF import OutlineOTFCompiler, OutlineTTFCompiler


def compile(font, outlineCompilerClass, featureCompilerClass):
    """Create FontTools TTFonts from a UFO."""

    outlineCompiler = outlineCompilerClass(font)
    outline = outlineCompiler.compile()

    featureCompiler = featureCompilerClass(font, outline)
    feasrc = featureCompiler.compile()
    for table in ['GPOS', 'GSUB']:
        outline[table] = feasrc[table]

    return outline


def compileOTF(font, outlineCompilerClass=OutlineOTFCompiler,
               featureCompilerClass=FeatureOTFCompiler):
    """Create FontTools CFF font from a UFO."""

    return compile(font, outlineCompilerClass, featureCompilerClass)


def compileTTF(font, outlineCompilerClass=OutlineTTFCompiler,
               featureCompilerClass=FeatureOTFCompiler):
    """Create FontTools TrueType font from a UFO."""

    return compile(font, outlineCompilerClass, featureCompilerClass)
