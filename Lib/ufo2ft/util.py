# -*- coding: utf-8 -*-
from __future__ import (
    print_function,
    division,
    absolute_import,
    unicode_literals,
)
try:
    from inspect import getfullargspec as getargspec  # PY3
except ImportError:
    from inspect import getargspec  # PY2
from copy import deepcopy
from fontTools.misc.py23 import unichr


def makeOfficialGlyphOrder(font, glyphOrder=None):
    """ Make the final glyph order for 'font'.

    If glyphOrder is None, try getting the font.glyphOrder list.
    If not explicit glyphOrder is defined, sort glyphs alphabetically.

    If ".notdef" glyph is present in the font, force this to always be
    the first glyph (at index 0).
    """
    if glyphOrder is None:
        glyphOrder = getattr(font, "glyphOrder", ())
    names = set(font.keys())
    order = []
    if ".notdef" in names:
        names.remove(".notdef")
        order.append(".notdef")
    for name in glyphOrder:
        if name not in names:
            continue
        names.remove(name)
        order.append(name)
    order.extend(sorted(names))
    return order


def copyGlyphSet(font, layerName=None):
    if layerName is not None:
        layer = font.layers[layerName]
    else:
        layer = font.layers.defaultLayer

    if not len(layer):
        return {}

    # defcon.Glyph doesn't take a name argument, ufoLib2 requires one...
    g = next(iter(layer))
    cls = g.__class__
    if "name" in getargspec(cls.__init__).args:
        def newGlyph(name):
            return cls(name=name)
    else:
        def newGlyph(name):
            g = cls()
            g.name = name
            return g

    # copy everything except unused attributes: 'guidelines', 'note', 'image'
    glyphSet = {}
    for glyph in layer:
        copy = newGlyph(glyph.name)
        copy.width = glyph.width
        copy.height = glyph.height
        copy.unicodes = list(glyph.unicodes)
        copy.anchors = [dict(a) for a in glyph.anchors]
        copy.lib = deepcopy(glyph.lib)
        pointPen = copy.getPointPen()
        glyph.drawPoints(pointPen)
        glyphSet[glyph.name] = copy
    return glyphSet


def calcCodePageRanges(unicodes):
    """ Given a set of Unicode codepoints (integers), calculate the
    corresponding OS/2 CodePage range bits.
    This is a direct translation of FontForge implementation:
    https://github.com/fontforge/fontforge/blob/7b2c074/fontforge/tottf.c#L3158
    """
    codepageRanges = set()

    chars = [unichr(u) for u in unicodes]

    hasAscii = set(range(0x20, 0x7E)).issubset(unicodes)
    hasLineart = "┤" in chars

    for char in chars:
        if char == "Þ" and hasAscii:
            codepageRanges.add(0)           # Latin 1
        elif char == "Ľ" and hasAscii:
            codepageRanges.add(1)           # Latin 2: Eastern Europe
            if hasLineart:
                codepageRanges.add(58)      # Latin 2
        elif char == "Б":
            codepageRanges.add(2)           # Cyrillic
            if "Ѕ" in chars and hasLineart:
                codepageRanges.add(57)      # IBM Cyrillic
            if "╜" in chars and hasLineart:
                codepageRanges.add(49)      # MS-DOS Russian
        elif char == "Ά":
            codepageRanges.add(3)           # Greek
            if hasLineart and "½" in chars:
                codepageRanges.add(48)      # IBM Greek
            if hasLineart and "√" in chars:
                codepageRanges.add(60)      # Greek, former 437 G
        elif char == "İ" and hasAscii:
            codepageRanges.add(4)           # Turkish
            if hasLineart:
                codepageRanges.add(56)      # IBM turkish
        elif char == "א":
            codepageRanges.add(5)           # Hebrew
            if hasLineart and "√" in chars:
                codepageRanges.add(53)      # Hebrew
        elif char == "ر":
            codepageRanges.add(6)           # Arabic
            if "√" in chars:
                codepageRanges.add(51)      # Arabic
            if hasLineart:
                codepageRanges.add(61)      # Arabic; ASMO 708
        elif char == "ŗ" and hasAscii:
            codepageRanges.add(7)           # Windows Baltic
            if hasLineart:
                codepageRanges.add(59)      # MS-DOS Baltic
        elif char == "₫" and hasAscii:
            codepageRanges.add(8)           # Vietnamese
        elif char == "ๅ":
            codepageRanges.add(16)          # Thai
        elif char == "エ":
            codepageRanges.add(17)          # JIS/Japan
        elif char == "ㄅ":
            codepageRanges.add(18)          # Chinese: Simplified chars
        elif char == "ㄱ":
            codepageRanges.add(19)          # Korean wansung
        elif char == "央":
            codepageRanges.add(20)          # Chinese: Traditional chars
        elif char == "곴":
            codepageRanges.add(21)          # Korean Johab
        elif char == "♥" and hasAscii:
            codepageRanges.add(30)          # OEM Character Set
        # TODO: Symbol bit has a special meaning (check the spec), we need
        # to confirm if this is wanted by default.
        # elif unichr(0xF000) <= char <= unichr(0xF0FF):
        #    codepageRanges.add(31)          # Symbol Character Set
        elif char == "þ" and hasAscii and hasLineart:
            codepageRanges.add(54)          # MS-DOS Icelandic
        elif char == "╚" and hasAscii:
            codepageRanges.add(62)          # WE/Latin 1
            codepageRanges.add(63)          # US
        elif hasAscii and hasLineart and "√" in chars:
            if char == "Å":
                codepageRanges.add(50)      # MS-DOS Nordic
            elif char == "é":
                codepageRanges.add(52)      # MS-DOS Canadian French
            elif char == "õ":
                codepageRanges.add(55)      # MS-DOS Portuguese

    if hasAscii and "‰" in chars and "∑" in chars:
        codepageRanges.add(29)              # Macintosh Character Set (US Roman)

    return codepageRanges
