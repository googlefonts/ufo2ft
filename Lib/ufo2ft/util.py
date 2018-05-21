from __future__ import print_function, division, absolute_import

try:
    from inspect import getfullargspec as getargspec  # PY3
except ImportError:
    from inspect import getargspec  # PY2
from copy import deepcopy
from fontTools import ttLib
from fontTools import subset
from fontTools.feaLib.builder import addOpenTypeFeatures
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
                    % (glyphName, uni, mapping[uni])
                )
    return mapping


def compileGSUB(featureFile, glyphOrder):
    """ Compile and return a GSUB table from `featureFile` (feaLib
    FeatureFile), using the given `glyphOrder` (list of glyph names).
    """
    font = ttLib.TTFont()
    font.setGlyphOrder(glyphOrder)
    addOpenTypeFeatures(font, featureFile, tables={"GSUB"})
    return font.get("GSUB")


def closeGlyphsOverGSUB(gsub, glyphs):
    """ Use the FontTools subsetter to perform a closure over the GSUB table
    given the initial `glyphs` (set of glyph names, str). Update the set
    in-place adding all the glyph names that can be reached via GSUB
    substitutions from this initial set.
    """
    subsetter = subset.Subsetter()
    subsetter.glyphs = glyphs
    gsub.closure_glyphs(subsetter)


def classifyGlyphs(unicodeFunc, cmap, gsub=None):
    """ 'unicodeFunc' is a callable that takes a Unicode codepoint and
    returns a string denoting some Unicode property associated with the
    given character (or None if a character is considered 'neutral').
    'cmap' is a dictionary mapping Unicode codepoints to glyph names.
    'gsub' is an (optional) fonttools GSUB table object, used to find all
    the glyphs that are "reachable" via substitutions from the initial
    sets of glyphs defined in the cmap.

    Returns a dictionary of glyph sets associated with the given Unicode
    properties.
    """
    glyphSets = {}
    neutralGlyphs = set()
    for uv, glyphName in cmap.items():
        key = unicodeFunc(uv)
        if key is None:
            neutralGlyphs.add(glyphName)
        else:
            glyphSets.setdefault(key, set()).add(glyphName)

    if gsub is not None:
        if neutralGlyphs:
            closeGlyphsOverGSUB(gsub, neutralGlyphs)

        for glyphs in glyphSets.values():
            s = glyphs | neutralGlyphs
            closeGlyphsOverGSUB(gsub, s)
            glyphs.update(s - neutralGlyphs)

    return glyphSets
