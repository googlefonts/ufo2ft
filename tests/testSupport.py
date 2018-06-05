from __future__ import print_function, division, absolute_import
import sys
import os
import types
import contextlib
from fontTools.misc.py23 import tostr


class _TempModule(object):
    """Temporarily replace a module in sys.modules with an empty namespace"""

    def __init__(self, mod_name):
        mod_name = tostr(mod_name, encoding="ascii")
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


@contextlib.contextmanager
def pushd(target):
    saved = os.getcwd()
    os.chdir(target)
    try:
        yield saved
    finally:
        os.chdir(saved)
