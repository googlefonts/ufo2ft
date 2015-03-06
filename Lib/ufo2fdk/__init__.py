import os
import shutil
import tempfile
import fdkBridge
from fdkBridge import haveFDK
from makeotfParts import MakeOTFPartsCompiler
from outlineOTF import OutlineOTFCompiler


__all__ = [
    "haveFDK",
    "OTFCompiler",
    "version"
]

version = "0.1"


#def preflightFont(font):
#    missingGlyphs = []
#    if ".notdef" not in font:
#        missingGlyphs.append(".notdef")
#    if space not in font and ord(" ") not in font.unicodedata:
#        missingGlyphs.append("space")
#    missingInfo, suggestedInfo = preflightInfo(font.info)
#    # if maxIndex >= 0xFFFF: from outlineOTF


class OTFCompiler(object):

    """
    This object will create an OTF from a UFO. When creating this object,
    there are three optional arguments:

    +------------------------+------------------------------------------------------------+
    | *savePartsNextToUFO*   | This will cause the compilation of parts for the           |
    |                        | FDK to occur at *yourUFOName.fdk*. Use this with           |
    |                        | caution, as an existing file at that location will         |
    |                        | be overwritten.                                            |
    +------------------------+------------------------------------------------------------+
    | *partsCompilerClass*   | This will override the default parts compiler,             |
    |                        | :class:`ufo2fdk.tools.makeotfParts.MakeOTFPartsCompiler`.  |
    +------------------------+------------------------------------------------------------+
    | *outlineCompilerClass* | This will override the default parts compiler,             |
    |                        | :class:`ufo2fdk.tools.outlineOTF.OutlineOTFCompiler`.      |
    +------------------------+------------------------------------------------------------+
    """

    def __init__(self, savePartsNextToUFO=False, partsCompilerClass=MakeOTFPartsCompiler, outlineCompilerClass=OutlineOTFCompiler):
        self.savePartsNextToUFO = savePartsNextToUFO
        self.partsCompilerClass = partsCompilerClass
        self.outlineCompilerClass = outlineCompilerClass

    def compile(self, font, path, checkOutlines=False, autohint=False, releaseMode=False, features=None, glyphOrder=None, progressBar=None):
        """
        This method will write *font* into an OTF-CFF at *path*.
        If *checkOutlines* is True, the checkOutlines program
        will be run on the font. If *autohint* is True, the
        autohint program will be run on the font. If *releaseMode*
        is True, makeotf will be told to compile the font in
        release mode. A custom feature file may be used instead of
        that of the UFO in *features*. An optional list of glyph names
        in *glyphOrder* will specifiy the order of glyphs in the font.
        If provided, *progressBar* should be an object that has an
        *update* method.

        When this method is finished, it will return a dictionary
        containing reports from the run programs. The keys
        are as follows:

        * makeotf
        * checkOutlines
        * autohint
        """
        # get the path for the parts
        if self.savePartsNextToUFO:
            partsPath = os.path.splitext(font.path)[0] + ".fdk"
        else:
            partsPath = tempfile.mkdtemp()
        # make report storage
        report = dict(parts=None, makeotf=None, checkOutlines=None, autohint=None)
        # do the compile
        try:
            # make the parts
            if progressBar is not None:
                progressBar.update("Preparing...")
            partsCompiler = self.partsCompilerClass(font, partsPath, features=features, glyphOrder=glyphOrder, outlineCompilerClass=self.outlineCompilerClass)
            partsCompiler.compile()
            report["parts"] = "\n".join(partsCompiler.log)
            # checkOutlines
            if checkOutlines:
                if progressBar is not None:
                    progressBar.update("Removing overlap...")
                stderr, stdout = fdkBridge.checkOutlines(partsCompiler.paths["outlineSource"])
                ## replace the temp names in the report.
                if not self.savePartsNextToUFO:
                    stderr = stderr.replace(partsPath, "")
                    stderr = stderr.replace(partsPath + "/", "")
                    stdout = stdout.replace(partsPath, "")
                    stdout = stdout.replace(partsPath + "/", "")
                report["checkOutlines"] = "\n".join((stdout, stderr))
            # autohint
            if autohint:
                if progressBar is not None:
                    progressBar.update("Autohinting...")
                stderr, stdout = fdkBridge.autohint(partsCompiler.paths["outlineSource"])
                ## replace the temp names in the report.
                if not self.savePartsNextToUFO:
                    stderr = stderr.replace(partsPath, "")
                    stderr = stderr.replace(partsPath + "/", "")
                    stdout = stdout.replace(partsPath, "")
                    stdout = stdout.replace(partsPath + "/", "")
                report["autohint"] = "\n".join((stdout, stderr))
            # makeotf
            if progressBar is not None:
                progressBar.update("Compiling...")
            ## make a temp location for makeotf to compile to.
            ## it gets confused by the various directories,
            ## so compile into the parts directory. it will
            ## be moved later.
            tempFontPath = os.path.join(partsPath, "compile.otf")
            stderr, stdout = fdkBridge.makeotf(
                outputPath=tempFontPath,
                outlineSourcePath=partsCompiler.paths["outlineSource"],
                featuresPath=partsCompiler.paths["features"],
                glyphOrderPath=partsCompiler.paths["glyphOrder"],
                menuNamePath=partsCompiler.paths["menuName"],
                fontInfoPath=partsCompiler.paths["fontInfo"],
                releaseMode=releaseMode
                )
            ## replace the temp names in the report.
            stderr = stderr.replace("compile.otf", os.path.basename(path))
            stdout = stdout.replace("compile.otf", os.path.basename(path))
            stderr = stderr.replace(tempFontPath, path)
            stdout = stdout.replace(tempFontPath, path)
            stderr = stderr.replace(os.path.basename(tempFontPath), os.path.basename(path))
            stdout = stdout.replace(os.path.basename(tempFontPath), os.path.basename(path))
            if not self.savePartsNextToUFO:
                stderr = stderr.replace(partsPath, "")
                stderr = stderr.replace(partsPath + "/", "")
                stdout = stdout.replace(partsPath, "")
                stdout = stdout.replace(partsPath + "/", "")
            ## copy the result from the temp location
            if os.path.exists(tempFontPath):
                shutil.copy(tempFontPath, path)
            report["makeotf"] = "\n".join((stdout, stderr))
            if progressBar is not None:
                progressBar.update("Finishing...")
        # destroy the temp directory
        finally:
            if not self.savePartsNextToUFO and os.path.exists(partsPath):
                shutil.rmtree(partsPath)
        # return the report
        return report
