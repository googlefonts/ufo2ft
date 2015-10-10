from makeotfParts import MakeOTFPartsCompiler
from outlineOTF import OutlineOTFCompiler, OutlineTTFCompiler


class UFOCompiler:
    """Creates an OpenType font from a UFO."""

    def compile(self, font, path):
        """Writes font into an OTF-CFF/TTF at path."""

        partsCompiler = self.partsCompilerClass(
            font, path, self.outlineCompilerClass)
        partsCompiler.compile()


class OTFCompiler(UFOCompiler):
    def __init__(self, partsCompilerClass=MakeOTFPartsCompiler,
                 outlineCompilerClass=OutlineOTFCompiler):
        self.partsCompilerClass = partsCompilerClass
        self.outlineCompilerClass = outlineCompilerClass


class TTFCompiler(UFOCompiler):
    def __init__(self, partsCompilerClass=MakeOTFPartsCompiler,
                 outlineCompilerClass=OutlineTTFCompiler):
        self.partsCompilerClass = partsCompilerClass
        self.outlineCompilerClass = outlineCompilerClass
