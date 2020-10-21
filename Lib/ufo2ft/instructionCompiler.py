# -*- coding: utf-8 -*-
from __future__ import (
    print_function,
    division,
    absolute_import,
    unicode_literals,
)

import array

from fontTools.pens.hashPointPen import HashPointPen
from fontTools import ttLib
from fontTools.ttLib.tables._g_a_s_p import (
    GASP_SYMMETRIC_GRIDFIT,
    GASP_SYMMETRIC_SMOOTHING,
    GASP_DOGRAY,
    GASP_GRIDFIT,
)
from math import log2

import logging


logger = logging.getLogger(__name__)

# Calculate the bit numbers for gasp flags
doGray = log2(GASP_DOGRAY)
doGridfit = log2(GASP_GRIDFIT)
symGridfit = log2(GASP_SYMMETRIC_GRIDFIT)
symSmoothing = log2(GASP_SYMMETRIC_SMOOTHING)


ufoLibKey = "public.truetype.instructions"


class InstructionCompiler(object):
    def __init__(self, ufo, ttf, rename_map={}):
        self.ufo = ufo
        self.font = ttf
        self.rename_map = rename_map

    def _compile_program(self, key, table_tag):
        assert table_tag in ("prep", "fpgm")
        ttdata = self.ufo.lib.get(ufoLibKey, None)
        if ttdata:
            asm = ttdata.get(key, None)
            if asm is not None:
                self.font[table_tag] = table = ttLib.newTable(table_tag)
                table.program = ttLib.tables.ttProgram.Program()
                table.program.fromAssembly(asm)
                # Roundtrip once, or if the font is dumped to XML before having
                # been saved, the assembly code if will look awful.
                table.program._assemble()
                table.program._disassemble(preserve=True)

    def compile_cvt(self):
        cvts = []
        ttdata = self.ufo.lib.get(ufoLibKey, None)
        if ttdata:
            cvt_list = ttdata.get("controlValue", None)
            if cvt_list is not None:
                # Convert string keys to int
                cvt_dict = {int(v["id"]): v["value"] for v in cvt_list}
                # Find the maximum cvt index.
                # We can't just use the dict keys because the cvt must be
                # filled consecutively.
                max_cvt = max(cvt_dict.keys())
                # Make value list, filling entries for missing keys with 0
                cvts = [cvt_dict.get(i, 0) for i in range(max_cvt)]

        if cvts:
            # Only write cvt to font if it contains any values
            self.font["cvt "] = cvt = ttLib.newTable("cvt ")
            cvt.values = array.array("h", cvts)

    def compile_fpgm(self):
        self._compile_program("fontProgram", "fpgm")

    def compile_gasp(self):
        gasp = ttLib.newTable("gasp")
        gasp.gaspRange = {}
        uses_symmetric = False
        if hasattr(self.ufo.info, "openTypeGaspRangeRecords"):
            ufo_gasp = self.ufo.info.openTypeGaspRangeRecords
            if ufo_gasp is not None:
                for r in self.ufo.info.openTypeGaspRangeRecords:
                    bits = r["rangeGaspBehavior"]
                    flags = 0
                    if doGridfit in bits:
                        flags |= GASP_GRIDFIT
                    if doGray in bits:
                        flags |= GASP_DOGRAY
                    if symGridfit in bits:
                        flags |= GASP_SYMMETRIC_GRIDFIT
                        uses_symmetric = True
                    if symSmoothing in bits:
                        flags |= GASP_SYMMETRIC_SMOOTHING
                        uses_symmetric = True
                    gasp.gaspRange[r["rangeMaxPPEM"]] = flags

        if gasp.gaspRange:
            # Only write gasp to font if it contains any ranges
            gasp.version = 1 if uses_symmetric else 0
            self.font["gasp"] = gasp

    def compile_glyf(self):
        for name in sorted(self.ufo.keys()):
            glyph = self.ufo[name]
            ttdata = glyph.lib.get(ufoLibKey, None)
            if ttdata is None:
                continue
            else:
                formatVersion = ttdata.get("formatVersion", None)
                if int(formatVersion) != 1:
                    logger.error(
                        f"Unknown formatVersion {formatVersion} "
                        "in glyph '{name}', it will have "
                        "no instructions in font."
                    )
                    continue

                # Check if glyph hash matches the current outlines
                hash_pen = HashPointPen(glyph.width, self.ufo)
                glyph.drawPoints(hash_pen)
                glyph_id = ttdata.get("id", None)
                if glyph_id is None or glyph_id != hash_pen.hash:
                    logger.error(
                        f"Glyph hash mismatch, glyph '{name}' will have "
                        "no instructions in font."
                    )
                    continue

                # Write hti code
                asm = ttdata.get("assembly", None)
                if asm is not None:
                    production_name = self.rename_map.get(name, name)
                    glyf = self.font["glyf"][production_name]
                    glyf.program = ttLib.tables.ttProgram.Program()
                    glyf.program.fromAssembly(asm)
                    # Roundtrip once, or if the font is dumped to XML before
                    # having been saved, the assembly code if will look awful.
                    glyf.program._assemble()
                    glyf.program._disassemble(preserve=True)

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
        self._compile_program("controlValueProgram", "prep")

    def compile(self):
        self.compile_gasp()
        self.compile_head()
        self.compile_maxp()
        self.compile_cvt()
        self.compile_fpgm()
        self.compile_prep()
        self.compile_glyf()
