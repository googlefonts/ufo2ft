import os

import py
import pytest
from fontTools import designspaceLib


@pytest.fixture(scope="session", params=["defcon", "ufoLib2"])
def ufo_module(request):
    return pytest.importorskip(request.param)


@pytest.fixture(scope="session")
def FontClass(ufo_module):
    if hasattr(ufo_module.Font, "open"):

        def ctor(path=None):
            if path is None:
                return ufo_module.Font()
            else:
                return ufo_module.Font.open(path)

        return ctor
    return ufo_module.Font


@pytest.fixture(scope="session")
def InfoClass(ufo_module):
    return ufo_module.objects.info.Info


@pytest.fixture
def datadir():
    return py.path.local(py.path.local(__file__).dirname).join("data")


def getpath(filename):
    dirname = os.path.dirname(__file__)
    return os.path.join(dirname, "data", filename)


@pytest.fixture
def layertestrgufo(FontClass):
    font = FontClass(getpath("LayerFont-Regular.ufo"))
    return font


@pytest.fixture
def layertestbdufo(FontClass):
    font = FontClass(getpath("LayerFont-Bold.ufo"))
    return font


@pytest.fixture
def designspace(layertestrgufo, layertestbdufo):
    ds = designspaceLib.DesignSpaceDocument()

    a1 = designspaceLib.AxisDescriptor()
    a1.tag = "wght"
    a1.name = "Weight"
    a1.default = a1.minimum = 350
    a1.maximum = 625
    ds.addAxis(a1)

    s1 = designspaceLib.SourceDescriptor()
    s1.name = "Layer Font Regular"
    s1.familyName = "Layer Font"
    s1.styleName = "Regular"
    s1.filename = "LayerFont-Regular.ufo"
    s1.location = {"Weight": 350}
    s1.font = layertestrgufo
    ds.addSource(s1)

    s2 = designspaceLib.SourceDescriptor()
    s2.name = "Layer Font Medium"
    s2.familyName = "Layer Font"
    s2.styleName = "Medium"
    s2.filename = "LayerFont-Regular.ufo"
    s2.layerName = "Medium"
    s2.location = {"Weight": 450}
    s2.font = layertestrgufo
    ds.addSource(s2)

    s3 = designspaceLib.SourceDescriptor()
    s3.name = "Layer Font Bold"
    s3.familyName = "Layer Font"
    s3.styleName = "Bold"
    s3.filename = "LayerFont-Bold.ufo"
    s3.location = {"Weight": 625}
    s3.font = layertestbdufo
    ds.addSource(s3)

    return ds


@pytest.fixture
def designspace_v5(FontClass):
    def draw_rectangle(pen, x_offset, y_offset):
        pen.moveTo((0 + x_offset, 0 + y_offset))
        pen.lineTo((10 + x_offset, 0 + y_offset))
        pen.lineTo((10 + x_offset, 10 + y_offset))
        pen.lineTo((0 + x_offset, 10 + y_offset))
        pen.closePath()

    def add_cvt(font, index):
        font.lib["public.truetype.instructions"] = {
            "controlValue": {0: 0, 2: 30 + 10 * index, 3: 100 - index**2},
            "formatVersion": "1",
            "maxFunctionDefs": 1,
            "maxInstructionDefs": 0,
            "maxStackElements": 2,
            "maxStorage": 0,
            "maxTwilightPoints": 0,
            "maxZones": 1,
        }

    def add_programs(font):
        font.lib["public.truetype.instructions"][
            "controlValueProgram"
        ] = "PUSHB[ ]\n4 3\nINSTCTRL[ ]"
        font.lib["public.truetype.instructions"][
            "fontProgram"
        ] = "PUSHB[ ]\n0\nFDEF[ ]\nPOP[ ]\nENDF[ ]"

    def add_glyph_program(glyph, hash):
        # The hash must be passed as an argument. We could probably calculate it here,
        # but it must match the outline after it has been passed through cu2qu.
        glyph.lib["public.truetype.instructions"] = {
            "assembly": "PUSHB[ ]\n0 0\nSVTCA[0]\nMDRP[01100]",
            "formatVersion": "1",
            "id": hash,
        }

    def draw_something(glyph, number, is_sans):
        # Ensure Sans and Serif sources are incompatible to make sure that the
        # DS5 code treats them separately when using e.g. cu2qu. Use some number
        # to offset the drawings so we get some variation.
        if is_sans:
            draw_rectangle(glyph.getPen(), 10 * number, 0)
        else:
            draw_rectangle(glyph.getPen(), -10 * number, -20)
            draw_rectangle(glyph.getPen(), 10 * number, 20)

    ds5 = designspaceLib.DesignSpaceDocument.fromfile(
        "tests/data/DSv5/test_v5_MutatorSans_and_Serif.designspace"
    )

    sources = {}
    # Create base UFOs
    for index, source in enumerate(ds5.sources):
        if source.layerName is not None:
            continue
        font = FontClass()
        add_cvt(font, index)
        if index == 0:
            # Add some instructions to the default source
            add_programs(font)
        for name in ("I", "S", "I.narrow", "S.closed", "a"):
            glyph = font.newGlyph(name)
            draw_something(glyph, index, "Serif" not in source.filename)
        if index == 0:
            add_glyph_program(font["a"], "w0l0+0l0+10l10+10l10+0|")
        font.lib["public.glyphOrder"] = sorted(font.keys())
        sources[source.filename] = font

    # Fill in sparse UFOs
    for index, source in enumerate(ds5.sources):
        if source.layerName is None:
            continue
        font = sources[source.filename]
        layer = font.newLayer(source.layerName)
        for name in ("I", "S", "I.narrow", "S.closed"):
            glyph = layer.newGlyph(name)
            draw_something(glyph, index, "Serif" not in source.filename)

    # Assign UFOs to their attribute
    for source in ds5.sources:
        source.font = sources[source.filename]

    return ds5
