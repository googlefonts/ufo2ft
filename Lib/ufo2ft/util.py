from __future__ import print_function, division, absolute_import


def makeOfficialGlyphOrder(font, glyphOrder=None):
    """ Make the final glyph order for 'font'.

    If glyphOrder is None, try getting the font.glyphOrder list.
    If not explicit glyphOrder is defined, sort glyphs alphabetically.

    If ".notdef" glyph is present in the font, force this to always be
    the first glyph (at index 0).
    """
    if glyphOrder is None:
        glyphOrder = getattr(font, "glyphOrder", ())
    orderedGlyphs = [".notdef"] if ".notdef" in font else []
    for glyphName in glyphOrder:
        if glyphName == ".notdef":
            continue
        if glyphName not in font:
            continue
        orderedGlyphs.append(glyphName)
    orderedGlyphSet = set(orderedGlyphs)
    for glyphName in sorted(font.keys()):
        if glyphName not in orderedGlyphSet:
            orderedGlyphs.append(glyphName)
    return orderedGlyphs
