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
from fontTools.ttLib.tables._g_l_y_f import ROUND_XY_TO_GRID, USE_MY_METRICS
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
            formatVersion = ttdata.get("formatVersion", None)
            if int(formatVersion) != 1:
                logger.error(
                    f"Unknown formatVersion {formatVersion} "
                    f"in key '{key}', "
                    f"table '{table_tag}' will be empty in font."
                )
                return
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
            formatVersion = ttdata.get("formatVersion", None)
            if int(formatVersion) != 1:
                logger.error(
                    f"Unknown formatVersion {formatVersion} "
                    f"in key 'controlValue', "
                    f"table 'cvt' will be empty in font."
                )
                return
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

    def compile_glyf(self):
        for name in sorted(self.ufo.keys()):
            glyph = self.ufo[name]
            ttdata = glyph.lib.get(ufoLibKey, None)
            production_name = self.rename_map.get(name, name)
            glyf = self.font["glyf"][production_name]
            if ttdata is not None:
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

                # Compile the glyph program
                asm = ttdata.get("assembly", None)
                if asm is not None:
                    glyf.program = ttLib.tables.ttProgram.Program()
                    glyf.program.fromAssembly(asm)
                    # Roundtrip once, or if the font is dumped to XML before
                    # having been saved, the assembly code if will look awful.
                    glyf.program._assemble()
                    glyf.program._disassemble(preserve=True)

            # Handle composites
            if glyf.isComposite():
                # Remove empty glyph programs from composite glyphs
                if hasattr(glyf, "program") and not glyf.program:
                    delattr(glyf, "program")

                # Recalculate component flags

                # TODO: Take these values from the UFO. See
                # https://github.com/unified-font-object/ufo-spec/issues/93#issuecomment-650253676
                # https://github.com/unified-font-object/ufo-spec/issues/115
                found_metrics = False
                width, _lsb = self.font["hmtx"][name]
                for c in glyf.components:
                    # Reset all flags we will calculate ourselves
                    c.flags &= ~USE_MY_METRICS
                    c.flags &= ~ROUND_XY_TO_GRID

                    # Set ROUND_XY_TO_GRID if the component has an
                    # offset
                    if c.x != 0 or c.y != 0:
                        c.flags |= ROUND_XY_TO_GRID

                    try:
                        _baseName, transform = c.getComponentInfo()
                    except AttributeError:
                        continue
                    try:
                        baseMetrics = self.font["hmtx"][c.glyphName]
                    except KeyError:
                        continue
                    else:
                        # Set USE_MY_METRICS on the first matching
                        # component
                        if (
                            not found_metrics
                            and baseMetrics[0] == width
                            and transform[:-1] == (1, 0, 0, 1, 0)
                        ):
                            c.flags |= USE_MY_METRICS
                            found_metrics = True

    def compile_maxp(self):
        maxp = self.font["maxp"]
        ttdata = self.ufo.lib.get(ufoLibKey, None)
        if ttdata:
            for name in (
                "maxStorage",
                "maxFunctionDefs",
                "maxInstructionDefs",
                "maxStackElements",
                # "maxSizeOfInstructions",  # Is recalculated below
                "maxZones",
                "maxTwilightPoints",
            ):
                value = ttdata.get(name, None)
                if value is not None:
                    setattr(maxp, name, value)

        # Recalculate maxp.maxSizeOfInstructions
        sizes = [
            len(glyph.program.getBytecode())
            for glyph in self.font["glyf"].glyphs.values()
            if hasattr(glyph, "program")
        ] + [0]
        maxp.maxSizeOfInstructions = max(sizes)

    def compile_prep(self):
        self._compile_program("controlValueProgram", "prep")

    def compile(self):
        self.compile_cvt()
        self.compile_fpgm()
        self.compile_prep()
        self.compile_glyf()
        # maxp depends on the other programs, to it needs to be last
        self.compile_maxp()
