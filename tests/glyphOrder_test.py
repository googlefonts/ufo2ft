import unittest
import os

from ufo2ft.outlineOTF import OutlineTTFCompiler
from defcon import Font


def getTestUFO():
    dirname = os.path.dirname(__file__)
    return Font(os.path.join(dirname, 'data', 'TestFont.ufo'))


class TestGlyphOrder(unittest.TestCase):

    NEW_GLYPH_ORDER = ['.notdef', 'space', 'b', 'a', 'c']

    def setUp(self):
        self.ufo = getTestUFO()
        self.ufo.lib['public.glyphOrder'] = self.NEW_GLYPH_ORDER

    def test_compile_glyph_order(self):
        compiler = OutlineTTFCompiler(self.ufo)
        compiler.compile()
        self.assertEqual(compiler.otf.getGlyphOrder(), self.NEW_GLYPH_ORDER)


if __name__ == "__main__":
    unittest.main()
