from __future__ import print_function, division, absolute_import

from ufo2ft.filters import getFilterClass, BaseFilter
from ufo2ft.filters.removeOverlaps import RemoveOverlapsFilter

import sys
import types
import pytest


class _TempModule(object):
    """Temporarily replace a module in sys.modules with an empty namespace"""
    def __init__(self, mod_name):
        self.mod_name = mod_name
        self.module = types.ModuleType(mod_name)
        self._saved_module = []

    def __enter__(self):
        mod_name = self.mod_name
        try:
            self._saved_module.append(sys.modules[mod_name])
        except KeyError:
            pass
        sys.modules[mod_name] = self.module
        return self

    def __exit__(self, *args):
        if self._saved_module:
            sys.modules[self.mod_name] = self._saved_module[0]
        else:
            del sys.modules[self.mod_name]
        self._saved_module = []


def test_getFilterClass():
    assert getFilterClass("Remove Overlaps") == RemoveOverlapsFilter
    assert getFilterClass("RemoveOverlaps") == RemoveOverlapsFilter
    assert getFilterClass("removeOverlaps") == RemoveOverlapsFilter
    with pytest.raises(ImportError):
        getFilterClass("Foo Bar")

    class FooBarFilter(BaseFilter):
        def filter(self, glyph):
            return False

    with _TempModule("myfilters") as temp_pkg, \
            _TempModule("myfilters.fooBar") as temp_module:
        temp_pkg.module.__dict__['fooBar'] = temp_module
        temp_module.module.__dict__['FooBarFilter'] = FooBarFilter

        # this will attempt to import the `FooBarFilter` class from the
        # `myfilters.fooBar` module
        assert getFilterClass("Foo Bar", pkg="myfilters") == FooBarFilter


if __name__ == "__main__":
    sys.exit(pytest.main(sys.argv))
