# -*- coding: utf-8 -*-
from __future__ import print_function, division, absolute_import, unicode_literals

from fontTools.pens.hashPointPen import HashPointPen
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
      1 X     # X axis
      0 Y     # Y axis
      1 O     # Use original outline
      0 N     # Use gridfitted outline
      1 R     # Round distance; or perpendicular to line
      0 r     # Do not round distance; or parallel to line
      1 M     # Set rp0 to point number on the stack
      0 m     # Do not set rp0
      1 1     # Use rp1
      0 2     # Use rp2
      1 D     # Obey minimum distance VTT: >
      0 d     # Do not obey minimum distance VTT: <
     00 Gr    # Gray
     01 Bl    # Black
     10 Wh    # White

  # Combined flags
  00000 mdrGr
  00001 mdrBl
  00010 mdrWh
  00100 mdRGr
  00101 mdRBl
  00110 mdRWh
  01000 mDrGr
  01001 mDrBl
  01010 mDrWh
  01100 mDRGr
  01101 mDRBl
  01110 mDRWh
  10000 MdrGr
  10001 MdrBl
  10010 MdrWh
  10100 MdRGr
  10101 MdRBl
  10110 MdRWh
  11000 MDrGr
  11001 MDrBl
  11010 MDrWh
  11100 MDRGr
  11101 MDRBl
  11110 MDRWh
}
"""

ufoLibKey = "public.truetype.instructions"


class InstructionCompiler(object):
    def __init__(self, ufo, ttf, rename_map={}):
        self.ufo = ufo
        self.font = ttf
        self.rename_map = rename_map

    def _compile_program(self, key, block_name):
        hti = ""
        ttdata = self.ufo.lib.get(ufoLibKey, None)
        if ttdata:
            value = ttdata.get(key, None)
            if value is not None:
                if isinstance(value, str):
                    hti += value
                else:
                    # CVT is a list
                    cvts = []
                    for cvt in value:
                        cvts.append("%6s %s" % (cvt["value"], cvt["id"]))
                    hti = "\n".join(cvts) + "\n"
        if hti:
            print("%s {\n%s}\n" % (block_name, hti))
            return "%s {\n%s}\n" % (block_name, hti)
        else:
            return "\n"

    def compile_cvt(self):
        return self._compile_program("controlValue", "cvt")

    def compile_flags(self):
        return hti_flags

    def compile_fpgm(self):
        return self._compile_program("fontProgram", "fpgm")

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
            return "\n"

    def compile_glyf(self):
        glyf = []
        for name in sorted(self.ufo.keys()):
            production_name = self.rename_map.get(name, name)
            glyph = self.ufo[name]
            ttdata = glyph.lib.get(ufoLibKey, None)
            if ttdata is None:
                glyf.append("%s {\n}\n" % production_name)
            else:
                formatVersion = ttdata.get("formatVersion", None)
                if formatVersion != "1":
                    logger.error("Unknown formatVersion %i in glyph '%s', it will have no instructions in font." % (formatVersion, name))
                    continue

                # Check if glyph hash matches the current outlines
                hash_pen = HashPointPen(glyph, self.ufo)
                glyph.drawPoints(hash_pen)
                glyph_id = ttdata.get("id", None)
                if glyph_id is None or glyph_id != hash_pen.getHash():
                    logger.error("Glyph hash mismatch, glyph '%s' will have no instructions in font." % name)
                    continue

                # Write hti code
                pgm = ttdata.get("assembly", None)
                if pgm is not None:
                    glyf.append("%s {\n  %s\n}\n" % (production_name, pgm.strip()))
        if glyf:
            return "\n".join(glyf)
        else:
            return "\n"

    def compile_head(self):
        head = ""

        # Head flags
        if hasattr(self.ufo.info, "openTypeHeadFlags"):
            flags = self.ufo.info.openTypeHeadFlags
            if flags is not None:
                head += "%4i flags.instructionsMayDependOnPointSize\n" % (
                    1 if 2 in flags else 0
                )
                head += "%4i flags.forcePpemToIntegerValues\n" % (
                    1 if 3 in flags else 0
                )
                head += "%4i flags.instructionsMayAlterAdvanceWidth\n" % (
                    1 if 4 in flags else 0
                )
                head += "%4i flags.fontOptimizedForClearType\n" % (
                    1 if 13 in flags else 0
                )

        # Lowest rec PPEM
        if hasattr(self.ufo.info, "openTypeHeadLowestRecPPEM"):
            lowestRecPPEM = self.ufo.info.openTypeHeadLowestRecPPEM
            if lowestRecPPEM is not None:
                head += "%4i lowestRecPPEM\n" % lowestRecPPEM

        if head:
            return "head {\n%s}\n" % head
        else:
            return "\n"

    def compile_maxp(self):
        maxp = ""
        ttdata = self.ufo.lib.get(ufoLibKey, None)
        if ttdata:
            for name in (
                "maxStorage",
                "maxFunctionDefs",
                # "maxInstructionDefs",  # Not supported by htic
                "maxStackElements",
                # "maxSizeOfInstructions",  # Not supported by htic; recalculated by compiler
                "maxZones",
                "maxTwilightPoints",
            ):
                value = ttdata.get(name, None)
                if value is not None:
                    maxp += "%6i %s\n" % (value, name)
        if maxp:
            return "maxp {\n%s}\n" % maxp
        else:
            return "\n"

    def compile_prep(self):
        return self._compile_program("controlValueProgram", "prep")

    def compile(self):
        htic = "\n".join([
            self.compile_flags(),
            self.compile_gasp(),
            self.compile_head(),
            self.compile_maxp(),
            self.compile_cvt(),
            self.compile_fpgm(),
            self.compile_prep(),
            self.compile_glyf()
        ]) + "\n"
        return htic
