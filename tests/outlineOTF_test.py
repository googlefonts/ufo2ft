from fontTools.ttLib import TTFont
from defcon import Font
from ufo2ft.outlineOTF import OutlineTTFCompiler
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


if __name__ == "__main__":
    unittest.main()
