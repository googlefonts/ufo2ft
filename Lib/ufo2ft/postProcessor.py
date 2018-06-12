from __future__ import print_function, division, absolute_import, unicode_literals

from fontTools.misc.py23 import BytesIO
from fontTools.ttLib import TTFont
from ufo2ft.maxContextCalc import maxCtxFont
from ufo2ft.constants import (
    USE_PRODUCTION_NAMES,
    GLYPHS_DONT_USE_PRODUCTION_NAMES
)
import logging


logger = logging.getLogger(__name__)


class PostProcessor(object):
    """Does some post-processing operations on a compiled OpenType font, using
    info from the source UFO where necessary.
    """

    def __init__(self, otf, ufo):
        self.ufo = ufo
        stream = BytesIO()
        otf.save(stream)
        stream.seek(0)
        self.otf = TTFont(stream)
        self._postscriptNames = ufo.lib.get('public.postscriptNames')

    def process(self, useProductionNames=None, optimizeCFF=True):
        """
        useProductionNames:
          Rename glyphs using using 'public.postscriptNames' in UFO lib,
          if present. Else, generate uniXXXX names from the glyphs' unicode.

          If 'com.github.googlei18n.ufo2ft.useProductionNames' key in the UFO
          lib is present and is set to False, do not modify the glyph names.

          Alternatively, if "com.schriftgestaltung.Don't use Production Names"
          key is present if the UFO lib, and is set to True, do not modify
          the glyph names.

        optimizeCFF:
          Run compreffor to subroubtinize CFF table, if present.
        """
        if useProductionNames is None:
            useProductionNames = self.ufo.lib.get(
                USE_PRODUCTION_NAMES,
                not self.ufo.lib.get(GLYPHS_DONT_USE_PRODUCTION_NAMES))
        if useProductionNames:
            self._rename_glyphs_from_ufo()
        if optimizeCFF and 'CFF ' in self.otf:
            from compreffor import compress

            logger.info("Subroutinizing CFF table")
            compress(self.otf)
        if 'OS/2' in self.otf:
            self.otf['OS/2'].usMaxContext = maxCtxFont(self.otf)
        return self.otf

    def _rename_glyphs_from_ufo(self):
        """Rename glyphs using ufo.lib.public.postscriptNames in UFO."""

        rename_map = {
            g.name: self._build_production_name(g) for g in self.ufo}
        # .notdef may not be present in the original font
        rename_map[".notdef"] = ".notdef"
        rename = lambda names: [rename_map[n] for n in names]

        otf = self.otf
        otf.setGlyphOrder(rename(otf.getGlyphOrder()))

        # we need to compile format 2 'post' table so that the 'extraNames'
        # attribute is updated with the list of the names outside the
        # standard Macintosh glyph order; otherwise, if one dumps the font
        # to TTX directly before compiling first, the post table will not
        # contain the extraNames.
        if 'post' in otf and otf['post'].formatType == 2.0:
            otf['post'].compile(self.otf)

        if 'CFF ' in otf:
            cff = otf['CFF '].cff.topDictIndex[0]
            char_strings = cff.CharStrings.charStrings
            cff.CharStrings.charStrings = {
                rename_map.get(n, n): v for n, v in char_strings.items()}
            cff.charset = rename(cff.charset)

    def _build_production_name(self, glyph):
        """Build a production name for a single glyph."""

        # use PostScript names from UFO lib if available
        if self._postscriptNames:
            production_name = self._postscriptNames.get(glyph.name)
            return production_name if production_name else glyph.name

        # use name derived from unicode value
        unicode_val = glyph.unicode
        if glyph.unicode is not None:
            return '%s%04X' % (
                'u' if unicode_val > 0xffff else 'uni', unicode_val)

        # use production name + last (non-script) suffix if possible
        parts = glyph.name.rsplit('.', 1)
        if len(parts) == 2 and parts[0] in self.ufo:
            return '%s.%s' % (
                self._build_production_name(self.ufo[parts[0]]), parts[1])

        # use ligature name, making sure to look up components with suffixes
        parts = glyph.name.split('.', 1)
        if len(parts) == 2:
            liga_parts = ['%s.%s' % (n, parts[1]) for n in parts[0].split('_')]
        else:
            liga_parts = glyph.name.split('_')
        if len(liga_parts) > 1 and all(n in self.ufo for n in liga_parts):
            unicode_vals = [self.ufo[n].unicode for n in liga_parts]
            if all(v and v <= 0xffff for v in unicode_vals):
                return 'uni' + ''.join('%04X' % v for v in unicode_vals)
            return '_'.join(
                self._build_production_name(self.ufo[n]) for n in liga_parts)

        return glyph.name
