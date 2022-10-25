from __future__ import annotations

import itertools
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING

from fontTools import unicodedata
from fontTools.feaLib import ast
from fontTools.misc.classifyTools import classify

from ufo2ft.constants import COMMON_SCRIPT, INDIC_SCRIPTS, USE_SCRIPTS
from ufo2ft.featureWriters import BaseFeatureWriter
from ufo2ft.featureWriters.ast import (
    addLookupReferences,
    getScriptLanguageSystems,
    makeGlyphClassDefinition,
    makeGlyphClassDefinitions,
    makeLookupFlag,
)
from ufo2ft.util import DFLT_SCRIPTS, classifyGlyphs, quantize, unicodeScriptDirection

if TYPE_CHECKING:
    from typing import Any, Iterator, Literal, Mapping

SIDE1_PREFIX = "public.kern1."
SIDE2_PREFIX = "public.kern2."

# In HarfBuzz the 'dist' feature is automatically enabled for these shapers:
#   src/hb-ot-shape-complex-myanmar.cc
#   src/hb-ot-shape-complex-use.cc
#   src/hb-ot-shape-complex-indic.cc
#   src/hb-ot-shape-complex-khmer.cc
# We derived the list of scripts associated to each dist-enabled shaper from
# `hb_ot_shape_complex_categorize` in src/hb-ot-shape-complex-private.hh
DIST_ENABLED_SCRIPTS = set(INDIC_SCRIPTS) | {"Khmr", "Mymr"} | set(USE_SCRIPTS)

RTL_BIDI_TYPES = {"R", "AL"}
LTR_BIDI_TYPES = {"L", "AN", "EN"}
COMMON_SCRIPTS_SET = {COMMON_SCRIPT}


def unicodeBidiType(uv: int) -> Literal["R"] | Literal["L"] | None:
    """Return "R" for characters with RTL direction, or "L" for LTR (whether
    'strong' or 'weak'), or None for neutral direction.
    """
    char = chr(uv)
    bidiType = unicodedata.bidirectional(char)
    if bidiType in RTL_BIDI_TYPES:
        return "R"
    elif bidiType in LTR_BIDI_TYPES:
        return "L"
    return None


class KerningPair:

    __slots__ = ("side1", "side2", "value", "scripts", "directions", "bidiTypes")

    def __init__(
        self,
        side1: str
        | ast.GlyphClassDefinition
        | ast.GlyphClass
        | ast.GlyphClassName
        | list[str]
        | set[str],
        side2: str
        | ast.GlyphClassDefinition
        | ast.GlyphClass
        | ast.GlyphClassName
        | list[str]
        | set[str],
        value: float,
        scripts: set[str] | None = None,
        directions: set[str] | None = None,
        bidiTypes: set[str] | None = None,
    ) -> None:
        self.side1: ast.GlyphName | ast.GlyphClassName | ast.GlyphClass
        if isinstance(side1, str):
            self.side1 = ast.GlyphName(side1)
        elif isinstance(side1, ast.GlyphClassDefinition):
            self.side1 = ast.GlyphClassName(side1)
        elif isinstance(side1, (ast.GlyphClass, ast.GlyphClassName)):
            self.side1 = side1
        elif isinstance(side1, (list, set)):
            self.side1 = ast.GlyphClass([ast.GlyphName(g) for g in sorted(side1)])
        else:
            raise AssertionError(side1)

        self.side2: ast.GlyphName | ast.GlyphClassName | ast.GlyphClass
        if isinstance(side2, str):
            self.side2 = ast.GlyphName(side2)
        elif isinstance(side2, ast.GlyphClassDefinition):
            self.side2 = ast.GlyphClassName(side2)
        elif isinstance(side2, (ast.GlyphClass, ast.GlyphClassName)):
            self.side2 = side2
        elif isinstance(side2, (list, set)):
            self.side2 = ast.GlyphClass([ast.GlyphName(g) for g in sorted(side2)])
        else:
            raise AssertionError(side2)

        self.value: float = value
        self.scripts: set[str] = scripts or set()
        self.directions: set[str] = directions or set()
        self.bidiTypes: set[str] = bidiTypes or set()

    def __lt__(self, other: KerningPair) -> bool:
        if not isinstance(other, KerningPair):
            return NotImplemented

        # NOTE: Comparing classes relies on their glyph names being sorted in
        # __init__.
        selfTuple = (
            self.firstIsClass,
            self.secondIsClass,
            self.side1.glyph
            if isinstance(self.side1, ast.GlyphName)
            else self.side1.glyphSet()[0].glyph,
            self.side2.glyph
            if isinstance(self.side2, ast.GlyphName)
            else self.side2.glyphSet()[0].glyph,
        )
        otherTuple = (
            other.firstIsClass,
            other.secondIsClass,
            other.side1.glyph
            if isinstance(other.side1, ast.GlyphName)
            else other.side1.glyphSet()[0].glyph,
            other.side2.glyph
            if isinstance(other.side2, ast.GlyphName)
            else other.side2.glyphSet()[0].glyph,
        )
        return selfTuple < otherTuple

    def __eq__(self, other: KerningPair) -> bool:
        if other.__class__ is not self.__class__:
            return False

        return (
            self.firstIsClass,
            self.secondIsClass,
            self.side1.glyph
            if isinstance(self.side1, ast.GlyphName)
            else {glyph.glyph for glyph in self.side1.glyphSet()},
            self.side2.glyph
            if isinstance(self.side2, ast.GlyphName)
            else {glyph.glyph for glyph in self.side2.glyphSet()},
            self.value,
            self.scripts,
            self.directions,
            self.bidiTypes,
        ) == (
            other.firstIsClass,
            other.secondIsClass,
            other.side1.glyph
            if isinstance(other.side1, ast.GlyphName)
            else {glyph.glyph for glyph in other.side1.glyphSet()},
            other.side2.glyph
            if isinstance(other.side2, ast.GlyphName)
            else {glyph.glyph for glyph in other.side2.glyphSet()},
            other.value,
            other.scripts,
            other.directions,
            other.bidiTypes,
        )

    def partitionByScript(
        self, glyphScripts: Mapping[str, set[str]]
    ) -> Iterator[tuple[str, KerningPair]]:
        """Split a potentially mixed-script pair into pairs that make sense based
        on the dominant script, and yield each combination with its dominant script."""

        # First, partition the pair by their assigned scripts. Glyphs can have
        # multiple scripts assigned to them (legitimately, e.g. U+0951
        # DEVANAGARI STRESS SIGN UDATTA, or for random reasons like having both
        # `sub h by h.sc` and `sub Etaprosgegrammeni by h.sc;`). We duplicate
        # the glyph name into each script bucket because each script gets its
        # own lookup and group membership is exclusive per lookup.
        side1Scripts: dict[str, set[str]] = {}
        side2Scripts: dict[str, set[str]] = {}
        for glyph in self.firstGlyphs:
            for script in glyphScripts.get(glyph, COMMON_SCRIPTS_SET):
                side1Scripts.setdefault(script, set()).add(glyph)
        for glyph in self.secondGlyphs:
            for script in glyphScripts.get(glyph, COMMON_SCRIPTS_SET):
                side2Scripts.setdefault(script, set()).add(glyph)

        # 0. UFO and Glyphs.app sources require that kerning groups are disjoint
        #    per side, which we also assume here.
        # 1. Kerning groups must be disjoint within each pair positioning lookup
        #    (specifically for class-to-class subtables, glyph-to-glyph doesn't
        #    matter here because it has no classes), but can overlap in whatever
        #    way across all pair positioning lookups.
        # 2. Implicit scripts like Zyyy and Zinh take on the explicit script of
        #    the pair (e.g. Latn) and can land in the same lookup as the
        #    explicit script.
        #
        # Example: a Latn,Latn and Latn,Zyyy and Zyyy,Latn pair all end up in
        # the same Latn lookup and a Zyyy,Zyyy pair ends up in the Zyyy lookup.
        #
        # Put all common glyphs into all explicit script buckets that they are
        # kerned against.
        #
        # Example: a pair of `([a, period] [b]: ...)` would have the side1
        # scripts Latn and Zyyy and side2 script Latn. We add period to the Latn
        # script bucket on side1, the code below then sees Latn = {a, period} on
        # side1 and Latn = {b} on side2 and emits that; Zyyy on side1 is ignored
        # because side2 doesn't have it. Effectively, the pair remains unsplit.
        #
        # NOTE: This logic avoids a problem when blindly emitting the product of
        # the scripts of each side and emitting the split groups of explicit and
        # implicit script pairings; I.e. if a glyph for some reason has the
        # scripts Latn and Zyyy associated with it, it is going to be emitted
        # once as part of the Latn group and once of the Zyyy groups, violating
        # the disjointness invariant above.

        # TODO: help, we're generating different script buckets depending on
        # what's on the other side, so we're undermining our determinism and may
        # create overlapping kerning groups in the same lookup...
        for common_script in DFLT_SCRIPTS:
            if common_script in side1Scripts:
                common_glyphs = side1Scripts[common_script]
                for other_script in side2Scripts:  # NOTE: Must look at other side!
                    side1Scripts.setdefault(other_script, set()).update(common_glyphs)
            if common_script in side2Scripts:
                common_glyphs = side2Scripts[common_script]
                for other_script in side1Scripts:  # NOTE: Must look at other side!
                    side2Scripts.setdefault(other_script, set()).update(common_glyphs)

        # Super common case: both sides are of the same, one script. Nothing to do, emit
        # self as is.
        # TODO: remove this special casing?
        if len(side1Scripts.keys()) == 1 and side1Scripts.keys() == side2Scripts.keys():
            (onlyScript,) = side1Scripts.keys()
            yield onlyScript, self
            return

        # TODO: Do we want to warn the user about dropped mixed split pairs
        # (e.g. accidental Latn against Grek)? Kerning groups might be set up by
        # glyph shape rather than script semantics, in which case it is expected
        # that some entries are going to be dropped. Other users might be
        # scratching their heads why their specific pair doesn't work? Or this
        # would be untestable because we just implement shaping rules? The
        # design application seems like a better place for this kind of check...
        shared_scripts = side1Scripts.keys() & side2Scripts
        for script in shared_scripts:
            firstGlyphs = side1Scripts[script]
            secondGlyphs = side2Scripts[script]

            # Preserve the type (glyph or class) of each side.
            if self.firstIsClass:
                localSide1: str | list[str] = sorted(firstGlyphs)
            else:
                assert len(firstGlyphs) == 1
                (localSide1,) = firstGlyphs
            if self.secondIsClass:
                localSide2: str | list[str] = sorted(secondGlyphs)
            else:
                assert len(secondGlyphs) == 1
                (localSide2,) = secondGlyphs
            localPair = KerningPair(
                localSide1,
                localSide2,
                self.value,
                scripts=self.scripts,
                directions=self.directions,
                bidiTypes=self.bidiTypes,
            )

            localPair.scripts = {script}
            yield script, localPair

    @property
    def firstIsClass(self) -> bool:
        return isinstance(self.side1, (ast.GlyphClassName, ast.GlyphClass))

    @property
    def secondIsClass(self) -> bool:
        return isinstance(self.side2, (ast.GlyphClassName, ast.GlyphClass))

    @property
    def firstGlyphs(self) -> set[str]:
        if self.firstIsClass:
            if isinstance(self.side1, ast.GlyphClassName):
                classDef1 = self.side1.glyphclass
            else:
                classDef1 = self.side1
            return {g.asFea() for g in classDef1.glyphSet()}
        else:
            return {self.side1.asFea()}

    @property
    def secondGlyphs(self) -> set[str]:
        if self.secondIsClass:
            if isinstance(self.side2, ast.GlyphClassName):
                classDef2 = self.side2.glyphclass
            else:
                classDef2 = self.side2
            return {g.asFea() for g in classDef2.glyphSet()}
        else:
            return {self.side2.asFea()}

    @property
    def glyphs(self) -> set[str]:
        return self.firstGlyphs | self.secondGlyphs

    def __repr__(self) -> str:
        return "<{} {} {} {}{}{}{}>".format(
            self.__class__.__name__,
            self.side1,
            self.side2,
            self.value,
            " %r" % self.directions if self.directions else "",
            " %r" % self.scripts if self.scripts else "",
            " %r" % self.bidiTypes if self.bidiTypes else "",
        )


class KernFeatureWriter(BaseFeatureWriter):
    """Generates a kerning feature based on groups and rules contained
    in an UFO's kerning data.

    There are currently two possible writing modes:
    2) "skip" (default) will not write anything if the features are already present;
    1) "append" will add additional lookups to an existing feature, if present,
       or it will add a new one at the end of all features.

    If the `quantization` argument is given in the filter options, the resulting
    anchors are rounded to the nearest multiple of the quantization value.
    """

    tableTag = "GPOS"
    features = frozenset(["kern", "dist"])
    options = dict(ignoreMarks=True, quantization=1)

    def setContext(self, font, feaFile, compiler=None):
        ctx = super().setContext(font, feaFile, compiler=compiler)
        ctx.gdefClasses = self.getGDEFGlyphClasses()
        ctx.kerning = self.getKerningData(font, feaFile, self.getOrderedGlyphSet())

        feaScripts = getScriptLanguageSystems(feaFile)
        ctx.scriptGroups = self._groupScriptsByTagAndDirection(feaScripts)
        ctx.knownScripts = feaScripts.keys()

        # TODO: Also include substitution information from Designspace rules to
        # correctly the scripts of variable substitution glyphs, maybe add
        # `glyphUnicodeMapping: dict[str, int] | None` to `BaseFeatureCompiler`?
        cmap = self.makeUnicodeToGlyphNameMapping()
        gsub = self.compileGSUB()
        dirGlyphs = classifyGlyphs(unicodeScriptDirection, cmap, gsub)
        self._intersectPairs("directions", dirGlyphs)
        scriptGlyphs = classifyGlyphs(script_extensions_for_codepoint, cmap, gsub)
        self._intersectPairs("scripts", scriptGlyphs)
        bidiGlyphs = classifyGlyphs(unicodeBidiType, cmap, gsub)
        self._intersectPairs("bidiTypes", bidiGlyphs)
        glyphScripts = {}
        for script, glyphs in scriptGlyphs.items():
            for g in glyphs:
                glyphScripts.setdefault(g, set()).add(script)
        ctx.glyphScripts = glyphScripts

        return ctx

    def shouldContinue(self):
        if not self.context.kerning.pairs:
            self.log.debug("No kerning data; skipped")
            return False

        if "dist" in self.context.todo and "dist" not in self.context.scriptGroups:
            self.log.debug(
                "No dist-enabled scripts defined in languagesystem "
                "statements; dist feature will not be generated"
            )
            self.context.todo.remove("dist")

        return super().shouldContinue()

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
        feaFile = self.context.feaFile

        # first add the glyph class definitions
        side1Classes = self.context.kerning.newClass1Defs
        side2Classes = self.context.kerning.newClass2Defs
        newClassDefs = []
        for classes in (side1Classes, side2Classes):
            newClassDefs.extend([c for _, c in sorted(classes.items())])

        lookupGroups = []
        for _, lookupGroup in sorted(lookups.items()):
            lookupGroups.extend(lookupGroup.values())

        self._insert(
            feaFile=feaFile,
            classDefs=newClassDefs,
            lookups=lookupGroups,
            features=[features[tag] for tag in ["kern", "dist"] if tag in features],
        )
        return True

    @classmethod
    def getKerningData(cls, font, feaFile=None, glyphSet=None):
        side1Classes, side2Classes = cls.getKerningClasses(font, feaFile, glyphSet)
        pairs = cls.getKerningPairs(font, side1Classes, side2Classes, glyphSet)
        return SimpleNamespace(
            side1Classes=side1Classes, side2Classes=side2Classes, pairs=pairs
        )

    @staticmethod
    def getKerningGroups(font, glyphSet=None):
        if glyphSet:
            allGlyphs = set(glyphSet.keys())
        else:
            allGlyphs = set(font.keys())
        side1Groups = {}
        side2Groups = {}
        for name, members in font.groups.items():
            # prune non-existent or skipped glyphs
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
    def getKerningClasses(cls, font, feaFile=None, glyphSet=None):
        side1Groups, side2Groups = cls.getKerningGroups(font, glyphSet)
        side1Classes = makeGlyphClassDefinitions(
            side1Groups, feaFile, stripPrefix="public."
        )
        side2Classes = makeGlyphClassDefinitions(
            side2Groups, feaFile, stripPrefix="public."
        )
        return side1Classes, side2Classes

    @staticmethod
    def getKerningPairs(
        font: Any,
        side1Classes: Mapping[str, ast.GlyphClassDefinition],
        side2Classes: Mapping[str, ast.GlyphClassDefinition],
        glyphSet: dict[str, Any] | None = None,
    ) -> list[KerningPair]:
        if glyphSet:
            allGlyphs = set(glyphSet.keys())
        else:
            allGlyphs = set(font.keys())
        kerning = font.kerning

        # XXX: stop sorting here, we split later

        # Sort Kerning pairs so that glyph to glyph comes first, then glyph to
        # class, class to glyph, and finally class to class. This makes "kerning
        # exceptions" work, where more specific glyph pair values override less
        # specific class kerning.
        pairsByFlags: dict[tuple[bool, bool], set[tuple[str, str]]] = {}
        for (side1, side2) in kerning:
            # filter out pairs that reference missing groups or glyphs
            if side1 not in side1Classes and side1 not in allGlyphs:
                continue
            if side2 not in side2Classes and side2 not in allGlyphs:
                continue
            flags = (side1 in side1Classes, side2 in side2Classes)
            pairsByFlags.setdefault(flags, set()).add((side1, side2))

        result: list[KerningPair] = []
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
            if scriptCode:
                direction = unicodedata.script_horizontal_direction(scriptCode)
            else:
                direction = "LTR"
            if scriptCode in DIST_ENABLED_SCRIPTS:
                tag = "dist"
            else:
                tag = "kern"
            scriptGroups.setdefault(tag, {}).setdefault(direction, []).extend(
                scriptLangSys
            )
        return scriptGroups

    # TODO: make this a method on KerningPair and do the quantization earlier,
    # so we can drop the parameter
    @staticmethod
    def _makePairPosRule(pair, rtl=False, quantization=1):
        enumerated = pair.firstIsClass ^ pair.secondIsClass
        value = quantize(pair.value, quantization)
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

    def _makeKerningLookups(self) -> dict[str, dict[str, ast.LookupBlock]]:
        lookups: dict[str, dict[str, ast.LookupBlock]] = {}
        glyphScripts = self.context.glyphScripts
        pairs = self.context.kerning.pairs
        if self.options.ignoreMarks:
            marks = self.context.gdefClasses.mark
            basePairs, markPairs = self._splitBaseAndMarkPairs(pairs, marks)
            if basePairs:
                self._makeSplitScriptKernLookups(lookups, basePairs, glyphScripts)
            if markPairs:
                self._makeSplitScriptKernLookups(
                    lookups, markPairs, glyphScripts, ignoreMarks=False, suffix="_marks"
                )
        else:
            self._makeSplitScriptKernLookups(lookups, pairs, glyphScripts)
        return lookups

    def _splitBaseAndMarkPairs(self, pairs, marks):
        basePairs, markPairs = [], []
        if marks:
            for pair in pairs:
                if any(glyph in marks for glyph in pair.glyphs):
                    markPairs.append(pair)
                else:
                    basePairs.append(pair)
        else:
            basePairs[:] = pairs
        return basePairs, markPairs

    def _makeSplitScriptKernLookups(
        self,
        lookups: dict[str, dict[str, ast.LookupBlock]],
        pairs: list[KerningPair],
        glyphScripts: Mapping[str, set[str]],
        ignoreMarks: bool = True,
        suffix: str = "",
    ) -> None:
        # Split kerning into per-script buckets, so we can post-process them
        # before continuing.
        # newKern1: dict[str, ast.GlyphClassDefinition] = {}
        newClass1Defs: dict[str, ast.GlyphClassDefinition] = {}
        newClass2Defs: dict[str, ast.GlyphClassDefinition] = {}
        kerning_per_script: dict[str, list[KerningPair]] = {}
        for pair in pairs:
            for script, split_pair in pair.partitionByScript(glyphScripts):
                kerning_per_script.setdefault(script, []).append(split_pair)
                # capture_split_groups(
                #     pair, split_pair, script, newClass1Defs, newClass2Defs
                # )
                if pair.firstIsClass:
                    assert isinstance(pair.side1, ast.GlyphClassName)
                    group_name_stem = pair.side1.glyphclass.name.replace("kern1.", "")
                    new_group_name = f"kern1.{script}.{group_name_stem}"
                    classDef = makeGlyphClassDefinition(
                        new_group_name,
                        sorted(name.glyph for name in split_pair.side1.glyphSet()),
                    )
                    split_pair.side1 = ast.GlyphClassName(classDef)
                    newClass1Defs[new_group_name] = classDef
                if pair.secondIsClass:
                    assert isinstance(pair.side2, ast.GlyphClassName)
                    group_name_stem = pair.side2.glyphclass.name.replace("kern2.", "")
                    new_group_name = f"kern2.{script}.{group_name_stem}"
                    classDef = makeGlyphClassDefinition(
                        new_group_name,
                        sorted(name.glyph for name in split_pair.side2.glyphSet()),
                    )
                    split_pair.side2 = ast.GlyphClassName(classDef)
                    newClass2Defs[new_group_name] = classDef
        self.context.kerning.newClass1Defs = newClass1Defs
        self.context.kerning.newClass2Defs = newClass2Defs

        # TODO: Remove for production.
        for script, pairs in kerning_per_script.items():
            try:
                ensure_unique_group_membership(pairs)
            except Exception as e:
                raise Exception(f"In {script}: {e}")

        # Sort Kerning pairs so that glyph to glyph comes first, then glyph to
        # class, class to glyph, and finally class to class. This makes "kerning
        # exceptions" work, where more specific glyph pair values override less
        # specific class kerning.
        for script, pairs in kerning_per_script.items():
            pairs.sort()

        quantization = self.options.quantization
        for script, pairs in kerning_per_script.items():
            key = f"kern_{script}{suffix}"
            script_lookups = lookups.setdefault(script, {})
            lookup = script_lookups.get(key)
            if not lookup:
                # For neatness:
                lookup_name = key.replace(COMMON_SCRIPT, "Common")
                lookup = ast.LookupBlock(lookup_name)
                if ignoreMarks:
                    lookup.statements.append(makeLookupFlag("IgnoreMarks"))
                script_lookups[key] = lookup
            for pair in pairs:
                # TODO: Derive direction from script and remove .directions attribute?
                script_is_rtl = "RTL" in pair.directions
                # Numbers are always shaped LTR even in RTL scripts:
                pair_is_rtl = "L" not in pair.bidiTypes
                rtl = script_is_rtl and pair_is_rtl
                rule = self._makePairPosRule(pair, rtl, quantization)
                lookup.statements.append(rule)

    def _makeFeatureBlocks(self, lookups):
        features = {}
        if "kern" in self.context.todo:
            kern = ast.FeatureBlock("kern")
            self._registerLookups(kern, lookups)
            if kern.statements:
                features["kern"] = kern
        if "dist" in self.context.todo:
            dist = ast.FeatureBlock("dist")
            self._registerLookups(dist, lookups)
            if dist.statements:
                features["dist"] = dist
        return features

    def _registerLookups(self, feature, lookups):
        scriptGroups = self.context.scriptGroups
        scripts = scriptGroups.get(feature.name, {})

        # Ensure we have kerning for pure common script runs (e.g. ">1")
        if feature.name == "kern" and COMMON_SCRIPT in lookups:
            addLookupReferences(
                feature, lookups[COMMON_SCRIPT].values(), "DFLT", ["dflt"]
            )
        if not scripts:
            return

        # Collapse scripts
        scripts = scripts.get("LTR", []) + scripts.get("RTL", [])
        otscript2uniscript = {}
        for uniscript in lookups.keys():
            for ot2script in unicodedata.ot_tags_from_script(uniscript):
                otscript2uniscript[ot2script] = uniscript
                if ot2script != "DFLT" and not any(
                    script == ot2script for script, _ in scripts
                ):
                    scripts.append((ot2script, ["dflt"]))

        for script, langs in sorted(scripts):
            if script not in otscript2uniscript:
                continue
            uniscript = otscript2uniscript[script]
            lookups_for_this_script = []
            if uniscript not in lookups:
                continue
            if feature.statements:
                feature.statements.append(ast.Comment(""))
            # We have something for this script. First add the default
            # lookups, then the script-specific ones
            for dflt_script in DFLT_SCRIPTS:
                if dflt_script in lookups:
                    lookups_for_this_script.extend(lookups[dflt_script].values())
            lookups_for_this_script.extend(lookups[uniscript].values())
            addLookupReferences(feature, lookups_for_this_script, script, langs)


def script_extensions_for_codepoint(uv: int) -> set[str]:
    return unicodedata.script_extension(chr(uv))


def ensure_unique_group_membership(pairs: list[KerningPair]) -> None:
    """Raises an exception when a glyph is found to belong to multiple groups per
    side.

    Group membership must be exclusive per side per lookup (script bucket).
    """

    kern1_membership: dict[str, set[str]] = {}
    kern2_membership: dict[str, set[str]] = {}

    for pair in pairs:
        if pair.firstIsClass:
            kern1 = {name.glyph for name in pair.side1.glyphSet()}
            for name in kern1:
                if name not in kern1_membership:
                    kern1_membership[name] = kern1
                elif kern1_membership[name] != kern1:
                    membership = kern1_membership[name]
                    raise Exception(
                        f"Glyph {name} in multiple kern1 groups, originally "
                        f"in {membership} but now also in {kern1}"
                    )
        if pair.secondIsClass:
            kern2 = {name.glyph for name in pair.side2.glyphSet()}
            for name in kern2:
                if name not in kern2_membership:
                    kern2_membership[name] = kern2
                elif kern2_membership[name] != kern2:
                    membership = kern2_membership[name]
                    raise Exception(
                        f"Glyph {name} in multiple kern2 groups, originally "
                        f"in {membership} but now also in {kern2}"
                    )
