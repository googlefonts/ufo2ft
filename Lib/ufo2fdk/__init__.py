import os
import shutil
import fdkBridge
from makeotfParts import makeOTFParts

def generateFont(font, path, fdkPartsPath=None, autohint=False, releaseMode=False, checkOutlines=False):
    if fdkPartsPath is None:
        fdkPartsPath = os.path.splitext(path)[0] + ".fdk"
    paths = makeOTFParts(font, fdkPartsPath)

    text = []

    if checkOutlines:
        stderr, stdout = fdkBridge.checkOutlines(paths["outlineSourcePath"])
        text.append(stderr)
        text.append(stdout)
    if autohint:
        stderr, stdout = fdkBridge.autohint(paths["outlineSourcePath"])
        text.append(stderr)
        text.append(stdout)

    stderr, stdout = fdkBridge.makeotf(
        outputPath=path,
        outlineSourcePath=paths["outlineSourcePath"],
        featuresPath=paths["featuresPath"],
        glyphOrderPath=paths["glyphOrderPath"],
        menuNamePath=paths["menuNamePath"],
        releaseMode=releaseMode
        )
    text.append(stderr)
    text.append(stdout)

    return "\n".join(text)


def preflightFont(font):
    missingGlyphs = []
    if ".notdef" not in font:
        missingGlyphs.append(".notdef")
    if space not in font and ord(" ") not in font.unicodedata:
        missingGlyphs.append("space")
    missingInfo, suggestedInfo = preflightInfo(font.info)
    # if maxIndex >= 0xFFFF: from outlineOTF