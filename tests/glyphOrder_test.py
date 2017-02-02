import unittest
import os

from ufo2ft.outlineOTF import OutlineTTFCompiler
from defcon import Font


def getTestUFO():
    dirname = os.path.dirname(__file__)
    return Font(os.path.join(dirname, 'data', 'TestFont.ufo'))


class TestGlyphOrder(unittest.TestCase):

    def setUp(self):
        self.ufo = getTestUFO()

    def test_compile_original_glyph_order(self):
        DEFAULT_ORDER = ['.notdef', 'space', 'a', 'b', 'c']
        compiler = OutlineTTFCompiler(self.ufo)
        compiler.compile()
        self.assertEqual(compiler.otf.getGlyphOrder(), DEFAULT_ORDER)

    def test_compile_tweaked_glyph_order(self):
        NEW_ORDER = ['.notdef', 'space', 'b', 'a', 'c']
        self.ufo.lib['public.glyphOrder'] = NEW_ORDER
        compiler = OutlineTTFCompiler(self.ufo)
        compiler.compile()
        self.assertEqual(compiler.otf.getGlyphOrder(), NEW_ORDER)

    def test_compile_strange_glyph_order(self):
        """Move space and .notdef to end of glyph ids
        ufo2ft always puts .notdef first.
        """
        NEW_ORDER = ['b', 'a', 'c', 'space', '.notdef']
        EXPECTED_ORDER = ['.notdef', 'b', 'a', 'c', 'space']
        self.ufo.lib['public.glyphOrder'] = NEW_ORDER
        compiler = OutlineTTFCompiler(self.ufo)
        compiler.compile()
        self.assertEqual(compiler.otf.getGlyphOrder(), EXPECTED_ORDER)


if __name__ == "__main__":
    unittest.main()
