from __future__ import (
    print_function, division, absolute_import, unicode_literals
)
from fontTools.misc.py23 import unichr, round

from fontTools import unicodedata
from fontTools.feaLib import ast

from ufo2ft.featureWriters import BaseFeatureWriter
from ufo2ft.util import closeGlyphsOverGSUB

import collections
import logging


logger = logging.getLogger(__name__)

SIDE1_PREFIX = "public.kern1."
SIDE2_PREFIX = "public.kern2."

DFLT_SCRIPTS = {"Zyyy", "Zinh"}

# In HarfBuzz the 'dist' feature is automatically enabled for these shapers:
#   src/hb-ot-shape-complex-myanmar.cc
#   src/hb-ot-shape-complex-use.cc
#   src/hb-ot-shape-complex-dist.cc
#   src/hb-ot-shape-complex-khmer.cc
# We derived the list of scripts associated to each dist-enabled shaper from
# `hb_ot_shape_complex_categorize` in src/hb-ot-shape-complex-private.hh
DIST_ENABLED_SCRIPTS = {
    # Indic shaper's scripts
    # Unicode-1.1 additions
    "Beng",  # Bengali
    "Deva",  # Devanagari
    "Gujr",  # Gujarati
    "Guru",  # Gurmukhi
    "Knda",  # Kannada
    "Mlym",  # Malayalam
    "Orya",  # Oriya
    "Taml",  # Tamil
    "Telu",  # Telugu
    # Unicode-3.0 additions
    "Sinh",  # Sinhala

    # Khmer shaper
    "Khmr",  # Khmer

    # Myanmar shaper
    "Mymr",  # Myanmar

    # USE shaper's scripts
    # Unicode-3.2 additions
    "Buhd",  # Buhid
    "Hano",  # Hanunoo
    "Tglg",  # Tagalog
    "Tagb",  # Tagbanwa
    # Unicode-4.0 additions
    "Limb",  # Limbu
    "Tale",  # Tai Le
    # Unicode-4.1 additions
    "Bugi",  # Buginese
    "Khar",  # Kharoshthi
    "Sylo",  # Syloti Nagri
    "Tfng",  # Tifinagh
    # Unicode-5.0 additions
    "Bali",  # Balinese
    # Unicode-5.1 additions
    "Cham",  # Cham
    "Kali",  # Kayah Li
    "Lepc",  # Lepcha
    "Rjng",  # Rejang
    "Saur",  # Saurashtra
    "Sund",  # Sundanese
    # Unicode-5.2 additions
    "Egyp",  # Egyptian Hieroglyphs
    "Java",  # Javanese
    "Kthi",  # Kaithi
    "Mtei",  # Meetei Mayek
    "Lana",  # Tai Tham
    "Tavt",  # Tai Viet
    # Unicode-6.0 additions
    "Batk",  # Batak
    "Brah",  # Brahmi
    # Unicode-6.1 additions
    "Cakm",  # Chakma
    "Shrd",  # Sharada
    "Takr",  # Takri
    # Unicode-7.0 additions
    "Dupl",  # Duployan
    "Gran",  # Grantha
    "Khoj",  # Khojki
    "Sind",  # Khudawadi
    "Mahj",  # Mahajani
    "Modi",  # Modi
    "Hmng",  # Pahawh Hmong
    "Sidd",  # Siddham
    "Tirh",  # Tirhuta
    # Unicode-8.0 additions
    "Ahom",  # Ahom
    "Mult",  # Multani
    # Unicode-9.0 additions
    "Bhks",  # Bhaiksuki
    "Marc",  # Marchen
    "Newa",  # Newa
    # Unicode-10.0 additions
    "Gonm",  # Masaram Gondi
    "Soyo",  # Soyombo
    "Zanb",  # Zanabazar Square
}

PUBLIC_PREFIX = "public."

KerningPair = collections.namedtuple("KerningPair",
                                     "name1 name2 value flags glyphs directions")


class KernFeatureWriter(BaseFeatureWriter):
    """Generates a kerning feature based on groups and rules contained
    in an UFO's kerning data.

    There are currently two possible writing modes:
    1) "append" (default) will add additional lookups to an existing feature,
       if present, or it will add a new one at the end of all features.
    2) "skip" will not write anything if any of the features is already present;
    """

    features = frozenset(["kern", "dist"])
    mode = "append"
    options = dict(
        ignoreMarks=True,
    )

    def _write(self, feaFile):
        ltrLangSyses, rtlLangSyses = self.getLanguageSystems(feaFile)

        font = self.context.font

        cmap = self.makeUnicodeToGlyphNameMapping()
        scriptDirections = self.getCmapScriptHorizontalDirections(cmap)

        side1Groups, side2Groups = self.getKerningGroups(font)
        side1Classes = self.makeGlyphClassDefinitions(side1Groups,
                                                      PUBLIC_PREFIX)
        side2Classes = self.makeGlyphClassDefinitions(side2Groups,
                                                      PUBLIC_PREFIX)

        kerning = self.getKerningPairs(font, side1Classes, side2Classes)

        anyLTR = "LTR" in scriptDirections
        anyRTL = "RTL" in scriptDirections

        # if there's any RTL scripts in the cmap, we attempt to split the
        # kern lookups into LTR and RTL
        if anyRTL:
            gsub = self.compileGSUB(feaFile)
            glyphsByDirection = self.groupGlyphsByDirection(cmap, gsub)
            self.updatePairsDirection(kerning, glyphsByDirection)

        # write the lookup
        ignoreMarks = self.options.ignoreMarks
        if anyLTR or not anyRTL:
            ltrKern = self.makeKerningLookup(
                "kern_ltr", kerning,
                ignoreMarks=ignoreMarks,
                rtl=False)
        else:
            ltrKern = None

        if anyRTL:
            rtlKern = self.makeKerningLookup(
                "kern_rtl", kerning,
                ignoreMarks=ignoreMarks,
                rtl=True)
        else:
            rtlKern = None

        if not (ltrKern or rtlKern):
            # no kerning pairs, don't write empty feature
            return False

        onlyDFLT = not (ltrLangSyses or rtlLangSyses)
        if ltrKern and rtlKern and onlyDFLT:
            raise ValueError(
                "cannot use DFLT script for both LTR and RTL kern lookups; "
                "add 'languagesystems' to feature file and try again")

        kern = ast.FeatureBlock("kern")

        dfltLangSys = {"DFLT": ["dflt"]}

        if ltrKern and rtlKern:
            # register different lookups each under different scripts
            if ltrLangSyses:
                self.addLookupReference(kern, ltrKern, ltrLangSyses)
            elif rtlLangSyses:
                # no LTR languagesystems: use DFLT for LTR kerning
                self.addLookupReference(kern, ltrKern, dfltLangSys)
            else:
                self.addLookupReference(kern, ltrKern)

            if rtlLangSyses:
                self.addLookupReference(kern, rtlKern, rtlLangSyses)
            elif ltrLangSyses:
                # no RTL languagesystems: use DFLT for RTL kerning
                self.addLookupReference(kern, rtlKern, dfltLangSys)
            else:
                self.addLookupReference(kern, rtlKern)

        elif ltrKern:
            self.addLookupReference(kern, ltrKern)
        else:
            self.addLookupReference(kern, rtlKern)

        # extend feature file with the new generated statements
        statements = feaFile.statements

        # add glyph class definitions
        for classes in (side1Classes, side2Classes):
            statements.extend([c for _, c in sorted(classes.items())])

        # add empty line to separate classes from following statements
        if statements:
            statements.append(ast.Comment(""))

        # add the lookup and feature blocks
        if ltrKern:
            statements.append(ltrKern)
        if rtlKern:
            statements.append(rtlKern)

        statements.append(kern)
        return True

    @staticmethod
    def getLanguageSystems(feaFile):
        ltrLangSyses = collections.OrderedDict()
        rtlLangSyses = collections.OrderedDict()
        for ls in [st for st in feaFile.statements
                   if isinstance(st, ast.LanguageSystemStatement)]:
            if ls.script == "DFLT":
                continue
            sc = unicodedata.ot_tag_to_script(ls.script)
            if unicodedata.script_horizontal_direction(sc) == "LTR":
                ltrLangSyses.setdefault(ls.script, []).append(ls.language)
            else:
                rtlLangSyses.setdefault(ls.script, []).append(ls.language)
        return ltrLangSyses, rtlLangSyses

    @staticmethod
    def getCmapScriptHorizontalDirections(cmap):
        directions = set()
        for uv in cmap:
            sc = unicodedata.script(unichr(uv))
            if sc in DFLT_SCRIPTS:
                continue
            directions.add(unicodedata.script_horizontal_direction(sc))
            if len(directions) == 2:
                break
        return directions

    @staticmethod
    def getKerningGroups(font):
        allGlyphs = set(font.keys())
        side1Groups = {}
        side2Groups = {}
        for name, members in font.groups.items():
            # prune non-existent glyphs
            members = [g for g in members if g in allGlyphs]
            if not members:
                # skip empty groups
                continue
            if name.startswith(SIDE1_PREFIX):
                side1Groups[name] = members
            elif name.startswith(SIDE2_PREFIX):
                side2Groups[name] = members
            else:
                # skip groups without UFO3 public.kern{1,2} prefix
                continue
        return side1Groups, side2Groups

    @staticmethod
    def getKerningPairs(font, side1Classes, side2Classes):
        allGlyphs = set(font.keys())
        kerning = font.kerning

        pairsByFlags = {}
        for (side1, side2) in kerning:
            # filter out pairs that reference missing groups or glyphs
            if side1 not in side1Classes and side1 not in allGlyphs:
                continue
            if side2 not in side2Classes and side2 not in allGlyphs:
                continue
            flags = (side1 in side1Classes, side2 in side2Classes)
            pairsByFlags.setdefault(flags, set()).add((side1, side2))

        result = []
        for flags, pairs in sorted(pairsByFlags.items()):
            firstIsClass, secondIsClass = flags
            for side1, side2 in sorted(pairs):
                if firstIsClass:
                    classDef1 = side1Classes[side1]
                    name1 = ast.GlyphClassName(classDef1)
                    glyphs1 = set(classDef1.glyphSet())
                else:
                    name1 = ast.GlyphName(side1)
                    glyphs1 = {side1}

                if secondIsClass:
                    classDef2 = side2Classes[side2]
                    name2 = ast.GlyphClassName(classDef2)
                    glyphs2 = set(classDef2.glyphSet())
                else:
                    name2 = ast.GlyphName(side2)
                    glyphs2 = {side2}

                pair = KerningPair(name1=name1,
                                   name2=name2,
                                   value=kerning[side1, side2],
                                   flags=flags,
                                   glyphs=(glyphs1 | glyphs2),
                                   directions=set())
                result.append(pair)

        return result

    @staticmethod
    def groupGlyphsByDirection(cmap, gsub):
        directions = {}
        for uv, glyphName in cmap.items():
            direction = _getUnicodeDirection(uv)
            directions.setdefault(direction, set()).add(glyphName)

        noDirectionGlyphs = directions.get(None, set())
        if noDirectionGlyphs:
            closeGlyphsOverGSUB(gsub, noDirectionGlyphs)

        for direction, glyphs in directions.items():
            if direction is None:
                continue
            s = glyphs | noDirectionGlyphs
            closeGlyphsOverGSUB(gsub, s)
            glyphs.update(s - noDirectionGlyphs)

        return directions

    @staticmethod
    def updatePairsDirection(kerning, directions):
        for pair in kerning:
            for direction, glyphs in directions.items():
                if direction is None:
                    continue
                if not pair.glyphs.isdisjoint(glyphs):
                    pair.directions.add(direction)
    @staticmethod
    def makeKerningValueRecord(value, rtl=False):
        value = round(value)
        return ast.ValueRecord(xPlacement=value if rtl else None,
                               yPlacement=0 if rtl else None,
                               xAdvance=value,
                               yAdvance=0 if rtl else None)

    @classmethod
    def makePairPosRule(cls, pair, rtl=False):
        firstIsClass, secondIsClass = pair.flags
        enumerated = firstIsClass ^ secondIsClass

        if rtl and "N" in pair.directions:
            # numbers are shaped LTR even in RTL scripts
            rtl = False

        valuerecord = cls.makeKerningValueRecord(pair.value, rtl)

        return ast.PairPosStatement(glyphs1=pair.name1,
                                    valuerecord1=valuerecord,
                                    glyphs2=pair.name2,
                                    valuerecord2=None,
                                    enumerated=enumerated)

    @classmethod
    def makeKerningLookup(cls, name, kerning, ignoreMarks=True,
                          rtl=False):
        rules = []
        for pair in kerning:
            if rtl:
                if pair.directions.isdisjoint({"R", "N"}):
                    continue
            elif "R" in pair.directions:
                continue
            if all(pair.flags) and pair.value == 0:
                # ignore zero-valued class kern pairs
                continue
            rules.append(cls.makePairPosRule(pair, rtl))

        if rules:
            lookup = ast.LookupBlock(name)
            if ignoreMarks:
                lookup.statements.append(cls.makeLookupFlag("IgnoreMarks"))
            lookup.statements.extend(rules)
            return lookup


STRONG_LTR_BIDI_TYPE = "L"
STRONG_RTL_BIDI_TYPES = {"R", "AL"}
LTR_NUMBER_BIDI_TYPES = {"AN", "EN"}


def _getUnicodeDirection(uv):
    # return "R", "L", "N" (for numbers), or None for everything else
    char = unichr(uv)
    bidiType = unicodedata.bidirectional(char)
    if bidiType in STRONG_RTL_BIDI_TYPES:
        return "R"
    elif bidiType == STRONG_LTR_BIDI_TYPE:
        return "L"
    elif bidiType in LTR_NUMBER_BIDI_TYPES:
        return "N"
    else:
        return None
