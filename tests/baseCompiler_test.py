import sys
from types import ModuleType

from ufo2ft._compilers.baseCompiler import _maybe_uppercase_beyond64k


class _FakeTTFont:
    def __init__(self, glyph_count):
        self.glyph_count = glyph_count

    def getGlyphOrder(self):
        return range(self.glyph_count)


def test_maybe_uppercase_beyond64k_ignores_64k_glyphs(monkeypatch):
    def import_module(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "fontTools.ttLib.beyond64k":
            raise AssertionError("beyond64k should not be imported")
        return real_import(name, globals, locals, fromlist, level)

    real_import = __import__
    monkeypatch.setattr("builtins.__import__", import_module)

    _maybe_uppercase_beyond64k(_FakeTTFont(0x10000))


def test_maybe_uppercase_beyond64k_converts_above_64k(monkeypatch):
    calls = []
    module = ModuleType("fontTools.ttLib.beyond64k")
    module.upper_tables = calls.append
    monkeypatch.setitem(sys.modules, "fontTools.ttLib.beyond64k", module)

    font = _FakeTTFont(0x10001)
    _maybe_uppercase_beyond64k(font)

    assert calls == [font]
