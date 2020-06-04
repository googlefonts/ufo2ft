from __future__ import print_function, division, absolute_import, unicode_literals

from fontTools.misc.py23 import BytesIO
from fontTools.ttLib import TTFont
from ufo2ft.constants import (
    USE_PRODUCTION_NAMES,
    GLYPHS_DONT_USE_PRODUCTION_NAMES,
    KEEP_GLYPH_NAMES,
)
import enum
import logging
import re


logger = logging.getLogger(__name__)


class CFFVersion(enum.IntEnum):
    CFF = 1
    CFF2 = 2


class PostProcessor(object):
    """Does some post-processing operations on a compiled OpenType font, using
    info from the source UFO where necessary.
    """

    GLYPH_NAME_INVALID_CHARS = re.compile("[^0-9a-zA-Z_.]")
    MAX_GLYPH_NAME_LENGTH = 63

    class SubroutinizerBackend(enum.Enum):
        COMPREFFOR = "compreffor"
        CFFSUBR = "cffsubr"

    # keep defaulting to compreffor for CFF 1.0, use cffsubr for CFF2;
    # can override by passing explicit subroutinizer parameter to process method
    DEFAULT_SUBROUTINIZER_FOR_CFF_VERSION = {
        1: SubroutinizerBackend.COMPREFFOR,
        2: SubroutinizerBackend.CFFSUBR,
    }

    def __init__(self, otf, ufo, glyphSet=None):
        self.ufo = ufo
        self.glyphSet = glyphSet if glyphSet is not None else ufo
        stream = BytesIO()
        otf.save(stream)
        stream.seek(0)
        self.otf = TTFont(stream)
        self._postscriptNames = ufo.lib.get("public.postscriptNames")

    def process(
        self,
        useProductionNames=None,
        optimizeCFF=True,
        cffVersion=None,
        subroutinizer=None,
    ):
        """
        useProductionNames:
          By default, when value is None, this will rename glyphs using the
          'public.postscriptNames' in then UFO lib. If the mapping is not
          present, no glyph names are renamed.
          If the value is False, no glyphs are renamed whether or not the
          'public.postscriptNames' mapping is present.
          If the value is True, but no 'public.postscriptNames' are present,
          then uniXXXX names are generated from the glyphs' unicode.

          The 'com.github.googlei18n.ufo2ft.useProductionNames' key can be set
          in the UFO lib to control this parameter (plist boolean value).

          For legacy reasons, an alias key (with an inverted meaning) is also
          supported: "com.schriftgestaltung.Don't use Production Names";
          when this is present if the UFO lib and is set to True, this is
          equivalent to 'useProductionNames' set to False.

        optimizeCFF:
          Subroubtinize CFF table, if present.
        """
        if self._get_cff_version(self.otf):
            self.process_cff(
                optimizeCFF=optimizeCFF,
                cffVersion=cffVersion,
                subroutinizer=subroutinizer,
            )

        self.process_glyph_names(useProductionNames)

        return self.otf

    def process_cff(self, *, optimizeCFF=True, cffVersion=None, subroutinizer=None):
        cffInputVersion = self._get_cff_version(self.otf)
        if not cffInputVersion:
            raise ValueError("Missing required 'CFF ' or 'CFF2' table")

        if cffVersion is None:
            cffOutputVersion = cffInputVersion
        else:
            cffOutputVersion = CFFVersion(cffVersion)

        if optimizeCFF:
            if subroutinizer is None:
                backend = self.DEFAULT_SUBROUTINIZER_FOR_CFF_VERSION[cffOutputVersion]
            else:
                backend = self.SubroutinizerBackend(subroutinizer)
            self._subroutinize(backend, self.otf, cffOutputVersion)

        elif cffInputVersion != cffOutputVersion:
            if (
                cffInputVersion == CFFVersion.CFF
                and cffOutputVersion == CFFVersion.CFF2
            ):
                self._convert_cff_to_cff2(self.otf)
            else:
                raise NotImplementedError(
                    "Unsupported CFF conversion {cffInputVersion} => {cffOutputVersion}"
                )

    def process_glyph_names(self, useProductionNames=None):
        if useProductionNames is None:
            keepGlyphNames = self.ufo.lib.get(KEEP_GLYPH_NAMES, True)
            useProductionNames = self.ufo.lib.get(
                USE_PRODUCTION_NAMES,
                not self.ufo.lib.get(GLYPHS_DONT_USE_PRODUCTION_NAMES)
                and self._postscriptNames is not None,
            )
        else:
            keepGlyphNames = True

        if keepGlyphNames:
            if "CFF " not in self.otf:
                self.set_post_table_format(self.otf, 2.0)

            if useProductionNames:
                logger.info("Renaming glyphs to final production names")
                self._rename_glyphs_from_ufo()

        else:
            if "CFF " in self.otf:
                logger.warning(
                    "Dropping glyph names from CFF 1.0 is currently unsupported"
                )
            else:
                self.set_post_table_format(self.otf, 3.0)

    def _rename_glyphs_from_ufo(self):
        """Rename glyphs using ufo.lib.public.postscriptNames in UFO."""
        rename_map = self._build_production_names()

        otf = self.otf
        otf.setGlyphOrder([rename_map.get(n, n) for n in otf.getGlyphOrder()])

        # we need to compile format 2 'post' table so that the 'extraNames'
        # attribute is updated with the list of the names outside the
        # standard Macintosh glyph order; otherwise, if one dumps the font
        # to TTX directly before compiling first, the post table will not
        # contain the extraNames.
        if "post" in otf and otf["post"].formatType == 2.0:
            otf["post"].extraNames = []
            otf["post"].compile(otf)

        if "CFF " in otf:
            cff = otf["CFF "].cff.topDictIndex[0]
            char_strings = cff.CharStrings.charStrings
            cff.CharStrings.charStrings = {
                rename_map.get(n, n): v for n, v in char_strings.items()
            }
            cff.charset = [rename_map.get(n, n) for n in cff.charset]

    def _build_production_names(self):
        seen = {}
        rename_map = {}
        for name in self.otf.getGlyphOrder():
            # Ignore glyphs that aren't in the source, as they are usually generated
            # and we lack information about them.
            if name not in self.glyphSet:
                continue
            prod_name = self._build_production_name(self.glyphSet[name])

            # strip invalid characters not allowed in postscript glyph names
            if name != prod_name:
                valid_name = self.GLYPH_NAME_INVALID_CHARS.sub("", prod_name)
                if len(valid_name) > self.MAX_GLYPH_NAME_LENGTH:
                    # if the length of the generated production name is too
                    # long, try to fall back to the original name
                    valid_name = self.GLYPH_NAME_INVALID_CHARS.sub("", name)
            else:
                valid_name = self.GLYPH_NAME_INVALID_CHARS.sub("", name)

            if len(valid_name) > self.MAX_GLYPH_NAME_LENGTH:
                logger.warning(
                    "glyph name length exceeds 63 characters: '%s'", valid_name
                )
            # add a suffix to make the production names unique
            rename_map[name] = self._unique_name(valid_name, seen)
        return rename_map

    @staticmethod
    def _unique_name(name, seen):
        """Append incremental '.N' suffix if glyph is a duplicate."""
        if name in seen:
            n = seen[name]
            while (name + ".%d" % n) in seen:
                n += 1
            seen[name] = n + 1
            name += ".%d" % n
        seen[name] = 1
        return name

    def _build_production_name(self, glyph):
        """Build a production name for a single glyph."""

        # use PostScript names from UFO lib if available
        if self._postscriptNames:
            production_name = self._postscriptNames.get(glyph.name)
            return production_name if production_name else glyph.name

        # use name derived from unicode value
        unicode_val = glyph.unicode
        if glyph.unicode is not None:
            return "%s%04X" % ("u" if unicode_val > 0xFFFF else "uni", unicode_val)

        # use production name + last (non-script) suffix if possible
        parts = glyph.name.rsplit(".", 1)
        if len(parts) == 2 and parts[0] in self.glyphSet:
            return "%s.%s" % (
                self._build_production_name(self.glyphSet[parts[0]]),
                parts[1],
            )

        # use ligature name, making sure to look up components with suffixes
        parts = glyph.name.split(".", 1)
        if len(parts) == 2:
            liga_parts = ["%s.%s" % (n, parts[1]) for n in parts[0].split("_")]
        else:
            liga_parts = glyph.name.split("_")
        if len(liga_parts) > 1 and all(n in self.glyphSet for n in liga_parts):
            unicode_vals = [self.glyphSet[n].unicode for n in liga_parts]
            if all(v and v <= 0xFFFF for v in unicode_vals):
                return "uni" + "".join("%04X" % v for v in unicode_vals)
            return "_".join(
                self._build_production_name(self.glyphSet[n]) for n in liga_parts
            )

        return glyph.name

    @staticmethod
    def set_post_table_format(otf, formatType):
        if formatType not in (2.0, 3.0):
            raise NotImplementedError(formatType)

        post = otf.get("post")
        if post and post.formatType != formatType:
            logger.info("Setting post.formatType = %s", formatType)
            post.formatType = formatType
            if formatType == 2.0:
                post.extraNames = []
                post.mapping = {}
            else:
                for attr in ("extraNames", "mapping"):
                    if hasattr(post, attr):
                        delattr(post, attr)
                post.glyphOrder = None

    @staticmethod
    def _get_cff_version(otf):
        if "CFF " in otf:
            return CFFVersion.CFF
        elif "CFF2" in otf:
            return CFFVersion.CFF2
        else:
            return None

    @staticmethod
    def _convert_cff_to_cff2(otf):
        from fontTools.varLib.cff import convertCFFtoCFF2

        logger.info("Converting CFF table to CFF2")

        # convertCFFtoCFF2 expects a fully decompiled CFF table
        otf["CFF "].cff[0].decompileAllCharStrings()

        # need to decompile glyphOrder, otherwise I get AttribtueError('charset') when
        # running convertCFFtoCFF2(). TODO: Fix it upstream and remove this
        _ = otf.getGlyphOrder()

        convertCFFtoCFF2(otf)

    @classmethod
    def _subroutinize(cls, backend, otf, cffVersion):
        subroutinize = getattr(cls, f"_subroutinize_with_{backend.value}")
        subroutinize(otf, cffVersion)

    @classmethod
    def _subroutinize_with_compreffor(cls, otf, cffVersion):
        from compreffor import compress

        if cls._get_cff_version(otf) != CFFVersion.CFF:
            raise NotImplementedError(
                "Only 'CFF ' 1.0 input is supported by compreffor; try using cffsubr"
            )

        logger.info("Subroutinizing CFF table with compreffor")

        compress(otf)

        if cffVersion == CFFVersion.CFF2:
            cls._convert_cff_to_cff2(otf)

    @classmethod
    def _subroutinize_with_cffsubr(cls, otf, cffVersion):
        import cffsubr

        cffInputVersion = cls._get_cff_version(otf)
        assert cffInputVersion is not None, "Missing required 'CFF ' or 'CFF2' table"

        msg = f"Subroutinizing {cffInputVersion.name} table with cffsubr"
        if cffInputVersion != cffVersion:
            msg += f" (output format: {cffVersion.name})"
        logger.info(msg)

        return cffsubr.subroutinize(otf, cff_version=cffVersion, keep_glyph_names=False)
