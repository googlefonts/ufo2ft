from __future__ import print_function, division, absolute_import
try:
    from inspect import getfullargspec as getargspec  # PY3
except ImportError:
    from inspect import getargspec  # PY2
from copy import deepcopy


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
