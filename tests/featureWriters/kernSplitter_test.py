import pprint
from typing import Any

import py
from fontTools.designspaceLib import DesignSpaceDocument

from ufo2ft.featureCompiler import parseLayoutFeatures
from ufo2ft.featureWriters.kernFeatureWriter import (
    KernFeatureWriter,
    KerningPair,
    script_extensions_for_codepoint,
    unicodeBidiType,
)
from ufo2ft.featureWriters.kernSplitter import (
    get_and_split_kerning_data,
    getAndSplitKerningData,
    make_feature_blocks,
    make_lookups,
)
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

    with open("kerndata.txt", "w") as f:
        pprint.pprint(kern_data, stream=f)


def test_split_kerning_groups(datadir: py.path.local, FontClass: Any) -> None:
    testdata_dir = datadir.join("Mystery")
    ds = DesignSpaceDocument.fromfile(testdata_dir.join("Mystery.designspace"))
    ufo = FontClass(testdata_dir.join("Mystery-Regular.ufo"))

    kern_writer = KernFeatureWriter()
    feaFile = parseLayoutFeatures(ufo)
    kern_writer.setContext(ufo, feaFile)
    cmap = kern_writer.makeUnicodeToGlyphNameMapping()
    gsub = kern_writer.compileGSUB()
    scriptGlyphs = classifyGlyphs(script_extensions_for_codepoint, cmap, gsub)
    glyphScripts: dict[str, set[str]] = {}
    for script, glyphs in scriptGlyphs.items():
        for g in glyphs:
            glyphScripts.setdefault(g, set()).add(script)
    for rule in ds.rules:
        for source, target in rule.subs:
            if source in glyphScripts:
                glyphScripts.setdefault(target, set()).update(glyphScripts[source])
    bidiGlyphs = classifyGlyphs(unicodeBidiType, cmap, gsub)
    glyphBidis: dict[str, set[str]] = {}
    for script, glyphs in bidiGlyphs.items():
        for g in glyphs:
            glyphBidis.setdefault(g, set()).add(script)
    for rule in ds.rules:
        for source, target in rule.subs:
            if source in glyphBidis:
                glyphBidis.setdefault(target, set()).update(glyphBidis[source])

    pairs_by_script = get_and_split_kerning_data(
        ufo.kerning, ufo.groups, ufo.keys(), glyphScripts
    )
    lookups = make_lookups(pairs_by_script, glyphBidis, quantization=1)
    feature_blocks = make_feature_blocks(
        feaFile, lookups, make_kern=True, make_dist=True
    )

    with open("debug.fea", "w") as f:
        for block in feature_blocks.values():
            f.write(block.asFea())


def test_weird_split() -> None:
    groups = {
        "public.kern1.V": "V Vdotbelow Vtilde Izhitsa-cy".split(),
        "public.kern2.H.sc": "bdotaccent.sc bdotbelow.sc blinebelow.sc d.sc eth.sc dcaron.sc dcedilla.sc dcircumflexbelow.sc dcroat.sc ddotaccent.sc ddotbelow.sc dlinebelow.sc e.sc eacute.sc ebreve.sc ecaron.sc ecedilla.sc ecedillabreve.sc ecircumflex.sc ecircumflexacute.sc ecircumflexbelow.sc ecircumflexdotbelow.sc ecircumflexgrave.sc ecircumflexhookabove.sc ecircumflextilde.sc edblgrave.sc edieresis.sc edotaccent.sc edotbelow.sc egrave.sc ehookabove.sc einvertedbreve.sc emacron.sc emacronacute.sc emacrongrave.sc eogonek.sc etilde.sc etildebelow.sc f.sc fdotaccent.sc h.sc h.sc.001 hbar.sc hbrevebelow.sc hcedilla.sc hcircumflex.sc hdieresis.sc hdotaccent.sc hdotbelow.sc i.sc idotless.sc iacute.sc ibreve.sc icaron.sc icircumflex.sc idblgrave.sc idieresis.sc idieresisacute.sc idotaccent.sc idotbelow.sc igrave.sc ihookabove.sc iinvertedbreve.sc ij.sc imacron.sc iogonek.sc itilde.sc itildebelow.sc k.sc kacute.sc kcaron.sc kcommaaccent.sc kdotbelow.sc kgreenlandic.sc klinebelow.sc l.sc lacute.sc lcaron.sc lcircumflexbelow.sc lcommaaccent.sc ldot.sc ldotbelow.sc ldotbelowmacron.sc llinebelow.sc lslash.sc n.sc nacute.sc ncaron.sc ncircumflexbelow.sc ncommaaccent.sc ndotaccent.sc ndotbelow.sc ngrave.sc nlinebelow.sc ntilde.sc eng.sc p.sc pacute.sc pdotaccent.sc thorn.sc r.sc racute.sc rcaron.sc rcommaaccent.sc rdblgrave.sc rdotaccent.sc rdotbelow.sc rdotbelowmacron.sc rinvertedbreve.sc rlinebelow.sc be-cy.loclSRB.sc be-cy.sc ve-cy.loclBGR.sc ve-cy.sc ge-cy.loclBGR.sc ge-cy.sc gje-cy.sc gheupturn-cy.sc ie-cy.sc iegrave-cy.sc io-cy.sc ii-cy.loclBGR.sc ii-cy.sc iishort-cy.loclBGR.sc iishort-cy.sc iigrave-cy.loclBGR.sc iigrave-cy.sc ka-cy.loclBGR.sc ka-cy.sc kje-cy.sc en-cy.sc pe-cy.loclBGR.sc pe-cy.sc er-cy.sc tse-cy.loclBGR.sc tse-cy.sc sha-cy.loclBGR.sc sha-cy.sc shcha-cy.loclBGR.sc shcha-cy.sc dzhe-cy.sc softsign-cy.loclBGR.sc softsign-cy.sc yeru-cy.sc i-cy.sc iu-cy.loclBGR.sc iu-cy.sc gamma.sc epsilon.sc eta.sc iota.sc kappa.sc nu.sc rho.sc iotadieresis.sc kaiSymbol.sc".split(),
    }
    glyphScripts = {
        "bdotaccent.sc": {"Latn"},
        "bdotbelow.sc": {"Latn"},
        "be-cy.loclSRB.sc": {"Cyrl"},
        "be-cy.sc": {"Cyrl"},
        "blinebelow.sc": {"Latn"},
        "d.sc": {"Latn"},
        "dcaron.sc": {"Latn"},
        "dcedilla.sc": {"Latn"},
        "dcircumflexbelow.sc": {"Latn"},
        "dcroat.sc": {"Latn"},
        "ddotaccent.sc": {"Latn"},
        "ddotbelow.sc": {"Latn"},
        "dlinebelow.sc": {"Latn"},
        "dzhe-cy.sc": {"Cyrl"},
        "e.sc": {"Latn"},
        "eacute.sc": {"Latn"},
        "ebreve.sc": {"Latn"},
        "ecaron.sc": {"Latn"},
        "ecedilla.sc": {"Latn"},
        "ecedillabreve.sc": {"Latn"},
        "ecircumflex.sc": {"Latn"},
        "ecircumflexacute.sc": {"Latn"},
        "ecircumflexbelow.sc": {"Latn"},
        "ecircumflexdotbelow.sc": {"Latn"},
        "ecircumflexgrave.sc": {"Latn"},
        "ecircumflexhookabove.sc": {"Latn"},
        "ecircumflextilde.sc": {"Latn"},
        "edblgrave.sc": {"Latn"},
        "edieresis.sc": {"Latn"},
        "edotaccent.sc": {"Latn"},
        "edotbelow.sc": {"Latn"},
        "egrave.sc": {"Latn"},
        "ehookabove.sc": {"Latn"},
        "einvertedbreve.sc": {"Latn"},
        "emacron.sc": {"Latn"},
        "emacronacute.sc": {"Latn"},
        "emacrongrave.sc": {"Latn"},
        "en-cy.sc": {"Cyrl"},
        "eng.sc": {"Latn"},
        "eogonek.sc": {"Latn"},
        "epsilon.sc": {"Grek"},
        "er-cy.sc": {"Cyrl"},
        "eta.sc": {"Grek"},
        "eth.sc": {"Latn"},
        "etilde.sc": {"Latn"},
        "etildebelow.sc": {"Latn"},
        "f.sc": {"Latn"},
        "fdotaccent.sc": {"Latn"},
        "gamma.sc": {"Grek"},
        "ge-cy.loclBGR.sc": {"Cyrl"},
        "ge-cy.sc": {"Cyrl"},
        "gheupturn-cy.sc": {"Cyrl"},
        "gje-cy.sc": {"Cyrl"},
        "h.sc": {"Latn", "Grek"},
        "hbar.sc": {"Latn"},
        "hbrevebelow.sc": {"Latn"},
        "hcedilla.sc": {"Latn"},
        "hcircumflex.sc": {"Latn"},
        "hdieresis.sc": {"Latn"},
        "hdotaccent.sc": {"Latn"},
        "hdotbelow.sc": {"Latn"},
        "i-cy.sc": {"Cyrl"},
        "i.sc": {"Latn"},
        "iacute.sc": {"Latn"},
        "ibreve.sc": {"Latn"},
        "icaron.sc": {"Latn"},
        "icircumflex.sc": {"Latn"},
        "idblgrave.sc": {"Latn"},
        "idieresis.sc": {"Latn"},
        "idieresisacute.sc": {"Latn"},
        "idotaccent.sc": {"Latn"},
        "idotbelow.sc": {"Latn"},
        "idotless.sc": {"Latn"},
        "ie-cy.sc": {"Cyrl"},
        "iegrave-cy.sc": {"Cyrl"},
        "igrave.sc": {"Latn"},
        "ihookabove.sc": {"Latn"},
        "ii-cy.loclBGR.sc": {"Cyrl"},
        "ii-cy.sc": {"Cyrl"},
        "iigrave-cy.loclBGR.sc": {"Cyrl"},
        "iigrave-cy.sc": {"Cyrl"},
        "iinvertedbreve.sc": {"Latn"},
        "iishort-cy.loclBGR.sc": {"Cyrl"},
        "iishort-cy.sc": {"Cyrl"},
        "ij.sc": {"Latn"},
        "imacron.sc": {"Latn"},
        "io-cy.sc": {"Cyrl"},
        "iogonek.sc": {"Latn"},
        "iota.sc": {"Grek"},
        "iotadieresis.sc": {"Grek"},
        "itilde.sc": {"Latn"},
        "itildebelow.sc": {"Latn"},
        "iu-cy.loclBGR.sc": {"Cyrl"},
        "iu-cy.sc": {"Cyrl"},
        "Izhitsa-cy": {"Cyrl"},
        "k.sc": {"Latn"},
        "ka-cy.loclBGR.sc": {"Cyrl"},
        "ka-cy.sc": {"Cyrl"},
        "kacute.sc": {"Latn"},
        "kaiSymbol.sc": {"Grek"},
        "kappa.sc": {"Grek"},
        "kcaron.sc": {"Latn"},
        "kcommaaccent.sc": {"Latn"},
        "kdotbelow.sc": {"Latn"},
        "kgreenlandic.sc": {"Latn"},
        "kje-cy.sc": {"Cyrl"},
        "klinebelow.sc": {"Latn"},
        "l.sc": {"Latn"},
        "lacute.sc": {"Latn"},
        "lcaron.sc": {"Latn"},
        "lcircumflexbelow.sc": {"Latn"},
        "lcommaaccent.sc": {"Latn"},
        "ldot.sc": {"Latn"},
        "ldotbelow.sc": {"Latn"},
        "ldotbelowmacron.sc": {"Latn"},
        "llinebelow.sc": {"Latn"},
        "lslash.sc": {"Latn"},
        "n.sc": {"Latn"},
        "nacute.sc": {"Latn"},
        "ncaron.sc": {"Latn"},
        "ncircumflexbelow.sc": {"Latn"},
        "ncommaaccent.sc": {"Latn"},
        "ndotaccent.sc": {"Latn"},
        "ndotbelow.sc": {"Latn"},
        "ngrave.sc": {"Latn"},
        "nlinebelow.sc": {"Latn"},
        "ntilde.sc": {"Latn"},
        "nu.sc": {"Grek"},
        "p.sc": {"Latn"},
        "pacute.sc": {"Latn"},
        "pdotaccent.sc": {"Latn"},
        "pe-cy.loclBGR.sc": {"Cyrl"},
        "pe-cy.sc": {"Cyrl"},
        "r.sc": {"Latn"},
        "racute.sc": {"Latn"},
        "rcaron.sc": {"Latn"},
        "rcommaaccent.sc": {"Latn"},
        "rdblgrave.sc": {"Latn"},
        "rdotaccent.sc": {"Latn"},
        "rdotbelow.sc": {"Latn"},
        "rdotbelowmacron.sc": {"Latn"},
        "rho.sc": {"Grek"},
        "rinvertedbreve.sc": {"Latn"},
        "rlinebelow.sc": {"Latn"},
        "sha-cy.loclBGR.sc": {"Cyrl"},
        "sha-cy.sc": {"Cyrl"},
        "shcha-cy.loclBGR.sc": {"Cyrl"},
        "shcha-cy.sc": {"Cyrl"},
        "softsign-cy.loclBGR.sc": {"Cyrl"},
        "softsign-cy.sc": {"Cyrl"},
        "thorn.sc": {"Latn"},
        "tse-cy.loclBGR.sc": {"Cyrl"},
        "tse-cy.sc": {"Cyrl"},
        "V": {"Latn"},
        "Vdotbelow": {"Latn"},
        "ve-cy.loclBGR.sc": {"Cyrl"},
        "ve-cy.sc": {"Cyrl"},
        "Vtilde": {"Latn"},
        "yeru-cy.sc": {"Cyrl"},
    }
    kerning = {("public.kern1.V", "public.kern2.H.sc"): -20}

    pairs_by_script = get_and_split_kerning_data(
        kerning, groups, glyphScripts.keys(), glyphScripts
    )
    with open("test.txt", "w") as f:
        pprint.pprint(pairs_by_script, stream=f)


def test_weird_split1() -> None:
    groups = {
        "public.kern1.first": "a h.sc".split(),
        "public.kern2.second": "b".split(),
    }
    glyphScripts = {
        "a": {"Latn"},
        "b": {"Latn"},
        "h.sc": {"Latn", "Zyyy"},
    }
    kerning = {("public.kern1.first", "public.kern2.second"): -20}

    pairs_by_script = get_and_split_kerning_data(
        kerning, groups, glyphScripts.keys(), glyphScripts
    )
    with open("test.txt", "w") as f:
        pprint.pprint(pairs_by_script, stream=f)


def test_weird_split2() -> None:
    # TODO: impl equality testing for KerningPair
    pair = KerningPair(["a", "something"], ["b"], 20, scripts={"Latn"})
    glyphScripts = {
        "a": {"Latn"},
        "b": {"Latn"},
        "something": {"Latn", "Zyyy"},
    }
    results = [
        (script, split_pair)
        for script, split_pair in pair.partitionByScript(glyphScripts)
    ]
    assert results == [
        ("Latn", KerningPair(["a", "something"], ["b"], 20, scripts={"Latn"}))
    ]
