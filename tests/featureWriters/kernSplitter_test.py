from typing import Any

import py
from fontTools.designspaceLib import DesignSpaceDocument

from ufo2ft.featureCompiler import parseLayoutFeatures
from ufo2ft.featureWriters.kernFeatureWriter import (
    KernFeatureWriter,
    script_extensions_for_codepoint,
)
from ufo2ft.featureWriters.kernSplitter import getAndSplitKerningData
from ufo2ft.util import classifyGlyphs


def test_splitting_kerning_data(datadir: py.path.local, FontClass: Any) -> None:
    testdata_dir = datadir.join("Mystery")
    ds = DesignSpaceDocument.fromfile(testdata_dir.join("Mystery.designspace"))
    ufo = FontClass(testdata_dir.join("Mystery-Regular.ufo"))

    kern_writer = KernFeatureWriter()
    feaFile = parseLayoutFeatures(ufo)
    kern_writer.setContext(ufo, feaFile)
    side1Classes, side2Classes = kern_writer.getKerningClasses(ufo, feaFile)

    cmap = kern_writer.makeUnicodeToGlyphNameMapping()
    gsub = kern_writer.compileGSUB()
    scriptGlyphs = classifyGlyphs(script_extensions_for_codepoint, cmap, gsub)

    glyphScripts = {}
    for script, glyphs in scriptGlyphs.items():
        for g in glyphs:
            glyphScripts.setdefault(g, set()).add(script)
    for rule in ds.rules:
        for source, target in rule.subs:
            if source in glyphScripts:
                glyphScripts[target] = glyphScripts[source]

    kerning = ufo.kerning
    glyphSet = ufo.keys()
    kern_data = getAndSplitKerningData(
        kerning, side1Classes, side2Classes, glyphSet, glyphScripts
    )
    import pprint

    with open("kerndata.txt", "w") as f:
        pprint.pprint(kern_data, stream=f)
