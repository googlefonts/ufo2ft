from __future__ import (
    print_function,
    division,
    absolute_import,
    unicode_literals,
)
from fontTools.misc.py23 import unichr, basestring, SimpleNamespace
from fontTools.misc.fixedTools import otRound

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
    # Unicode-11.0 additions
    "Dogr",  # Dogra
    "Gong",  # Gunjala Gondi
    "Maka",  # Makasar
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
    2) "skip" (default) will not write anything if the features are already present;
    1) "append" will add additional lookups to an existing feature, if present,
       or it will add a new one at the end of all features.
    """

    tableTag = "GPOS"
    features = frozenset(["kern", "dist"])
    options = dict(ignoreMarks=True)

    def setContext(self, font, feaFile, compiler=None):
        ctx = super(KernFeatureWriter, self).setContext(
            font, feaFile, compiler=compiler
        )
        ctx.gdefClasses = ast.getGDEFGlyphClasses(feaFile)
        ctx.kerning = self.getKerningData(font, feaFile)
        ctx.scriptGroups = self._groupScriptsByTagAndDirection(feaFile)

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
    def _groupScriptsByTagAndDirection(feaFile):
        # Read scripts/languages defined in feaFile's 'languagesystem'
        # statements and group them by the feature tag (kern or dist)
        # they are associated with, and the global script's horizontal
        # direction (DFLT is excluded)
        feaScripts = ast.getScriptLanguageSystems(feaFile)
        scriptGroups = {}
        tags = ['kern']
        for scriptCode, scriptLangSys in feaScripts.items():
            direction = unicodedata.script_horizontal_direction(scriptCode)
            if scriptCode in DIST_ENABLED_SCRIPTS:
                if 'feature kern' in feaFile.asFea():
                    tags.append('dist')
                else:
                    tags = ['dist']
            for tag in tags:
                scriptGroups.setdefault(tag, {}).setdefault(direction, []).extend(
                    scriptLangSys
            )
        return scriptGroups

    @staticmethod
    def _makePairPosRule(pair, rtl=False):
        enumerated = pair.firstIsClass ^ pair.secondIsClass
        value = otRound(pair.value)
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

    def _makeKerningLookup(self, name, pairs, exclude=None, rtl=False, ignoreMarks=True):
        assert pairs
        rules = []
        for pair in pairs:
            if exclude is not None and exclude(pair):
                self.log.debug(
                    "pair excluded from '%s' lookup: %r", name, pair
                )
                continue
            rules.append(self._makePairPosRule(pair, rtl=rtl))
        if rules:
            lookup = ast.LookupBlock(name)
            if ignoreMarks and self.options.ignoreMarks:
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

        # If there are pairs with a mix of mark/base then the IgnoreMarks
        # flag is unnecessary and should not be set
        base_to_base = []
        base_to_mark = []
        for pair in self.context.kerning.pairs:
            hasMarks = False
            for glyph in pair.side1.glyphSet() + pair.side2.glyphSet():
                if isinstance(glyph, ast.GlyphName):
                    glyph = glyph.glyphSet()[0]
                if self.context.gdefClasses.mark is not None:
                    if glyph in self.context.gdefClasses.mark:
                        hasMarks = True
                        break
            if hasMarks:
                base_to_mark.append(pair)
            else:
                base_to_base.append(pair)

        lookups = {}
        if shouldSplit:
            # make one DFLT lookup with script-agnostic characters, and two
            # LTR/RTL lookups excluding pairs from the opposite group.
            # We drop kerning pairs with ambiguous direction.
            pairs = []
            for pair in self.context.kerning.pairs:
                if "RTL" in pair.directions and "LTR" in pair.directions:
                    self.log.warning(
                        "skipped kern pair with ambiguous direction: %r", pair
                    )
                    continue
                pairs.append(pair)
            if not pairs:
                return lookups

            dfltKern = self._makeKerningLookup(
                "kern_dflt",
                pairs,
                exclude=(
                    lambda pair: bool({"LTR", "RTL"}.intersection(pair.directions))
                                 or pair in base_to_mark
                ),
                rtl=False,
            )
            if dfltKern:
                lookups["DFLT"] = dfltKern

            ltrKern = self._makeKerningLookup(
                "kern_ltr",
                pairs,
                exclude=(
                    lambda pair: (not pair.directions
                    or "RTL" in pair.directions)
                                 or pair in base_to_mark
                ),
                rtl=False,
            )
            if ltrKern:
                lookups["LTR"] = ltrKern

            rtlKern = self._makeKerningLookup(
                "kern_rtl",
                pairs,
                exclude=(
                    lambda pair: (not pair.directions
                    or "LTR" in pair.directions)
                                 or pair in base_to_mark
                ),
                rtl=True,
            )
            if rtlKern:
                lookups["RTL"] = rtlKern

            if base_to_mark:
                dfltKernHasMarks = self._makeKerningLookup(
                    "kern_dflt_marks",
                    pairs,
                    exclude=(
                        lambda pair: bool({"LTR", "RTL"}.intersection(pair.directions))
                                     and pair not in base_to_mark
                    ),
                    rtl=False,
                    ignoreMarks=False,
                )
                if dfltKernHasMarks:
                    lookups["DFLTHasMarks"] = dfltKernHasMarks

                ltrKernHasMarks = self._makeKerningLookup(
                    "kern_ltr_marks",
                    pairs,
                    exclude=(
                        lambda pair: pair not in base_to_mark or (not pair.directions
                        or "RTL" in pair.directions)
                    ),
                    rtl=False,
                    ignoreMarks=False,
                )
                if ltrKernHasMarks:
                    lookups["LTRHasMarks"] = ltrKernHasMarks

                rtlKernHasMarks = self._makeKerningLookup(
                    "kern_rtl_marks",
                    pairs,
                    exclude=(
                        lambda pair: pair not in base_to_mark or (not pair.directions
                        or "LTR" in pair.directions)
                    ),
                    rtl=True,
                    ignoreMarks=False,
                )
                if rtlKernHasMarks:
                    lookups["RTLHasMarks"] = rtlKernHasMarks
        else:
            # only make a single (implicitly LTR) lookup including all base/base pairs
            # and a single lookup including all base/mark pairs if necessary
            lookups["LTR"] = self._makeKerningLookup(
                "kern_ltr",
                self.context.kerning.pairs,
                exclude=(lambda pair: pair in base_to_mark),
            )
            if base_to_mark:
                lookups["LTRHasMarks"] = self._makeKerningLookup(
                    "kern_ltr_marks",
                    self.context.kerning.pairs,
                    exclude=(lambda pair: pair in base_to_base),
                    ignoreMarks=False,
                )
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
        if "DFLT" in lookups:
            ast.addLookupReference(feature, lookups["DFLT"])
        scriptGroups = self.context.scriptGroups
        if "dist" in self.context.todo:
            distScripts = scriptGroups.get("dist")
        else:
            distScripts = {}
        kernScripts = scriptGroups.get("kern", {})
        ltrScripts = kernScripts.get("LTR", [])
        rtlScripts = kernScripts.get("RTL", [])
        ltrLkp = lookups.get("LTR")
        rtlLkp = lookups.get("RTL")
        dfltLkpHasMarks = lookups.get("DFLTHasMarks")
        ltrLkpHasMarks = lookups.get("LTRHasMarks")
        rtlLkpHasMarks = lookups.get("RTLHasMarks")
        ltr_lookups = [ltrLkp]
        rtl_lookups = [rtlLkp]
        if ltrLkpHasMarks is not None:
            ltr_lookups.append(ltrLkpHasMarks)
        if rtlLkpHasMarks is not None:
            rtl_lookups.append(rtlLkpHasMarks)
        if ltrLkp and rtlLkp:
            if ltrScripts and rtlScripts:
                for script, langs in ltrScripts:
                    ast.addLookupReferences(feature, ltr_lookups, script, langs)
                for script, langs in rtlScripts:
                    ast.addLookupReferences(feature, rtl_lookups, script, langs)
            elif ltrScripts:
                ast.addLookupReference(feature, rtlLkp, script="DFLT")
                for script, langs in ltrScripts:
                    ast.addLookupReferences(feature, ltr_lookups, script, langs)
            elif rtlScripts:
                ast.addLookupReference(feature, ltrLkp, script="DFLT")
                for script, langs in rtlScripts:
                    ast.addLookupReferences(feature, rtl_lookups, script, langs)
            else:
                if not (distScripts.get("LTR") and distScripts.get("RTL")):
                    raise ValueError(
                        "cannot use DFLT script for both LTR and RTL kern "
                        "lookups; add 'languagesystems' to features for at "
                        "least one LTR or RTL script using the kern feature"
                    )
        elif ltrLkp:
            if not (rtlScripts or distScripts):
                ast.addLookupReferences(feature, ltr_lookups)
            else:
                ast.addLookupReferences(feature, ltr_lookups, script="DFLT")
                for script, langs in ltrScripts:
                    ast.addLookupReferences(feature, ltr_lookups, script, langs)
        elif rtlLkp:
            if not (ltrScripts or distScripts):
                ast.addLookupReferences(feature, rtl_lookups)
            else:
                ast.addLookupReferences(feature, rtl_lookups, script="DFLT")
                for script, langs in rtlScripts:
                    ast.addLookupReferences(feature, rtl_lookups, script, langs)

    def _registerDistLookups(self, feature, lookups):
        scripts = self.context.scriptGroups.get("dist")
        ltrLkp = lookups.get("LTR")
        if ltrLkp:
            for script, langs in scripts.get("LTR", []):
                ast.addLookupReference(feature, ltrLkp, script, langs)

        ltrLkpHasMarks = lookups.get("LTRHasMarks")
        if ltrLkpHasMarks:
            for script, langs in scripts.get("LTRHasMarks", []):
                ast.addLookupReference(feature, ltrLkpHasMarks, script, langs)
        rtlLkp = lookups.get("RTL")
        if rtlLkp:
            for script, langs in scripts.get("RTL", []):
                ast.addLookupReference(feature, rtlLkp, script, langs)

        rtlLkpHasMarks = lookups.get("RTLHasMarks")
        if rtlLkpHasMarks:
            for script, langs in scripts.get("RTLHasMarks", []):
                ast.addLookupReference(feature, rtlLkpHasMarks, script, langs)
