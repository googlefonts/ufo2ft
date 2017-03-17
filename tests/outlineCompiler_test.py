from fontTools.ttLib import TTFont
from fontTools.misc.py23 import basestring
from defcon import Font
from ufo2ft.outlineCompiler import OutlineTTFCompiler, OutlineOTFCompiler
from ufo2ft import compileTTF
import unittest
import os


def getTestUFO():
    dirname = os.path.dirname(__file__)
    return Font(os.path.join(dirname, 'data', 'TestFont.ufo'))


class OutlineTTFCompilerTest(unittest.TestCase):

    def setUp(self):
        self.ufo = getTestUFO()

    def test_setupTable_gasp(self):
        compiler = OutlineTTFCompiler(self.ufo)
        compiler.otf = TTFont()
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

    def test_makeGlyphsBoundingBoxes(self):
        # the call to 'makeGlyphsBoundingBoxes' happen in the __init__ method
        compiler = OutlineTTFCompiler(self.ufo)
        self.assertEqual(compiler.glyphBoundingBoxes['.notdef'],
                         (50, 0, 450, 750))
        # no outline data
        self.assertEqual(compiler.glyphBoundingBoxes['space'], None)
        # float coordinates are rounded, so is the bbox
        self.assertEqual(compiler.glyphBoundingBoxes['d'],
                         (90, 77, 211, 197))


class OutlineOTFCompilerTest(unittest.TestCase):

    def setUp(self):
        self.ufo = getTestUFO()

    def test_setupTable_CFF_all_blues_defined(self):
        self.ufo.info.postscriptBlueFuzz = 2
        self.ufo.info.postscriptBlueShift = 8
        self.ufo.info.postscriptBlueScale = 0.049736
        self.ufo.info.postscriptForceBold = False
        self.ufo.info.postscriptBlueValues = [-12, 0, 486, 498, 712, 724]
        self.ufo.info.postscriptOtherBlues = [-217, -205]
        self.ufo.info.postscriptFamilyBlues = [-12, 0, 486, 498, 712, 724]
        self.ufo.info.postscriptFamilyOtherBlues = [-217, -205]

        compiler = OutlineOTFCompiler(self.ufo)
        compiler.otf = TTFont(sfntVersion="OTTO")

        compiler.setupTable_CFF()

        cff = compiler.otf["CFF "].cff
        private = cff[list(cff.keys())[0]].Private

        self.assertEqual(private.BlueFuzz, 2)
        self.assertEqual(private.BlueShift, 8)
        self.assertEqual(private.BlueScale, 0.049736)
        self.assertEqual(private.ForceBold, False)
        self.assertEqual(private.BlueValues, [-12, 0, 486, 498, 712, 724])
        self.assertEqual(private.OtherBlues, [-217, -205])
        self.assertEqual(private.FamilyBlues, [-12, 0, 486, 498, 712, 724])
        self.assertEqual(private.FamilyOtherBlues, [-217, -205])

    def test_setupTable_CFF_no_blues_defined(self):
        # no blue values defined
        self.ufo.info.postscriptBlueValues = []
        self.ufo.info.postscriptOtherBlues = []
        self.ufo.info.postscriptFamilyBlues = []
        self.ufo.info.postscriptFamilyOtherBlues = []
        # the following attributes have no effect
        self.ufo.info.postscriptBlueFuzz = 2
        self.ufo.info.postscriptBlueShift = 8
        self.ufo.info.postscriptBlueScale = 0.049736
        self.ufo.info.postscriptForceBold = False

        compiler = OutlineOTFCompiler(self.ufo)
        compiler.otf = TTFont(sfntVersion="OTTO")

        compiler.setupTable_CFF()

        cff = compiler.otf["CFF "].cff
        private = cff[list(cff.keys())[0]].Private

        # expect default values as defined in fontTools' cffLib.py
        self.assertEqual(private.BlueFuzz, 1)
        self.assertEqual(private.BlueShift, 7)
        self.assertEqual(private.BlueScale, 0.039625)
        self.assertEqual(private.ForceBold, False)
        # CFF PrivateDict has no blues attributes
        self.assertFalse(hasattr(private, "BlueValues"))
        self.assertFalse(hasattr(private, "OtherBlues"))
        self.assertFalse(hasattr(private, "FamilyBlues"))
        self.assertFalse(hasattr(private, "FamilyOtherBlues"))

    def test_setupTable_CFF_some_blues_defined(self):
        self.ufo.info.postscriptBlueFuzz = 2
        self.ufo.info.postscriptForceBold = True
        self.ufo.info.postscriptBlueValues = []
        self.ufo.info.postscriptOtherBlues = [-217, -205]
        self.ufo.info.postscriptFamilyBlues = []
        self.ufo.info.postscriptFamilyOtherBlues = []

        compiler = OutlineOTFCompiler(self.ufo)
        compiler.otf = TTFont(sfntVersion="OTTO")

        compiler.setupTable_CFF()

        cff = compiler.otf["CFF "].cff
        private = cff[list(cff.keys())[0]].Private

        self.assertEqual(private.BlueFuzz, 2)
        self.assertEqual(private.BlueShift, 7)  # default
        self.assertEqual(private.BlueScale, 0.039625)  # default
        self.assertEqual(private.ForceBold, True)
        self.assertFalse(hasattr(private, "BlueValues"))
        self.assertEqual(private.OtherBlues, [-217, -205])
        self.assertFalse(hasattr(private, "FamilyBlues"))
        self.assertFalse(hasattr(private, "FamilyOtherBlues"))

    @staticmethod
    def get_charstring_program(ttFont, glyphName):
        cff = ttFont["CFF "].cff
        charstrings = cff[list(cff.keys())[0]].CharStrings
        c, _ = charstrings.getItemAndSelector(glyphName)
        c.decompile()
        return c.program

    def assertProgramEqual(self, expected, actual):
        self.assertEqual(len(expected), len(actual))
        for exp_token, act_token in zip(expected, actual):
            if isinstance(exp_token, basestring):
                self.assertEqual(exp_token, act_token)
            else:
                self.assertNotIsInstance(act_token, basestring)
                self.assertAlmostEqual(exp_token, act_token)

    def test_setupTable_CFF_round_all(self):
        # by default all floats are rounded to integer
        compiler = OutlineOTFCompiler(self.ufo)
        otf = compiler.otf = TTFont(sfntVersion="OTTO")

        compiler.setupTable_CFF()
        # glyph 'd' in TestFont.ufo contains float coordinates
        program = self.get_charstring_program(otf, "d")

        self.assertProgramEqual(program, [
            -26, 151, 197, 'rmoveto',
            -34, 0, -27, -27, 0, -33, 'rrcurveto',
            0, -33, 27, -27, 34, 0, 'rrcurveto',
            33, 0, 27, 27, 0, 33, 'rrcurveto',
            0, 33, -27, 27, -33, 0, 'rrcurveto',
            'endchar'])

    def test_setupTable_CFF_round_none(self):
        # roundTolerance=0 means 'don't round, keep all floats'
        compiler = OutlineOTFCompiler(self.ufo, roundTolerance=0)
        otf = compiler.otf = TTFont(sfntVersion="OTTO")

        compiler.setupTable_CFF()
        program = self.get_charstring_program(otf, "d")

        self.assertProgramEqual(program, [
            -26, 150.66, 197.32, 'rmoveto',
            -33.66, 0.0, -26.67, -26.99, 0.0, -33.33, 'rrcurveto',
            0.0, -33.33, 26.67, -26.66, 33.66, 0.0, 'rrcurveto',
            33.33, 0.0, 26.66, 26.66, 0.0, 33.33, 'rrcurveto',
            0.0, 33.33, -26.66, 26.99, -33.33, 0.0, 'rrcurveto',
            'endchar'])

    def test_setupTable_CFF_round_some(self):
        # only floats 'close enough' are rounded to integer
        compiler = OutlineOTFCompiler(self.ufo, roundTolerance=0.1)
        otf = compiler.otf = TTFont(sfntVersion="OTTO")

        compiler.setupTable_CFF()
        program = self.get_charstring_program(otf, "d")

        # e.g., 26.99 becomes 27, but 150.66 stays as it is
        self.assertProgramEqual(program, [
            -26, 150.66, 197.32, 'rmoveto',
            -33.66, 0, -26.67, -27, 0, -33.33, 'rrcurveto',
            0, -33.33, 26.67, -26.67, 33.66, 0, 'rrcurveto',
            33.34, 0, 26.65, 26.67, 0, 33.33, 'rrcurveto',
            0, 33.33, -26.65, 27, -33.34, 0, 'rrcurveto',
            'endchar'])

    def test_makeGlyphsBoundingBoxes(self):
        # the call to 'makeGlyphsBoundingBoxes' happen in the __init__ method
        compiler = OutlineOTFCompiler(self.ufo)
        # with default roundTolerance, all coordinates and hence the bounding
        # box values are rounded with round()
        self.assertEqual(compiler.glyphBoundingBoxes['d'],
                         (90, 77, 211, 197))

    def test_makeGlyphsBoundingBoxes_floats(self):
        # specifying a custom roundTolerance affects which coordinates are
        # rounded; in this case, the top-most Y coordinate stays a float
        # (197.32), hence the bbox.yMax (198) is rounded using math.ceiling()
        compiler = OutlineOTFCompiler(self.ufo, roundTolerance=0.1)
        self.assertEqual(compiler.glyphBoundingBoxes['d'],
                         (90, 77, 211, 198))



class TestGlyphOrder(unittest.TestCase):

    def setUp(self):
        self.ufo = getTestUFO()

    def test_compile_original_glyph_order(self):
        DEFAULT_ORDER = ['.notdef', 'space', 'a', 'b', 'c', 'd']
        compiler = OutlineTTFCompiler(self.ufo)
        compiler.compile()
        self.assertEqual(compiler.otf.getGlyphOrder(), DEFAULT_ORDER)

    def test_compile_tweaked_glyph_order(self):
        NEW_ORDER = ['.notdef', 'space', 'b', 'a', 'c', 'd']
        self.ufo.lib['public.glyphOrder'] = NEW_ORDER
        compiler = OutlineTTFCompiler(self.ufo)
        compiler.compile()
        self.assertEqual(compiler.otf.getGlyphOrder(), NEW_ORDER)

    def test_compile_strange_glyph_order(self):
        """Move space and .notdef to end of glyph ids
        ufo2ft always puts .notdef first.
        """
        NEW_ORDER = ['b', 'a', 'c', 'd', 'space', '.notdef']
        EXPECTED_ORDER = ['.notdef', 'b', 'a', 'c', 'd', 'space']
        self.ufo.lib['public.glyphOrder'] = NEW_ORDER
        compiler = OutlineTTFCompiler(self.ufo)
        compiler.compile()
        self.assertEqual(compiler.otf.getGlyphOrder(), EXPECTED_ORDER)


class TestNames(unittest.TestCase):

    def setUp(self):
        self.ufo = getTestUFO()

    def test_compile_without_production_names(self):
        result = compileTTF(self.ufo, useProductionNames=False)
        self.assertEqual(result.getGlyphOrder(),
                         ['.notdef', 'space', 'a', 'b', 'c', 'd'])

    def test_compile_with_production_names(self):
        result = compileTTF(self.ufo, useProductionNames=True)
        self.assertEqual(result.getGlyphOrder(),
                         ['.notdef', 'uni0020', 'uni0061', 'uni0062',
                          'uni0063', 'uni0064'])

    CUSTOM_POSTSCRIPT_NAMES = {
            '.notdef': '.notdef',
            'space': 'foo',
            'a': 'bar',
            'b': 'baz',
            'c': 'meh',
            'd': 'doh'
        }

    def test_compile_with_custom_postscript_names(self):
        self.ufo.lib['public.postscriptNames'] = self.CUSTOM_POSTSCRIPT_NAMES
        result = compileTTF(self.ufo, useProductionNames=True)
        self.assertEqual(sorted(result.getGlyphOrder()),
                         sorted(self.CUSTOM_POSTSCRIPT_NAMES.values()))

    def test_compile_with_custom_postscript_names_notdef_preserved(self):
        custom_names = dict(self.CUSTOM_POSTSCRIPT_NAMES)
        custom_names['.notdef'] = 'defnot'
        self.ufo.lib['public.postscriptNames'] = custom_names
        result = compileTTF(self.ufo, useProductionNames=True)
        self.assertEqual(result.getGlyphOrder(),
                         ['.notdef', 'foo', 'bar', 'baz', 'meh', 'doh'])


if __name__ == "__main__":
    import sys
    sys.exit(unittest.main())
