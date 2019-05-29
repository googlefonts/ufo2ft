# -*- coding: utf-8 -*-
from __future__ import print_function, division, absolute_import, unicode_literals

from fontTools.pens.pointPen import AbstractPointPen
from fontTools.ttLib.tables._g_a_s_p import \
    GASP_SYMMETRIC_GRIDFIT, GASP_SYMMETRIC_SMOOTHING, GASP_DOGRAY, GASP_GRIDFIT
from math import log2

import hashlib
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
      D 1     # Obey minimum distance VTT: >
      d 0     # Do not obey minimum distance VTT: <
     Gr 00    # Gray
     Bl 01    # Black
     Wh 10    # White

  # Combined flags
  mdrGr 00000
  mdrBl 00001
  mdrWh 00010
  mdRGr 00100
  mdRBl 00101
  mdRWh 00110
  mDrGr 01000
  mDrBl 01001
  mDrWh 01010
  mDRGr 01100
  mDRBl 01101
  mDRWh 01110
  MdrGr 10000
  MdrBl 10001
  MdrWh 10010
  MdRGr 10100
  MdRBl 10101
  MdRWh 10110
  MDrGr 11000
  MDrBl 11001
  MDrWh 11010
  MDRGr 11100
  MDRBl 11101
  MDRWh 11110
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
                hti += value
        if hti:
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


# Modified from https://github.com/adobe-type-tools/psautohint/blob/08b346865710ed3c172f1eb581d6ef243b203f99/python/psautohint/ufoFont.py#L800-L838

class HashPointPen(AbstractPointPen):
    DEFAULT_TRANSFORM = (1, 0, 0, 1, 0, 0)

    def __init__(self, glyph, glyphSet=None):
        self.glyphset = glyphSet
        self.width = round(getattr(glyph, "width", 1000), 9)
        self.data = ["w%s" % self.width]

    def getHash(self):
        data = "".join(self.data)
        if len(data) >= 128:
            data = hashlib.sha512(data.encode("ascii")).hexdigest()
        return data

    def beginPath(self, identifier=None, **kwargs):
        pass

    def endPath(self):
        pass

    def addPoint(self, pt, segmentType=None, smooth=False, name=None,
                 identifier=None, **kwargs):
        if segmentType is None:
            pt_type = ""
        else:
            pt_type = segmentType[0]
        self.data.append("%s%s%s" % (pt_type, repr(pt[0]), repr(pt[1])))

    def addComponent(self, baseGlyphName, transformation, identifier=None,
                     **kwargs):
        self.data.append("base:%s" % baseGlyphName)

        for i, v in enumerate(transformation):
            if transformation[i] != self.DEFAULT_TRANSFORM[i]:
                self.data.append(str(round(v, 9)))

        self.data.append("w%s" % self.width)
        glyph = self.glyphset[baseGlyphName]
        glyph.drawPoints(self)
