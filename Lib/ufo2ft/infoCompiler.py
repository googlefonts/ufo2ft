"""
InfoCompiler is used to apply fontinfo overrides to an already compiled font.
This is used to apply fontinfo from a DesignSpace variable-font after merging
font sources into final variable font.

It builds a temporary font with the only the tables that can be modified with
fontinfo, then merge relevant table attributes it into the original font.
"""

import copy

from ufo2ft.outlineCompiler import BaseOutlineCompiler


class InfoCompiler(BaseOutlineCompiler):
    info_tables = frozenset(
        [
            "head",
            "hhea",
            "name",
            "OS/2",
            "post",
            "vhea",
            "gasp",
        ]
    )

    def __init__(self, otf, ufo, info):
        self.orig_otf = otf
        tables = self.info_tables & set(otf.keys())

        # Create a temporary UFO and sets its fontinfo to the union of the main
        # UFO's fontinfo and the DesignSpace variable-font’s info.
        temp_ufo = type(ufo)()
        if hasattr(ufo.info, "getDataForSerialization"):
            # defcon
            data = ufo.info.getDataForSerialization()
            data.update(info)
            temp_ufo.info.setDataFromSerialization(data)
        else:
            # ufoLib2
            temp_ufo.info = copy.copy(ufo.info)
            for k, v in info.items():
                setattr(temp_ufo.info, k, v)

        super().__init__(temp_ufo, tables=tables, glyphSet={}, glyphOrder=[])

    def compile(self):
        super().compile()
        if "gasp" in self.tables:
            self.setupTable_gasp()
        return self.orig_otf

    @staticmethod
    def makeMissingRequiredGlyphs(*args, **kwargs):
        return

    def makeFontBoundingBox(self):
        from ufo2ft.outlineCompiler import EMPTY_BOUNDING_BOX

        return EMPTY_BOUNDING_BOX

    def _set_attrs(self, tag, attrs):
        temp = self.otf[tag]
        orig = self.orig_otf[tag]
        for attr in attrs:
            if (value := getattr(temp, attr, None)) is not None:
                setattr(orig, attr, value)

    def setupTable_head(self):
        super().setupTable_head()
        self._set_attrs(
            "head",
            {
                "fontRevision",
                "unitsPerEm",
                "created",
                "macStyle",
                "flags",
                "lowestRecPPEM",
            },
        )

    def setupTable_hhea(self):
        super().setupTable_hhea()
        self._set_attrs(
            "hhea",
            {
                "ascent",
                "descent",
                "lineGap",
                "caretSlopeRise",
                "caretSlopeRun",
                "caretOffset",
            },
        )

    def setupTable_vhea(self):
        super().setupTable_vhea()
        self._set_attrs(
            "vhea",
            {
                "ascent",
                "descent",
                "lineGap",
                "caretSlopeRise",
                "caretSlopeRun",
                "caretOffset",
            },
        )

    def setupTable_OS2(self):
        super().setupTable_OS2()
        self._set_attrs(
            "OS/2",
            {
                "usWeightClass",
                "usWidthClass",
                "fsType",
                "ySubscriptXSize",
                "ySubscriptYSize",
                "ySubscriptYOffset",
                "ySubscriptXOffset",
                "ySuperscriptXSize",
                "ySuperscriptYSize",
                "ySuperscriptYOffset",
                "ySuperscriptXOffset",
                "yStrikeoutSize",
                "yStrikeoutPosition",
                "sFamilyClass",
                "panose",
                "ulUnicodeRange1",
                "ulUnicodeRange2",
                "ulUnicodeRange3",
                "ulUnicodeRange4",
                "achVendID",
                "fsSelection",
                "sTypoAscender",
                "sTypoDescender",
                "sTypoLineGap",
                "usWinAscent",
                "usWinDescent",
                "ulCodePageRange1",
                "ulCodePageRange2",
                "sxHeight",
                "sCapHeight",
            },
        )

    def setupTable_post(self):
        super().setupTable_post()
        self._set_attrs(
            "post",
            {
                "italicAngle",
                "underlinePosition",
                "underlineThickness",
                "isFixedPitch",
            },
        )

    def setupTable_name(self):
        super().setupTable_name()
        temp = self.otf["name"]
        orig = self.orig_otf["name"]
        temp_names = {
            (n.nameID, n.platformID, n.platEncID, n.langID): n for n in temp.names
        }
        orig_names = {
            (n.nameID, n.platformID, n.platEncID, n.langID): n for n in orig.names
        }
        orig_names.update(temp_names)
        orig.names = list(orig_names.values())

    def setupTable_gasp(self):
        from ufo2ft.instructionCompiler import InstructionCompiler

        instructionCompiler = InstructionCompiler(self.ufo, self.otf)
        instructionCompiler.setupTable_gasp()
        self._set_attrs("gasp", {"gaspRange"})

    def setupTable_maxp(self):
        return
