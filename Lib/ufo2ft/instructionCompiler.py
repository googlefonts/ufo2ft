# -*- coding: utf-8 -*-
from __future__ import print_function, division, absolute_import, unicode_literals

from fontTools.ttLib.tables._g_a_s_p import \
    GASP_SYMMETRIC_GRIDFIT, GASP_SYMMETRIC_SMOOTHING, GASP_DOGRAY, GASP_GRIDFIT
from math import log2

import logging


logger = logging.getLogger(__name__)

# Calculate the bit numbers for gasp flags
doGray = log2(GASP_DOGRAY)
doGridfit = log2(GASP_GRIDFIT)
symGridfit = log2(GASP_SYMMETRIC_GRIDFIT)
symSmoothing = log2(GASP_SYMMETRIC_SMOOTHING)


hti_flags = """flags {
      X 1     # X axis
      Y 0     # Y axis
      O 1     # Use original outline
      N 0     # Use gridfitted outline
      R 1     # Round distance; or perpendicular to line
      r 0     # Do not round distance; or parallel to line
      M 1     # Set rp0 to point number on the stack
      m 0     # Do not set rp0
      1 1     # Use rp1
      2 0     # Use rp2
      > 1     # Obey minimum distance
      < 0     # Do not obey minimum distance
     Gr 00    # Gray
     Bl 01    # Black
     Wh 10    # White

  # Combined flags
  m<rGr 00000
  m<rBl 00001
  m<rWh 00010
  m<RGr 00100
  m<RBl 00101
  m<RWh 00110
  m>rGr 01000
  m>rBl 01001
  m>rWh 01010
  m>RGr 01100
  m>RBl 01101
  m>RWh 01110
  M<rGr 10000
  M<rBl 10001
  M<rWh 10010
  M<RGr 10100
  M<RBl 10101
  M<RWh 10110
  M>rGr 11000
  M>rBl 11001
  M>rWh 11010
  M>RGr 11100
  M>RBl 11101
  M>RWh 11110
}
"""


class InstructionCompiler(object):
    def __init__(self, ufo, ttf):
        self.ufo = ufo
        self.font = ttf

    def compile_cvt(self):
        pass

    def compile_flags(self):
        return hti_flags

    def compile_fpgm(self):
        pass

    def compile_gasp(self):
        gasp = ""
        if hasattr(self.ufo.info, "openTypeGaspRangeRecords"):
            ufo_gasp = self.ufo.info.openTypeGaspRangeRecords
            if ufo_gasp is not None:
                for r in self.ufo.info.openTypeGaspRangeRecords:
                    bits = r["rangeGaspBehavior"]
                    gasp += "%7i %9s %6s %10s %12s\n" % (
                        r["rangeMaxPPEM"],
                        "doGridfit" if doGridfit in bits else "",
                        "doGray" if doGray in bits else "",
                        "symGridfit" if symGridfit in bits else "",
                        "symSmoothing" if symSmoothing in bits else "",
                    )
        if gasp:
            return "gasp {\n%s}\n" % gasp
        else:
            return ""

    def compile_glyf(self):
        pass

    def compile_head(self):
        head = ""

        # Head flags
        if hasattr(self.ufo.info, "openTypeHeadFlags"):
            flags = self.ufo.info.openTypeHeadFlags
            if flags is not None:
                head += "# %4i flags_instructionsMayDependOnPointSize\n" % (
                    1 if 2 in flags else 0
                )
                head += "# %4i flags_forceIntegerPPEM\n" % (
                    1 if 3 in flags else 0
                )
                head += "# %4i flags_instructionsMayAlterAdvanceWidth\n" % (
                    1 if 4 in flags else 0
                )
                head += "# %4i flags_optimizedForClearType\n" % (
                    1 if 13 in flags else 0
                )

        # Lowest rec PPEM
        if hasattr(self.ufo.info, "openTypeHeadLowestRecPPEM"):
            lowestRecPPEM = self.ufo.info.openTypeHeadLowestRecPPEM
            if lowestRecPPEM is not None:
                head += "# %4i lowestRecPPEM\n" % lowestRecPPEM

        if head:
            return "# head {\n%s# }\n" % head
        else:
            return ""

    def compile_prep(self):
        pass

    def compile(self):
        flags = self.compile_flags()
        gasp = self.compile_gasp()
        head = self.compile_head()
        hti = "\n".join([
            flags,
            gasp,
            head,
        ]) + "\n"
        return hti
