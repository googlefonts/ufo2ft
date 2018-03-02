from __future__ import print_function, division, absolute_import
try:
    from inspect import getfullargspec as getargspec  # PY3
except ImportError:
    from inspect import getargspec  # PY2
from copy import deepcopy
from fontTools.misc.py23 import tounicode, UnicodeIO
from fontTools import feaLib
import os
import logging


logger = logging.getLogger(__name__)


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


def makeUnicodeToGlyphNameMapping(font, glyphOrder=None):
    """ Make a unicode: glyph name mapping for this glyph set (dict or Font).

    Raises InvalidFontData exception if multiple glyphs are mapped to the
    same unicode codepoint.
    """
    if glyphOrder is None:
        glyphOrder = makeOfficialGlyphOrder(font)
    mapping = {}
    for glyphName in glyphOrder:
        glyph = font[glyphName]
        unicodes = glyph.unicodes
        for uni in unicodes:
            if uni not in mapping:
                mapping[uni] = glyphName
            else:
                from ufo2ft.errors import InvalidFontData
                InvalidFontData(
                    "cannot map '%s' to U+%04X; already mapped to '%s'"
                    % (glyphName, uni, mapping[uni]))
    return mapping


def parseLayoutFeatures(font):
    """ Parse OpenType layout features in the UFO and return a
    feaLib.ast.FeatureFile instance.
    """
    featxt = tounicode(font.features.text or "", "utf-8")
    if not featxt:
        return feaLib.ast.FeatureFile()
    buf = UnicodeIO(featxt)
    # the path is used by the lexer to resolve 'include' statements
    # and print filename in error messages. For the UFO spec, this
    # should be the path of the UFO, not the inner features.fea:
    # https://github.com/unified-font-object/ufo-spec/issues/55
    ufoPath = font.path
    if ufoPath is not None:
        buf.name = ufoPath
    glyphNames = set(font.keys())
    parser = feaLib.parser.Parser(buf, glyphNames)
    try:
        doc = parser.parse()
    except feaLib.error.IncludedFeaNotFound as e:
        if ufoPath and os.path.exists(os.path.join(ufoPath), e.args[0]):
            logger.warning("Please change the file name in the include(...); "
                           "statement to be relative to the UFO itself, "
                           "instead of relative to the 'features.fea' file "
                           "contained in it.")
        raise
    return doc
