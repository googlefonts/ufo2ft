import importlib
import pytest


@pytest.fixture(scope="session", params=["defcon", "ufoLib2"])
def FontClass(request):
    module = importlib.import_module(request.param)
    return module.Font
