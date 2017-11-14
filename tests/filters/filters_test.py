from __future__ import print_function, division, absolute_import

from ufo2ft.filters import getFilterClass, BaseFilter

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


class FooBarFilter(BaseFilter):
    """A filter that does nothing."""

    _args = ("a", "b")
    _kwargs = {"c": 0}

    def filter(self, glyph):
        return False


@pytest.fixture(scope="module", autouse=True)
def fooBar():
    """Make a temporary 'ufo2ft.filters.fooBar' module containing a
    'FooBarFilter' class for testing the filter loading machinery.
    """
    with _TempModule("ufo2ft.filters.fooBar") as temp_module:
        temp_module.module.__dict__["FooBarFilter"] = FooBarFilter
        yield


def test_getFilterClass():
    assert getFilterClass("Foo Bar") == FooBarFilter
    assert getFilterClass("FooBar") == FooBarFilter
    assert getFilterClass("fooBar") == FooBarFilter
    with pytest.raises(ImportError):
        getFilterClass("Baz")

    with _TempModule("myfilters.fooBar") as temp_module:

        with pytest.raises(AttributeError):
            # this fails because `myfilters.fooBar` module does not
            # have a `FooBarFilter` class
            getFilterClass("Foo Bar", pkg="myfilters")

        temp_module.module.__dict__['FooBarFilter'] = FooBarFilter

        # this will attempt to import the `FooBarFilter` class from the
        # `myfilters.fooBar` module
        assert getFilterClass("Foo Bar", pkg="myfilters") == FooBarFilter


if __name__ == "__main__":
    sys.exit(pytest.main(sys.argv))
