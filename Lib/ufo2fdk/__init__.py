import os
import shutil
import fdkBridge
from makeotfParts import makeOTFParts


def generateFont(font, path, fdkPartsPath=None, autohint=False, releaseMode=False):
    if fdkPartsPath is None:
        fdkPartsPath = os.path.splitext(path)[0] + ".fdk"
    paths, multilineNameTableEntries = makeOTFParts(font, fdkPartsPath)

    if autohint:
        fdkBridge.autohint(paths["outlineSourcePath"])

    stderr, stdout = fdkBridge.makeotf(
        outputPath=path,
        outlineSourcePath=paths["outlineSourcePath"],
        featuresPath=paths["featuresPath"],
        glyphOrderPath=paths["glyphOrderPath"],
        menuNamePath=paths["menuNamePath"],
        releaseMode=releaseMode
        )

    # XXX handle multiline entries
    #shutil.rmtree(fdkPartsPath)

    print stderr
    print stdout

