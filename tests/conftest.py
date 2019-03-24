import importlib
import py
import pytest


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
