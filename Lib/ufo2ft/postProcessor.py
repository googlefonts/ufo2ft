from __future__ import print_function, division, absolute_import, unicode_literals

from fontTools.misc.py23 import BytesIO
from fontTools.ttLib import TTFont


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

    def process(self, useProductionNames=True, optimizeCFF=True):
        if useProductionNames:
            self._rename_glyphs_from_ufo()
        if optimizeCFF and 'CFF ' in self.otf:
            from compreffor import compress
            compress(self.otf)
        return self.otf

    def _rename_glyphs_from_ufo(self):
        """Rename glyphs using ufo.lib.public.postscriptNames in UFO."""

        rename_map = {
            g.name: self._build_production_name(g) for g in self.ufo}
        # .notdef may not be present in the original font
        rename_map[".notdef"] = ".notdef"
        rename = lambda names: [rename_map[n] for n in names]

        self.otf.setGlyphOrder(rename(self.otf.getGlyphOrder()))
        if 'CFF ' in self.otf:
            cff = self.otf['CFF '].cff.topDictIndex[0]
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
