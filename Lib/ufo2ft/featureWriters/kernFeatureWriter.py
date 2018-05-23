from __future__ import (
    print_function,
    division,
    absolute_import,
    unicode_literals,
)
from fontTools.misc.py23 import unichr, round, basestring, SimpleNamespace

from fontTools import unicodedata

from ufo2ft.featureWriters import BaseFeatureWriter, ast
from ufo2ft.util import classifyGlyphs


SIDE1_PREFIX = "public.kern1."
SIDE2_PREFIX = "public.kern2."

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


# we consider the 'Common' and 'Inherited' scripts as neutral for
# determining a kerning pair's horizontal direction
DFLT_SCRIPTS = {"Zyyy", "Zinh"}


def unicodeScriptDirection(uv):
    sc = unicodedata.script(unichr(uv))
    if sc in DFLT_SCRIPTS:
        return None
    return unicodedata.script_horizontal_direction(sc)


STRONG_LTR_BIDI_TYPE = "L"
STRONG_RTL_BIDI_TYPES = {"R", "AL"}
LTR_NUMBER_BIDI_TYPES = {"AN", "EN"}


def unicodeBidiType(uv):
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


class KerningPair(object):

    __slots__ = ("side1", "side2", "value", "directions", "bidiTypes")

    def __init__(self, side1, side2, value, directions=None, bidiTypes=None):
        if isinstance(side1, basestring):
            self.side1 = ast.GlyphName(side1)
        elif isinstance(side1, ast.GlyphClassDefinition):
            self.side1 = ast.GlyphClassName(side1)
        else:
            raise AssertionError(side1)

        if isinstance(side2, basestring):
            self.side2 = ast.GlyphName(side2)
        elif isinstance(side2, ast.GlyphClassDefinition):
            self.side2 = ast.GlyphClassName(side2)
        else:
            raise AssertionError(side2)

        self.value = value
        self.directions = directions or set()
        self.bidiTypes = bidiTypes or set()

    @property
    def firstIsClass(self):
        return isinstance(self.side1, ast.GlyphClassName)

    @property
    def secondIsClass(self):
        return isinstance(self.side2, ast.GlyphClassName)

    @property
    def glyphs(self):
        if self.firstIsClass:
            classDef1 = self.side1.glyphclass
            glyphs1 = set(g.asFea() for g in classDef1.glyphSet())
        else:
            glyphs1 = {self.side1.asFea()}
        if self.secondIsClass:
            classDef2 = self.side2.glyphclass
            glyphs2 = set(g.asFea() for g in classDef2.glyphSet())
        else:
            glyphs2 = {self.side2.asFea()}
        return glyphs1 | glyphs2

    def __repr__(self):
        return "<%s %s %s %s%s%s>" % (
            self.__class__.__name__,
            self.side1,
            self.side2,
            self.value,
            " %r" % self.directions if self.directions else "",
            " %r" % self.bidiTypes if self.bidiTypes else "",
        )


class KernFeatureWriter(BaseFeatureWriter):
    """Generates a kerning feature based on groups and rules contained
    in an UFO's kerning data.

    There are currently two possible writing modes:
    1) "append" (default) will add additional lookups to an existing feature,
       if present, or it will add a new one at the end of all features.
    2) "skip" will not write anything if the features are already present;
    """

    tableTag = "GPOS"
    features = frozenset(["kern", "dist"])
    mode = "append"
    options = dict(ignoreMarks=True)

    def setContext(self, font, feaFile, compiler=None):
        ctx = super(KernFeatureWriter, self).setContext(
            font, feaFile, compiler=compiler
        )
        ctx.kerning = self.getKerningData(font, feaFile)

        feaScripts = ast.getScriptLanguageSystems(feaFile)
        ctx.scriptGroups = self._groupScriptsByTagAndDirection(feaScripts)

        return ctx

    def shouldContinue(self):
        if not self.context.kerning.pairs:
            self.log.debug("No kerning data; skipped")
            return False

        if (
            "dist" in self.context.todo
            and "dist" not in self.context.scriptGroups
        ):
            self.log.debug(
                "No dist-enabled scripts defined in languagesystem "
                "statements; dist feature will not be generated"
            )
            self.context.todo.remove("dist")

        return super(KernFeatureWriter, self).shouldContinue()

    def _write(self):
        lookups = self._makeKerningLookups()
        if not lookups:
            self.log.debug("kerning lookups empty; skipped")
            return False

        features = self._makeFeatureBlocks(lookups)
        if not features:
            self.log.debug("kerning features empty; skipped")
            return False

        # extend feature file with the new generated statements
        statements = self.context.feaFile.statements

        # first add the glyph class definitions
        side1Classes = self.context.kerning.side1Classes
        side2Classes = self.context.kerning.side2Classes
        for classes in (side1Classes, side2Classes):
            statements.extend([c for _, c in sorted(classes.items())])

        # add empty line to separate classes from following statements
        if statements:
            statements.append(ast.Comment(""))

        # finally add the lookup and feature blocks
        for _, lookup in sorted(lookups.items()):
            statements.append(lookup)
        if "kern" in features:
            statements.append(features["kern"])
        if "dist" in features:
            statements.append(features["dist"])
        return True

    @classmethod
    def getKerningData(cls, font, feaFile=None):
        side1Classes, side2Classes = cls.getKerningClasses(font, feaFile)
        pairs = cls.getKerningPairs(font, side1Classes, side2Classes)
        return SimpleNamespace(
            side1Classes=side1Classes, side2Classes=side2Classes, pairs=pairs
        )

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
            # skip groups without UFO3 public.kern{1,2} prefix
            if name.startswith(SIDE1_PREFIX):
                side1Groups[name] = members
            elif name.startswith(SIDE2_PREFIX):
                side2Groups[name] = members
        return side1Groups, side2Groups

    @classmethod
    def getKerningClasses(cls, font, feaFile=None):
        side1Groups, side2Groups = cls.getKerningGroups(font)
        side1Classes = ast.makeGlyphClassDefinitions(
            side1Groups, feaFile, stripPrefix="public."
        )
        side2Classes = ast.makeGlyphClassDefinitions(
            side2Groups, feaFile, stripPrefix="public."
        )
        return side1Classes, side2Classes

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
            for side1, side2 in sorted(pairs):
                value = kerning[side1, side2]
                if all(flags) and value == 0:
                    # ignore zero-valued class kern pairs
                    continue
                firstIsClass, secondIsClass = flags
                if firstIsClass:
                    side1 = side1Classes[side1]
                if secondIsClass:
                    side2 = side2Classes[side2]
                result.append(KerningPair(side1, side2, value))
        return result

    def _intersectPairs(self, attribute, glyphSets):
        allKeys = set()
        for pair in self.context.kerning.pairs:
            for key, glyphs in glyphSets.items():
                if not pair.glyphs.isdisjoint(glyphs):
                    getattr(pair, attribute).add(key)
                    allKeys.add(key)
        return allKeys

    @staticmethod
    def _groupScriptsByTagAndDirection(feaScripts):
        # Read scripts/languages defined in feaFile's 'languagesystem'
        # statements and group them by the feature tag (kern or dist)
        # they are associated with, and the global script's horizontal
        # direction (DFLT is excluded)
        scriptGroups = {}
        for scriptCode, scriptLangSys in feaScripts.items():
            direction = unicodedata.script_horizontal_direction(scriptCode)
            if scriptCode in DIST_ENABLED_SCRIPTS:
                tag = "dist"
            else:
                tag = "kern"
            scriptGroups.setdefault(tag, {}).setdefault(direction, []).extend(
                scriptLangSys
            )
        return scriptGroups

    @staticmethod
    def _makePairPosRule(pair, rtl=False):
        enumerated = pair.firstIsClass ^ pair.secondIsClass
        value = round(pair.value)
        if rtl and "N" in pair.bidiTypes:
            # numbers are always shaped LTR even in RTL scripts
            rtl = False
        valuerecord = ast.ValueRecord(
            xPlacement=value if rtl else None,
            yPlacement=0 if rtl else None,
            xAdvance=value,
            yAdvance=0 if rtl else None,
        )
        return ast.PairPosStatement(
            glyphs1=pair.side1,
            valuerecord1=valuerecord,
            glyphs2=pair.side2,
            valuerecord2=None,
            enumerated=enumerated,
        )

    def _makeKerningLookup(self, name, rtl=None):
        pairs = self.context.kerning.pairs
        assert pairs
        rules = []
        for pair in pairs:
            if rtl is not None:
                if "RTL" in pair.directions and "LTR" in pair.directions:
                    self.log.warning(
                        "skipped kern pair with ambiguous direction: %r", pair
                    )
                    continue
                elif "RTL" in pair.directions:
                    if not rtl:
                        self.log.debug(
                            "RTL pair excluded from LTR kern lookup: %r", pair
                        )
                        continue
                elif "LTR" in pair.directions:
                    if rtl:
                        self.log.debug(
                            "LTR pair excluded from RTL kern lookup: %r", pair
                        )
                        continue
                else:
                    assert not pair.directions
                    if rtl:
                        self.log.debug(
                            "kern pair with unknown direction excluded from "
                            "RTL kern lookup: %r",
                            pair,
                        )
                        continue
            rules.append(self._makePairPosRule(pair, rtl=rtl))
        if rules:
            lookup = ast.LookupBlock(name)
            if self.options.ignoreMarks:
                lookup.statements.append(ast.makeLookupFlag("IgnoreMarks"))
            lookup.statements.extend(rules)
            return lookup

    def _makeKerningLookups(self):
        cmap = self.makeUnicodeToGlyphNameMapping()
        if any(unicodeScriptDirection(uv) == "RTL" for uv in cmap):
            # If there are any characters from globally RTL scripts in the
            # cmap, we compile a temporary GSUB table to resolve substitutions
            # and group glyphs by script horizontal direction and bidirectional
            # type. We then mark each kerning pair with these properties when
            # any of the glyphs involved in a pair intersects these groups.
            gsub = self.compileGSUB()
            dirGlyphs = classifyGlyphs(unicodeScriptDirection, cmap, gsub)
            directions = self._intersectPairs("directions", dirGlyphs)
            shouldSplit = "RTL" in directions
            if shouldSplit:
                bidiGlyphs = classifyGlyphs(unicodeBidiType, cmap, gsub)
                self._intersectPairs("bidiTypes", bidiGlyphs)
        else:
            shouldSplit = False

        lookups = {}
        if shouldSplit:
            # make two LTR/RTL lookups excluding pairs from the opposite group
            for rtl in (False, True):
                key = "RTL" if rtl else "LTR"
                lookupName = "kern_" + key.lower()
                lookup = self._makeKerningLookup(lookupName, rtl=rtl)
                if lookup is not None:
                    lookups[key] = lookup
        else:
            # only make a single (implicitly LTR) lookup including all pairs
            lookups["LTR"] = self._makeKerningLookup("kern_ltr")
        return lookups

    def _makeFeatureBlocks(self, lookups):
        features = {}
        if "kern" in self.context.todo:
            kern = ast.FeatureBlock("kern")
            self._registerKernLookups(kern, lookups)
            if kern.statements:
                features["kern"] = kern
        if "dist" in self.context.todo:
            dist = ast.FeatureBlock("dist")
            self._registerDistLookups(dist, lookups)
            if dist.statements:
                features["dist"] = dist
        return features

    def _registerKernLookups(self, feature, lookups):
        scriptGroups = self.context.scriptGroups
        if "dist" in self.context.todo:
            distScripts = scriptGroups["dist"]
        else:
            distScripts = {}
        kernScripts = scriptGroups.get("kern", {})
        ltrScripts = kernScripts.get("LTR", [])
        rtlScripts = kernScripts.get("RTL", [])
        ltrLkp = lookups.get("LTR")
        rtlLkp = lookups.get("RTL")
        if ltrLkp and rtlLkp:
            if ltrScripts and rtlScripts:
                for script, langs in ltrScripts:
                    ast.addLookupReference(feature, ltrLkp, script, langs)
                for script, langs in rtlScripts:
                    ast.addLookupReference(feature, rtlLkp, script, langs)
            elif ltrScripts:
                ast.addLookupReference(feature, rtlLkp, script="DFLT")
                for script, langs in ltrScripts:
                    ast.addLookupReference(feature, ltrLkp, script, langs)
            elif rtlScripts:
                ast.addLookupReference(feature, ltrLkp, script="DFLT")
                for script, langs in rtlScripts:
                    ast.addLookupReference(feature, rtlLkp, script, langs)
            else:
                if not (distScripts.get("LTR") and distScripts.get("RTL")):
                    raise ValueError(
                        "cannot use DFLT script for both LTR and RTL kern "
                        "lookups; add 'languagesystems' to features for at "
                        "least one LTR or RTL script using the kern feature"
                    )
        elif ltrLkp:
            if not (rtlScripts or distScripts):
                ast.addLookupReference(feature, ltrLkp)
            else:
                ast.addLookupReference(feature, ltrLkp, script="DFLT")
                for script, langs in ltrScripts:
                    ast.addLookupReference(feature, ltrLkp, script, langs)
        elif rtlLkp:
            if not (ltrScripts or distScripts):
                ast.addLookupReference(feature, rtlLkp)
            else:
                ast.addLookupReference(feature, rtlLkp, script="DFLT")
                for script, langs in rtlScripts:
                    ast.addLookupReference(feature, rtlLkp, script, langs)
        else:
            raise AssertionError(lookups)

    def _registerDistLookups(self, feature, lookups):
        scripts = self.context.scriptGroups["dist"]
        ltrLkp = lookups.get("LTR")
        if ltrLkp:
            for script, langs in scripts.get("LTR", []):
                ast.addLookupReference(feature, ltrLkp, script, langs)
        rtlLkp = lookups.get("RTL")
        if rtlLkp:
            for script, langs in scripts.get("RTL", []):
                ast.addLookupReference(feature, rtlLkp, script, langs)
