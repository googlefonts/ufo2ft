from __future__ import (
    print_function,
    absolute_import,
    division,
    unicode_literals,
)

from ufo2ft.featureWriters import (
    BaseFeatureWriter,
    FEATURE_WRITERS_KEY,
    loadFeatureWriters,
    loadFeatureWriterFromString,
)
import pytest
from ..testSupport import _TempModule


class FooBarWriter(BaseFeatureWriter):

    tableTag = "GSUB"

    def __init__(self, **kwargs):
        pass

    def write(self, font, feaFile, compiler=None):
        return False


@pytest.fixture(scope="module", autouse=True)
def customWriterModule():
    """Make a temporary 'myFeatureWriters' module containing a
    'FooBarWriter' class for testing the wruter loading machinery.
    """
    with _TempModule("myFeatureWriters") as temp_module:
        temp_module.module.__dict__["FooBarWriter"] = FooBarWriter
        yield


VALID_SPEC_LISTS = [
    [{"class": "KernFeatureWriter"}],
    [
        {"class": "KernFeatureWriter", "options": {"ignoreMarks": False}},
        {"class": "MarkFeatureWriter", "options": {"features": ["mark"]}},
    ],
    [
        {
            "class": "FooBarWriter",
            "module": "myFeatureWriters",
            "options": {"a": 1},
        }
    ],
]


@pytest.mark.parametrize("specList", VALID_SPEC_LISTS)
def test_loadFeatureWriters_valid(specList, FontClass):
    ufo = FontClass()
    ufo.lib[FEATURE_WRITERS_KEY] = specList
    for writer in loadFeatureWriters(ufo, ignoreErrors=False):
        assert writer.tableTag in {"GSUB", "GPOS"}
        assert callable(writer.write)


VALID_SPEC_STRINGS = [
    "KernFeatureWriter",
    "KernFeatureWriter(ignoreMarks=False)",
    "MarkFeatureWriter(features=['mark'])",
    "myFeatureWriters::FooBarWriter(a=1)",
]


@pytest.mark.parametrize("spec", VALID_SPEC_STRINGS)
def test_loadFeatureWriterFromString_valid(spec, FontClass):
    writer = loadFeatureWriterFromString(spec)
    assert writer.tableTag in {"GSUB", "GPOS"}
    assert callable(writer.write)
