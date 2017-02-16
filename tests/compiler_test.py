from __future__ import \
    print_function, division, absolute_import, unicode_literals
from fontTools.misc.py23 import *
from fontTools.ttLib import TTFont
from defcon import Font
from ufo2ft import compileOTF, compileTTF
import difflib
import os
import sys
import tempfile
import unittest


def getpath(filename):
    dirname = os.path.dirname(__file__)
    return os.path.join(dirname, 'data', filename)


def loadUFO(filename):
    return Font(getpath(filename))


class CompilerTest(unittest.TestCase):
    _tempdir, _num_tempfiles = None, 0

    def testTestFont(self):
        # We have specific unit tests for CFF vs TrueType output, but we run
        # an integration test here to make sure things work end-to-end.
        # No need to test both formats for every single test case.
        self.expectTTX(compileTTF(loadUFO("TestFont.ufo")), "TestFont.ttx")
        self.expectTTX(compileOTF(loadUFO("TestFont.ufo")), "TestFont-CFF.ttx")

    def _temppath(self, suffix):
        if not self._tempdir:
            self._tempdir = tempfile.mkdtemp()
        self._num_tempfiles += 1
        return os.path.join(self._tempdir,
                            "tmp%d%s" % (self._num_tempfiles, suffix))

    def _readTTX(self, path):
        lines = []
        with open(path, "r", encoding="utf-8") as ttx:
            for line in ttx.readlines():
                # Elide ttLibVersion because it frequently changes.
                # Use os-native line separators so we can run difflib.
                if line.startswith("<ttFont "):
                    lines.append("<ttFont>" + os.linesep)
                else:
                    lines.append(line.rstrip() + os.linesep)
        return lines

    def expectTTX(self, font, expectedTTX):
        expected = self._readTTX(getpath(expectedTTX))
        font.recalcTimestamp = False
        font['head'].created, font['head'].modified = 3570196637, 3601822698
        font['head'].checkSumAdjustment = 0x12345678
        path = self._temppath(suffix=".ttx")
        font.saveXML(path)
        actual = self._readTTX(path)
        if actual != expected:
            for line in difflib.unified_diff(
                    expected, actual, fromfile=expectedTTX, tofile=path):
                sys.stderr.write(line)
            self.fail("TTX output is different from expected")


if __name__ == "__main__":
    sys.exit(unittest.main())
