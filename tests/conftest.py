import os
import py
import pytest

from fontTools import designspaceLib


@pytest.fixture(scope="session", params=["defcon", "ufoLib2"])
def ufo_module(request):
    """
    Return a fully qualified module for a request.

    Args:
        request: (todo): write your description
    """
    return pytest.importorskip(request.param)


@pytest.fixture(scope="session")
def FontClass(ufo_module):
    """
    Return the ufo class for a ufo.

    Args:
        ufo_module: (todo): write your description
    """
    if hasattr(ufo_module.Font, "open"):

        def ctor(path=None):
            """
            Return the currently open window object.

            Args:
                path: (str): write your description
            """
            if path is None:
                return ufo_module.Font()
            else:
                return ufo_module.Font.open(path)

        return ctor
    return ufo_module.Font


@pytest.fixture(scope="session")
def InfoClass(ufo_module):
    """
    Return a wsdlmodule class for the given ufo.

    Args:
        ufo_module: (todo): write your description
    """
    return ufo_module.objects.info.Info


@pytest.fixture
def datadir():
    """
    Return the path to the datadir.

    Args:
    """
    return py.path.local(py.path.local(__file__).dirname).join("data")


def getpath(filename):
    """
    Return the path of the file.

    Args:
        filename: (str): write your description
    """
    dirname = os.path.dirname(__file__)
    return os.path.join(dirname, "data", filename)


@pytest.fixture
def layertestrgufo(FontClass):
    """
    Return a font font.

    Args:
        FontClass: (todo): write your description
    """
    font = FontClass(getpath("LayerFont-Regular.ufo"))
    return font


@pytest.fixture
def layertestbdufo(FontClass):
    """
    Returns a font object.

    Args:
        FontClass: (todo): write your description
    """
    font = FontClass(getpath("LayerFont-Bold.ufo"))
    return font


@pytest.fixture
def designspace(layertestrgufo, layertestbdufo):
    """
    Create designspace document.

    Args:
        layertestrgufo: (todo): write your description
        layertestbdufo: (todo): write your description
    """
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
