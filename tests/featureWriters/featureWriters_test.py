from ufo2ft.featureWriters import (
    FEATURE_WRITERS_KEY,
    BaseFeatureWriter,
    loadFeatureWriterFromString,
    loadFeatureWriters,
)

try:
    from plistlib import FMT_XML, loads

    def readPlistFromString(s):
        return loads(s, fmt=FMT_XML)

except ImportError:
    from plistlib import readPlistFromString

import pytest

from ..testSupport import _TempModule

TEST_LIB_PLIST = readPlistFromString(
    b"""
<dict>
    <key>com.github.googlei18n.ufo2ft.featureWriters</key>
    <array>
        <dict>
            <key>class</key>
            <string>KernFeatureWriter</string>
            <key>options</key>
            <dict>
                <key>mode</key>
                <string>skip</string>
            </dict>
        </dict>
    </array>
</dict>
"""
)


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
    [{"class": "FooBarWriter", "module": "myFeatureWriters", "options": {"a": 1}}],
    TEST_LIB_PLIST[FEATURE_WRITERS_KEY],
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
