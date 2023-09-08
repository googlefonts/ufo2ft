from __future__ import annotations

import array
import logging
from typing import TYPE_CHECKING, Optional

from fontTools import ttLib
from fontTools.pens.hashPointPen import HashPointPen
from fontTools.ttLib import newTable
from fontTools.ttLib.tables._g_l_y_f import (
    OVERLAP_COMPOUND,
    ROUND_XY_TO_GRID,
    USE_MY_METRICS,
    flagOverlapSimple,
)

from ufo2ft.constants import (
    OBJECT_LIBS_KEY,
    TRUETYPE_INSTRUCTIONS_KEY,
    TRUETYPE_METRICS_KEY,
    TRUETYPE_OVERLAP_KEY,
    TRUETYPE_ROUND_KEY,
)
from ufo2ft.fontInfoData import intListToNum

if TYPE_CHECKING:
    from fontTools.ttLib.tables._g_l_y_f import Glyph as TTGlyph
    from ufoLib2 import Font, Glyph


logger = logging.getLogger(__name__)


class InstructionCompiler:
    def __init__(
        self, ufo: Font, otf: ttLib.TTFont, autoUseMyMetrics: bool = True
    ) -> None:
        self.ufo = ufo
        self.otf = otf
        if not autoUseMyMetrics:
            # If autoUseMyMetrics is False, replace the method with a no-op
            self.autoUseMyMetrics = lambda ttGlyph, glyphName: None

    def _check_glyph_hash(
        self, glyphName: str, ttglyph: TTGlyph, glyph_hash: Optional[str]
    ) -> bool:
        """Check if the supplied glyph hash from the ufo matches the current outlines."""
        if glyph_hash is None:
            # The glyph hash is required
            logger.error(
                f"Glyph hash missing, glyph '{glyphName}' will have "
                "no instructions in font."
            )
            return False

        # Check the glyph hash against the TTGlyph that is being built

        ttwidth = self.otf["hmtx"][glyphName][0]
        hash_pen = HashPointPen(ttwidth, self.otf.getGlyphSet())
        ttglyph.drawPoints(hash_pen, self.otf["glyf"])

        if glyph_hash != hash_pen.hash:
            logger.error(
                f"The stored hash for glyph '{glyphName}' does not match the TrueType "
                "output glyph. Glyph will have no instructions in the font."
            )
            return False
        return True

    @staticmethod
    def _check_tt_data_format(ttdata: dict, name: str) -> None:
        """Make sure we understand the format version, currently only version 1
        is supported."""
        formatVersion = ttdata.get("formatVersion", None)
        if not isinstance(formatVersion, str):
            raise TypeError(
                f"Illegal type '{type(formatVersion).__name__}' instead of 'str' for "
                f"formatVersion for instructions in {name}."
            )
        if formatVersion != "1":
            raise NotImplementedError(
                f"Unknown formatVersion {formatVersion} for instructions in {name}."
            )

    def _compile_program(self, key: str, table_tag: str) -> None:
        """Compile the program for prep or fpgm."""
        assert key in ("controlValueProgram", "fontProgram")
        assert table_tag in ("prep", "fpgm")
        ttdata = self.ufo.lib.get(TRUETYPE_INSTRUCTIONS_KEY, None)
        if ttdata:
            self._check_tt_data_format(ttdata, f"lib key '{key}'")
            asm = ttdata.get(key, None)
            if asm is None:
                # The optional key is not there, quit right here
                return
            if not asm:
                # If assembly code is empty, don't bother to add the table
                logger.debug(
                    f"Assembly for table '{table_tag}' is empty, "
                    "table not added to font."
                )
                return

            self.otf[table_tag] = table = ttLib.newTable(table_tag)
            table.program = ttLib.tables.ttProgram.Program()
            table.program.fromAssembly(asm.splitlines())

    def compileGlyphInstructions(self, ttGlyph, name) -> None:
        """Compile the glyph instructions from the UFO glyph `name` to bytecode
        and add it to `ttGlyph`."""
        if name not in self.ufo:
            # Skip glyphs that are not in the UFO; no need to inform about '.notdef'
            # since that glyph is often auto-generated
            if name != ".notdef":
                logger.info(
                    f"Skipping compilation of instructions for glyph '{name}' because it "
                    "is not in the input UFO."
                )
            return

        glyph = self.ufo[name]
        ttdata = glyph.lib.get(TRUETYPE_INSTRUCTIONS_KEY, None)
        if ttdata is not None:
            self._compile_tt_glyph_program(glyph, ttGlyph, ttdata)
        if ttGlyph.isComposite():
            self._set_composite_flags(glyph, ttGlyph)
        else:
            self._set_simple_flags(glyph, ttGlyph)

    def _compile_tt_glyph_program(
        self, glyph: Glyph, ttglyph: TTGlyph, ttdata: dict
    ) -> None:
        self._check_tt_data_format(ttdata, f"glyph '{glyph.name}'")
        glyph_hash = ttdata.get("id", None)
        if not self._check_glyph_hash(glyph.name, ttglyph, glyph_hash):
            return

        # Compile the glyph program
        asm = ttdata.get("assembly", None)
        if asm is None:
            # The "assembly" key is required.
            logger.error(
                f"Glyph assembly missing, glyph '{glyph.name}' will have "
                "no instructions in font."
            )
            return

        if not asm:
            # If the assembly code is empty, don't bother adding a program
            logger.debug(f"Glyph '{glyph.name}' has no instructions.")
            return

        ttglyph.program = ttLib.tables.ttProgram.Program()
        ttglyph.program.fromAssembly(asm.splitlines())

    def autoUseMyMetrics(self, ttGlyph, glyphName):
        """Set the "USE_MY_METRICS" flag on the first component having the
        same advance width as the composite glyph, no transform and no
        horizontal shift (but allow it to shift vertically).
        This forces the composite glyph to use the possibly hinted horizontal
        metrics of the sub-glyph, instead of those from the "hmtx" table.
        """
        hmtx = self.otf["hmtx"]
        width = hmtx[glyphName][0]
        for component in ttGlyph.components:
            try:
                baseName, transform = component.getComponentInfo()
            except AttributeError:
                # component uses '{first,second}Pt' instead of 'x' and 'y'
                continue
            try:
                baseMetrics = hmtx[baseName]
            except KeyError:
                continue  # ignore missing components
            else:
                if baseMetrics[0] == width and transform[:-1] == (1, 0, 0, 1, 0):
                    component.flags |= USE_MY_METRICS
                    break

    def _set_composite_flags(self, glyph: Glyph, ttglyph: TTGlyph) -> None:
        # Set component flags

        if len(ttglyph.components) != len(glyph.components):
            # May happen if nested components have been flattened by a filter
            logger.debug(
                "Number of components differ between UFO and TTF "
                f"in glyph '{glyph.name}' ({len(glyph.components)} vs. "
                f"{len(ttglyph.components)}, not setting component flags from UFO."
            )
            self.autoUseMyMetrics(ttglyph, glyph.name)
            return

        # We need to decide when to set the flags.
        # Let's assume if any lib key is not there, or the component
        # doesn't have an identifier, we should leave the flags alone.

        # Keep track of which component has the USE_MY_METRICS flag
        # and whether any component lib contains the useMyMetrics key
        use_my_metrics_comp = None
        lib_contains_use_my_metrics_key = False

        for i, c in enumerate(ttglyph.components):
            # Set OVERLAP_COMPOUND on the first component only
            if i == 0 and TRUETYPE_OVERLAP_KEY in glyph.lib:
                if glyph.lib.get(TRUETYPE_OVERLAP_KEY, False):
                    c.flags |= OVERLAP_COMPOUND
                else:
                    c.flags &= ~OVERLAP_COMPOUND

            # Check if we have information about the current component in the glyph lib
            ufo_component_id = glyph.components[i].identifier
            if ufo_component_id is None:
                # No information about component flags is stored in the UFO.
                # We don’t modify the flags. Two flags are being set elsewhere:
                # - ROUND_XY_TO_GRID has already been set in TTGlyphPointPen.glyph()
                #                    called from OutlineTTFCompiler.compileGlyphs()
                # - USE_MY_METRICS   is set automatically below if no component has it
                continue

            if (
                OBJECT_LIBS_KEY in glyph.lib
                and ufo_component_id in glyph.lib[OBJECT_LIBS_KEY]
                and (
                    TRUETYPE_ROUND_KEY in glyph.lib[OBJECT_LIBS_KEY][ufo_component_id]
                    or TRUETYPE_METRICS_KEY
                    in glyph.lib[OBJECT_LIBS_KEY][ufo_component_id]
                )
            ):
                component_lib = glyph.lib[OBJECT_LIBS_KEY][ufo_component_id]

                # ROUND_XY_TO_GRID

                # https://github.com/googlefonts/ufo2ft/pull/425 recommends
                # to always set the ROUND_XY_TO_GRID flag, so we only
                # unset it if explicitly done so in the lib
                if not component_lib.get(TRUETYPE_ROUND_KEY, True):
                    c.flags &= ~ROUND_XY_TO_GRID

                # USE_MY_METRICS
                if component_lib.get(TRUETYPE_METRICS_KEY, False):
                    if use_my_metrics_comp is None:
                        c.flags |= USE_MY_METRICS
                        use_my_metrics_comp = ufo_component_id
                    else:
                        logger.debug(
                            f"Ignoring USE_MY_METRICS flag on component {i}, "
                            f"'{ufo_component_id}' because it has been set on "
                            f"component '{use_my_metrics_comp}' already "
                            f"in glyph {glyph.name}."
                        )
                        c.flags &= ~USE_MY_METRICS
                else:
                    c.flags &= ~USE_MY_METRICS
                lib_contains_use_my_metrics_key |= TRUETYPE_METRICS_KEY in component_lib

        # If no UFO component has the 'public.truetype.useMyMetrics' key defined
        # we try to automatically set it
        if not lib_contains_use_my_metrics_key:
            self.autoUseMyMetrics(ttglyph, glyph.name)

    def _set_simple_flags(self, glyph: Glyph, ttglyph: TTGlyph) -> None:
        # Set simple glyph flags

        if ttglyph.numberOfContours < 1 or not ttglyph.flags:
            return

        # Set OVERLAP_SIMPLE
        if TRUETYPE_OVERLAP_KEY in glyph.lib:
            if glyph.lib[TRUETYPE_OVERLAP_KEY]:
                ttglyph.flags[0] |= flagOverlapSimple
            else:
                ttglyph.flags[0] &= ~flagOverlapSimple

    def update_maxp(self) -> None:
        """Update the maxp table with relevant values from the UFO and compiled
        font.
        """
        maxp = self.otf["maxp"]
        ttdata = self.ufo.lib.get(TRUETYPE_INSTRUCTIONS_KEY, None)
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
            len(ttglyph.program.getBytecode())
            for ttglyph in self.otf["glyf"].glyphs.values()
            if hasattr(ttglyph, "program")
        ]
        maxp.maxSizeOfInstructions = max(sizes, default=0)

    def setupTable_cvt(self) -> None:
        """Make the cvt table."""
        cvts = []
        ttdata = self.ufo.lib.get(TRUETYPE_INSTRUCTIONS_KEY, None)
        if ttdata:
            self._check_tt_data_format(ttdata, "key 'controlValue'")
            cvt_dict = ttdata.get("controlValue", None)
            if cvt_dict:
                # Convert string keys to int
                cvt_dict = {int(k): v for k, v in cvt_dict.items()}
                # Find the maximum cvt index.
                # We can't just use the dict keys because the cvt must be
                # filled consecutively.
                max_cvt = max(cvt_dict.keys())
                # Make value list, filling entries for missing keys with 0
                cvts = [cvt_dict.get(i, 0) for i in range(max_cvt + 1)]

        if cvts:
            # Only write cvt to font if it contains any values
            self.otf["cvt "] = cvt = newTable("cvt ")
            cvt.values = array.array("h", cvts)

    def setupTable_fpgm(self) -> None:
        self._compile_program("fontProgram", "fpgm")

    def setupTable_gasp(self):
        if not self.ufo.info.openTypeGaspRangeRecords:
            return

        self.otf["gasp"] = gasp = newTable("gasp")
        gasp_ranges = dict()
        for record in self.ufo.info.openTypeGaspRangeRecords:
            rangeMaxPPEM = record["rangeMaxPPEM"]
            behavior_bits = record["rangeGaspBehavior"]
            rangeGaspBehavior = intListToNum(behavior_bits, 0, 4)
            gasp_ranges[rangeMaxPPEM] = rangeGaspBehavior
        gasp.gaspRange = gasp_ranges

    def setupTable_prep(self) -> None:
        self._compile_program("controlValueProgram", "prep")
