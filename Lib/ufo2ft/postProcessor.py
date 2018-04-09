from __future__ import print_function, division, absolute_import, unicode_literals

from fontTools.misc.py23 import BytesIO
from fontTools.ttLib import TTFont
import fontTools.agl


UFO2FT_PREFIX = 'com.github.googlei18n.ufo2ft.'


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

        optimizeCFF:
          Run compreffor to subroubtinize CFF table, if present.
        """
        if useProductionNames is None:
            useProductionNames = self.ufo.lib.get(
                UFO2FT_PREFIX + "useProductionNames", True)
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

        if glyph.name == ".null":
            return "uni0000"

        if "." in glyph.name:
            name, rest = glyph.name.split(".", 1)
            rest = "." + rest
        else:
            name, rest = glyph.name, ""

        def name_for_unicode_value(unicode_val):
            agl_match = fontTools.agl.UV2AGL.get(unicode_val)
            if agl_match:
                return agl_match
            else:
                return '%s%04X' % (
                    'u' if unicode_val > 0xffff else 'uni', unicode_val)

        # Try to use the Unicode value first. It it points to an entry in the
        # AGLFN, return the AGLFN name with whatever the glyph name has
        # appended to it (i.e. 'n.case' with the correct Unicode value returns
        # 'n.case'). Otherwise, return a "uniXXXX" or "uXXXXXX" name with
        # whatever the glyph name has appended to it (i.e. 'ie.case' with the
        # correct Unicode value becomes 'uni0435.case')
        unicode_val = glyph.unicode
        if unicode_val is not None:
            return name_for_unicode_value(unicode_val) + rest

        # Otherwise, infer the Unicode value(s) from the base name(s). This
        # helps when e.g. "n" has a Unicode value but "n.case" doesn't. If a
        # component's base glyph doesn't have a Unicode value, just use it
        # verbatim.
        components = []
        for component in name.split("_"):
            if component in self.ufo:
                unicode_val = self.ufo[component].unicode
                if unicode_val:
                    components.append(unicode_val)
                else:
                    components.append(component)  # Might be a helper glyph
            else:
                components.append(component)  # XXX: raise error?

        # If we don't have any AGLFN names and stay within the Unicode BMP, we
        # can compress the name.
        if all(isinstance(v, int) and v <= 0xffff and
               v not in fontTools.agl.UV2AGL for v in components):
            return 'uni' + ''.join('%04X' % v for v in components) + rest
        else:
            return "_".join([name_for_unicode_value(u) if isinstance(u, int)
                             else u
                             for u in components]) + rest
