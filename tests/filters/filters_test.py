from types import SimpleNamespace

import pytest
from fontTools.misc.loggingTools import CapturingLogHandler

from ufo2ft.filters import (
    FILTERS_KEY,
    BaseFilter,
    getFilterClass,
    loadFilterFromString,
    loadFilters,
    logger,
)

from ..testSupport import _TempModule


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

    with _TempModule("myfilters"), _TempModule("myfilters.fooBar") as temp_module:

        with pytest.raises(AttributeError):
            # this fails because `myfilters.fooBar` module does not
            # have a `FooBarFilter` class
            getFilterClass("Foo Bar", pkg="myfilters")

        temp_module.module.__dict__["FooBarFilter"] = FooBarFilter

        # this will attempt to import the `FooBarFilter` class from the
        # `myfilters.fooBar` module
        assert getFilterClass("Foo Bar", pkg="myfilters") == FooBarFilter


class MockFont(SimpleNamespace):
    pass


class MockGlyph(SimpleNamespace):
    pass


def test_loadFilters_empty():
    ufo = MockFont(lib={})
    assert FILTERS_KEY not in ufo.lib
    assert loadFilters(ufo) == ([], [])


@pytest.fixture
def ufo():
    ufo = MockFont(lib={})
    ufo.lib[FILTERS_KEY] = [{"name": "Foo Bar", "args": ["foo", "bar"]}]
    return ufo


def test_loadFilters_pre(ufo):
    ufo.lib[FILTERS_KEY][0]["pre"] = True
    pre, post = loadFilters(ufo)
    assert len(pre) == 1
    assert not post
    assert isinstance(pre[0], FooBarFilter)


def test_loadFilters_custom_namespace(ufo):
    ufo.lib[FILTERS_KEY][0]["name"] = "Self Destruct"
    ufo.lib[FILTERS_KEY][0]["namespace"] = "my_dangerous_filters"

    class SelfDestructFilter(FooBarFilter):
        def filter(self, glyph):
            # Don't try this at home!!! LOL :)
            # shutil.rmtree(os.path.expanduser("~"))
            return True

    with _TempModule("my_dangerous_filters"), _TempModule(
        "my_dangerous_filters.selfDestruct"
    ) as temp:
        temp.module.__dict__["SelfDestructFilter"] = SelfDestructFilter

        _, [filter_obj] = loadFilters(ufo)

    assert isinstance(filter_obj, SelfDestructFilter)


def test_loadFilters_args_missing(ufo):
    del ufo.lib[FILTERS_KEY][0]["args"]

    with pytest.raises(TypeError) as exc_info:
        loadFilters(ufo)

    assert exc_info.match("missing")


def test_loadFilters_args_unsupported(ufo):
    ufo.lib[FILTERS_KEY][0]["args"].append("baz")

    with pytest.raises(TypeError) as exc_info:
        loadFilters(ufo)

    assert exc_info.match("unsupported")


def test_loadFilters_args_as_keywords(ufo):
    del ufo.lib[FILTERS_KEY][0]["args"]
    ufo.lib[FILTERS_KEY][0]["kwargs"] = {"a": "foo", "b": "bar"}

    _, [filter_obj] = loadFilters(ufo)

    assert filter_obj.options.a == "foo"
    assert filter_obj.options.b == "bar"


def test_loadFilters_args_as_duplicated_keywords(ufo):
    ufo.lib[FILTERS_KEY][0]["args"] = ["foo"]
    ufo.lib[FILTERS_KEY][0]["kwargs"] = {"a": "foo", "b": "bar"}

    with pytest.raises(TypeError) as exc_info:
        loadFilters(ufo)

    assert exc_info.match("duplicated")


def test_loadFilters_include_all(ufo):
    _, [filter_obj] = loadFilters(ufo)

    assert filter_obj.include(MockGlyph(name="hello"))
    assert filter_obj.include(MockGlyph(name="world"))


def test_loadFilters_include_list(ufo):
    ufo.lib[FILTERS_KEY][0]["include"] = ["a", "b"]

    _, [filter_obj] = loadFilters(ufo)

    assert filter_obj.include(MockGlyph(name="a"))
    assert filter_obj.include(MockGlyph(name="b"))
    assert not filter_obj.include(MockGlyph(name="c"))


def test_loadFilters_exclude_list(ufo):
    ufo.lib[FILTERS_KEY][0]["exclude"] = ["a", "b"]

    _, [filter_obj] = loadFilters(ufo)

    assert not filter_obj.include(MockGlyph(name="a"))
    assert not filter_obj.include(MockGlyph(name="b"))
    assert filter_obj.include(MockGlyph(name="c"))


def test_loadFilters_both_include_exclude(ufo):
    ufo.lib[FILTERS_KEY][0]["include"] = ["a", "b"]
    ufo.lib[FILTERS_KEY][0]["exclude"] = ["c", "d"]

    with pytest.raises(ValueError) as exc_info:
        loadFilters(ufo)

    assert exc_info.match("arguments are mutually exclusive")


def test_loadFilters_failed(ufo):
    ufo.lib[FILTERS_KEY].append(dict(name="Non Existent"))

    with CapturingLogHandler(logger, level="ERROR") as captor:
        loadFilters(ufo)

    captor.assertRegex("Failed to load filter")


def test_loadFilters_kwargs_unsupported(ufo):
    ufo.lib[FILTERS_KEY][0]["kwargs"] = {}
    ufo.lib[FILTERS_KEY][0]["kwargs"]["c"] = 1
    ufo.lib[FILTERS_KEY][0]["kwargs"]["d"] = 2  # unknown

    with pytest.raises(TypeError) as exc_info:
        loadFilters(ufo)

    assert exc_info.match("got an unsupported keyword")


VALID_SPEC_STRINGS = [
    "RemoveOverlapsFilter",
    "PropagateAnchorsFilter(include=['a', 'b', 'c'])",
    "ufo2ft.filters.fooBar::FooBarFilter(a='a', b='b', c=1)",
]


@pytest.mark.parametrize("spec", VALID_SPEC_STRINGS)
def test_loadFilterFromString(spec, ufo):
    philter = loadFilterFromString(spec)
    assert callable(philter)


def test_loadFilterFromString_args_missing(ufo):
    with pytest.raises(TypeError) as info:
        loadFilterFromString(
            "ufo2ft.filters.fooBar::FooBarFilter(a='a', c=1)",
        )
    assert info.match("missing 1 required positional argument: 'b'")

    with pytest.raises(TypeError) as info:
        loadFilterFromString(
            "ufo2ft.filters.fooBar::FooBarFilter(c=1)",
        )
    assert info.match("missing 2 required positional arguments: 'a', 'b'")


def test_BaseFilter_repr():
    class NoArgFilter(BaseFilter):
        pass

    assert repr(NoArgFilter()) == "NoArgFilter()"

    assert repr(FooBarFilter("a", "b", c=1)) == ("FooBarFilter('a', 'b', c=1)")

    assert (
        repr(FooBarFilter("c", "d", include=["x", "y"]))
        == "FooBarFilter('c', 'd', c=0, include=['x', 'y'])"
    )

    assert (
        repr(FooBarFilter("e", "f", c=2.0, exclude=("z",)))
        == "FooBarFilter('e', 'f', c=2.0, exclude=('z',))"
    )

    def f(g):
        return False

    assert repr(
        FooBarFilter("g", "h", include=f)
    ) == "FooBarFilter('g', 'h', c=0, include={})".format(repr(f))


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main(sys.argv))
