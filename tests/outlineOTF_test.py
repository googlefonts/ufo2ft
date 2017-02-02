from fontTools.ttLib import TTFont
from defcon import Font
from ufo2ft.outlineOTF import OutlineTTFCompiler
from ufo2ft import compileTTF
import unittest
import os


def getTestUFO():
    dirname = os.path.dirname(__file__)
    return Font(os.path.join(dirname, 'data', 'TestFont.ufo'))


class TestOutlineTTCompiler(unittest.TestCase):

    def setUp(self):
        self.otf = TTFont()
        self.ufo = getTestUFO()

    def test_setupTable_gasp(self):
        compiler = OutlineTTFCompiler(self.ufo)
        compiler.otf = self.otf
        compiler.setupTable_gasp()
        self.assertTrue('gasp' in compiler.otf)
        self.assertEqual(compiler.otf['gasp'].gaspRange,
                         {7: 10, 65535: 15})

    def test_compile_with_gasp(self):
        compiler = OutlineTTFCompiler(self.ufo)
        compiler.compile()
        self.assertTrue('gasp' in compiler.otf)
        self.assertEqual(compiler.otf['gasp'].gaspRange,
                         {7: 10, 65535: 15})

    def test_compile_without_gasp(self):
        self.ufo.info.openTypeGaspRangeRecords = None
        compiler = OutlineTTFCompiler(self.ufo)
        compiler.compile()
        self.assertTrue('gasp' not in compiler.otf)

    def test_compile_empty_gasp(self):
        # ignore empty gasp
        self.ufo.info.openTypeGaspRangeRecords = []
        compiler = OutlineTTFCompiler(self.ufo)
        compiler.compile()
        self.assertTrue('gasp' not in compiler.otf)


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


class TestProductionNames(unittest.TestCase):

    def setUp(self):
        self.ufo = getTestUFO()

    def test_compile_without_production_names(self):
        result = compileTTF(self.ufo, useProductionNames=False)
        self.assertEqual(result.getGlyphOrder(), ['.notdef', 'space', 'a', 'b', 'c'])

    def test_compile_with_production_names(self):
        result = compileTTF(self.ufo, useProductionNames=True)
        self.assertEqual(result.getGlyphOrder(), ['.notdef', 'uni0020', 'uni0061', 'uni0062', 'uni0063'])


if __name__ == "__main__":
    unittest.main()
