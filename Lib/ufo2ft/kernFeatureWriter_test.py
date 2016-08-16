from __future__ import print_function, division, absolute_import, unicode_literals

import unittest
from defcon import Font

from ufo2ft.kernFeatureWriter import KernFeatureWriter


class KernFeatureWriterTest(unittest.TestCase):
    def test_collect_fea_classes(self):
        text = '@MMK_L_v = [v w y];'
        expected = {'@MMK_L_v': ['v', 'w', 'y']}

        ufo = Font()
        ufo.features.text = text
        writer = KernFeatureWriter(ufo)
        writer._collectFeaClasses()
        self.assertEquals(writer.leftFeaClasses, expected)


if __name__ == '__main__':
    unittest.main()
