import unittest
import os

from ufo2ft import compileTTF
from defcon import Font


def getTestUFO():
    dirname = os.path.dirname(__file__)
    return Font(os.path.join(dirname, 'data', 'TestFont.ufo'))


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

