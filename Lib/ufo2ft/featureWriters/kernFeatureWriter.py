from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Iterator, Mapping, NamedTuple

from fontTools import unicodedata
from fontTools.designspaceLib import DesignSpaceDocument
from fontTools.feaLib.variableScalar import Location as VariableScalarLocation
from fontTools.feaLib.variableScalar import VariableScalar
from fontTools.misc.classifyTools import classify
from fontTools.ufoLib.kerning import lookupKerningValue
from fontTools.unicodedata import script_horizontal_direction

from ufo2ft.constants import COMMON_SCRIPT, INDIC_SCRIPTS, USE_SCRIPTS
from ufo2ft.featureWriters import BaseFeatureWriter, ast
from ufo2ft.util import (
    DFLT_SCRIPTS,
    classifyGlyphs,
    collapse_varscalar,
    describe_ufo,
    get_userspace_location,
    quantize,
    unicodeScriptExtensions,
)

LOGGER = logging.getLogger(__name__)

SIDE1_PREFIX = "public.kern1."
SIDE2_PREFIX = "public.kern2."

# In HarfBuzz the 'dist' feature is automatically enabled for these shapers:
#   src/hb-ot-shape-complex-myanmar.cc
#   src/hb-ot-shape-complex-use.cc
#   src/hb-ot-shape-complex-indic.cc
#   src/hb-ot-shape-complex-khmer.cc
# We derived the list of scripts associated to each dist-enabled shaper from
# `hb_ot_shape_complex_categorize` in src/hb-ot-shape-complex-private.hh
DIST_ENABLED_SCRIPTS = set(INDIC_SCRIPTS) | set(["Khmr", "Mymr"]) | set(USE_SCRIPTS)

RTL_BIDI_TYPES = {"R", "AL"}
LTR_BIDI_TYPES = {"L", "AN", "EN"}
AMBIGUOUS_BIDIS = {"R", "L"}
COMMON_SCRIPTS_SET = {COMMON_SCRIPT}
COMMON_CLASS_NAME = "Default"

_MAX_LOGGED_DIVERGENT_GLYPHS = 10


def unicodeBidiType(uv):
    """Return "R" for characters with RTL direction, or "L" for LTR (whether
    'strong' or 'weak'), or None for neutral direction.
    """
    char = chr(uv)
    bidiType = unicodedata.bidirectional(char)
    if bidiType in RTL_BIDI_TYPES:
        return "R"
    elif bidiType in LTR_BIDI_TYPES:
        return "L"
    else:
        return None


def script_direction(script: str) -> str:
    if script == COMMON_SCRIPT:
        return "Auto"
    return script_horizontal_direction(script, "LTR")


@dataclass(frozen=True, order=False)
class KerningPair:
    __slots__ = ("side1", "side2", "value")

    side1: str | tuple[str, ...]
    side2: str | tuple[str, ...]
    value: float | VariableScalar

    def __lt__(self, other: KerningPair) -> bool:
        if not isinstance(other, KerningPair):
            return NotImplemented

        # Sort Kerning pairs so that glyph to glyph comes first, then glyph to
        # class, class to glyph, and finally class to class. This makes "kerning
        # exceptions" work, where more specific glyph pair values override less
        # specific class kerning. NOTE: Since comparisons terminate early, this
        # is never going to compare a str to a tuple.
        selfTuple = (self.firstIsClass, self.secondIsClass, self.side1, self.side2)
        otherTuple = (other.firstIsClass, other.secondIsClass, other.side1, other.side2)
        return selfTuple < otherTuple

    @property
    def firstIsClass(self) -> bool:
        return isinstance(self.side1, tuple)

    @property
    def secondIsClass(self) -> bool:
        return isinstance(self.side2, tuple)

    @property
    def firstGlyphs(self) -> tuple[str, ...]:
        if isinstance(self.side1, tuple):
            return self.side1
        else:
            return (self.side1,)

    @property
    def secondGlyphs(self) -> tuple[str, ...]:
        if isinstance(self.side2, tuple):
            return self.side2
        else:
            return (self.side2,)

    @property
    def glyphs(self) -> tuple[str, ...]:
        return (*self.firstGlyphs, *self.secondGlyphs)


class KernFeatureWriter(BaseFeatureWriter):
    """Generates a kerning feature based on groups and rules contained
    in an UFO's kerning data.

    If the `quantization` argument is given in the filter options, the resulting
    anchors are rounded to the nearest multiple of the quantization value.

    ## Implementation Notes

    The algorithm works like this:

    * Parse GDEF GlyphClassDefinition from UFO features.fea to get the set of
      "Mark" glyphs (this will be used later to decide whether to add
      ignoreMarks flag to kern lookups containing pairs between base and mark
      glyphs).
    * Get the ordered glyphset for the font, for filtering kerning groups and
      kernings that reference unknown glyphs.
    * Determine which scripts the kerning affects (read: "the font most probably
      supports"), to know which lookups to generate later:
        * First, determine the unambiguous script associations for each
          (Unicoded) glyph in the glyphset, as in, glyphs that have a single
          entry for their Unicode script extensions property;
        * then, parse the `languagesystem` statements in the provided feature
          file to add on top.
    * Compile a Unicode cmap from the UFO and a GSUB table from the features so
      far, so we can determine:
        * the script (extensions) for each glyph in the glyphset, including
          glyphs reachable via substitution, using the fontTools subsetter with
          its `closure_glyphs` machinery; the scripts are cut down to the ones
          we think the font supports;
        * and the bidirectionality class, so we can later filter out kerning
          pairs that would mix RTL and LTR glyphs, which will not occur in
          applications. Unicode BiDi classes L, AN and EN are considered L, R
          and AL are considered R.
    * Note: the glyph script determination has the quirk of declaring "Hira" and
      "Kana" scripts as "Hrkt" so that they are considered one script and can be
      kerned against each other.
    * Get the kerning groups from the UFO and filter out glyphs not in the
      glyphset and empty groups. Remember which group a glyph is a member of,
      for kern1 and kern2, so we can later reconstruct per-script groups.
    * Get the bare kerning pairs from the UFO, filtering out pairs with unknown
      groups or glyphs not in the glyphset and (redundant) zero class-to-class
      kernings and optionally quantizing kerning values.
    * Start generating lookups. By default, the ignore marks flag is added to
      each lookup. Kerning pairs that kern bases against marks or marks against
      marks, according to the glyphs' GDEF category, then get split off into a
      second lookup without the ignore marks flag.
    * Go through all kerning pairs and split them up by script, to put them in
      different lookups. This reduces the size of each lookup compared to
      splitting by direction, as previously done. If there are kerning pairs
      with different scripts on each side, these scripts are all kept together
      to allow for cross-script kerning (in implementations that apply it).
      Scripts with different direction are always split.
        * Partition the first and second side of a pair by script and emit only
          those with the same script (e.g. `a` and `b` are both "Latn", `period`
          and `period` are both "Default", but `a` and `a-cy` would mix "Latn"
          and "Cyrl" and are dropped), or those with kerning across them, or
          those that kern an explicit against a "common" or "inherited" script
          (e.g. `a` and `period`).
        * Glyphs can have multiple scripts assigned to them (legitimately, e.g.
          U+0951 DEVANAGARI STRESS SIGN UDATTA, or for random reasons like
          having both `sub h by h.sc` and `sub Etaprosgegrammeni by h.sc;`).
          Only scripts that were determined earlier to be supported by the font
          will be considered. Usually, we will emit pairs where both sides have
          the same script and no splitting is necessary. A glyph can be part of
          both for weird reasons, so we always treat any glyph with a common or
          inherited script as a purely common (not inherited) glyph for
          bucketing purposes. This avoids creating overlapping groups with the
          multi-script glyph in a lookup.
        * Some glyphs may have a script of Zyyy or Zinh but have a disjoint set
          of explicit scripts as their script extension. By looking only at the
          script extension, we treat many of them as being part of an explicit
          script rather than as a common or inherited glyph.
        * Preserve the type of the kerning pair, so class-to-class kerning stays
          that way, even when there's only one glyph on each side.
    * Reconstruct kerning group names for the newly split classes. This is done
      for debuggability; it makes no difference for the final font binary.
        * This first looks at the common lookups and then all others, assigning
          new group names are it goes. A class like `@kern1.A = [A A-cy
          increment]` may be split up into `@kern1.Latn.A = [A]`, `@kern1.Cyrl.A
          = [A-cy]` and `@kern1.Default.A = [increment]`. Note: If there is no
          dedicated Default lookup, common glyph classes like `[period]` might
          carry the name `@kern1.Grek.foo` if the class was first encountered
          while going over the Grek lookup.
    * Discard pairs that mix RTL and LTR BiDi types, because they won't show up
      in applications due to how Unicode text is split into runs.
    * Discard empty lookups, if they were created but all their pairs were
      discarded.
    * Make a `kern` (and potentially `dist`) feature block and register the
      lookups for each script. Some scripts need to be registered in the `dist`
      feature for some shapers to discover them, e.g. Yezi.
    * Write the new glyph class definitions and then the lookups and feature
      blocks to the feature file.
    """

    tableTag = "GPOS"
    features = frozenset(["kern", "dist"])
    options = dict(ignoreMarks=True, quantization=1)

    def setContext(self, font, feaFile, compiler=None):
        ctx = super().setContext(font, feaFile, compiler=compiler)
        ctx.gdefClasses = self.getGDEFGlyphClasses()
        ctx.glyphSet = self.getOrderedGlyphSet()

        # Unless we use the legacy append mode (which ignores insertion
        # markers), if the font (Designspace: default source) contains kerning
        # and the feaFile contains `kern` or `dist` feature blocks, but we have
        # no insertion markers (or they were misspelt and ignored), warn the
        # user that the kerning blocks in the feaFile take precedence and other
        # kerning is dropped.
        if hasattr(font, "findDefault"):
            default_source = font.findDefault().font
        else:
            default_source = font
        if (
            self.mode == "skip"
            and default_source.kerning
            and ctx.existingFeatures & self.features
            and not ctx.insertComments
        ):
            LOGGER.warning(
                "%s: font has kerning, but also manually written kerning features "
                "without an insertion comment. Dropping the former.",
                describe_ufo(default_source),
            )

        # Remember which languages are defined for which OT tag, as all
        # generated kerning needs to be registered for the script's `dflt`
        # language, but also all those the designer defined manually. Otherwise,
        # setting any language for a script would deactivate kerning.
        feaLanguagesByScript = ast.getScriptLanguageSystems(feaFile, excludeDflt=False)
        ctx.feaLanguagesByScript = {
            otTag: languages
            for _, languageSystems in feaLanguagesByScript.items()
            for otTag, languages in languageSystems
        }

        # TODO: Also include substitution information from Designspace rules to
        # correctly set the scripts of variable substitution glyphs, maybe add
        # `glyphUnicodeMapping: dict[str, int] | None` to `BaseFeatureCompiler`?
        cmap = self.makeUnicodeToGlyphNameMapping()
        gsub = self.compileGSUB()
        extras = self.extraSubstitutions()
        ctx.knownScripts = self.guessFontScripts()
        scriptGlyphs = classifyGlyphs(self.knownScriptsPerCodepoint, cmap, gsub, extras)
        bidiGlyphs = classifyGlyphs(unicodeBidiType, cmap, gsub, extras)
        ctx.bidiGlyphs = bidiGlyphs

        glyphScripts = {}
        for script, glyphs in scriptGlyphs.items():
            for g in glyphs:
                glyphScripts.setdefault(g, set()).add(script)
        ctx.glyphScripts = glyphScripts

        ctx.kerning = self.getKerningData()

        return ctx

    def shouldContinue(self):
        if not self.context.kerning.pairs:
            self.log.debug("No kerning data; skipped")
            return False

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
        classDefs = self.context.kerning.classDefs
        newClassDefs = [c for _, c in sorted(classDefs.items())]

        featureBlocks = [features[tag] for tag in ["kern", "dist"] if tag in features]

        # Collect only the lookups that are referenced by the features we're
        # writing, to avoid inserting unreferenced/dangling lookups when a
        # feature block already exists in the feature file.
        referencedLookups = {
            statement.lookup
            for feature in featureBlocks
            for statement in feature.statements
            if isinstance(statement, ast.LookupReferenceStatement)
        }

        lookupGroups = []
        for _, lookupGroup in sorted(lookups.items()):
            lookupGroups.extend(
                lkp
                for lkp in lookupGroup.values()
                if lkp in referencedLookups and lkp not in lookupGroups
            )

        # NOTE: We don't write classDefs because we literalise all classes.
        self._insert(
            feaFile=feaFile,
            classDefs=newClassDefs,
            lookups=lookupGroups,
            features=featureBlocks,
        )
        return True

    def getKerningData(self):
        side1Groups, side2Groups = self.getKerningGroups()
        pairs = self.getKerningPairs(side1Groups, side2Groups)
        # side(1|2)Classes and classDefs will hold the feaLib AST to write out.
        return SimpleNamespace(
            side1Classes={}, side2Classes={}, classDefs={}, pairs=pairs
        )

    def getKerningGroups(
        self,
    ) -> tuple[Mapping[str, tuple[str, ...]], Mapping[str, tuple[str, ...]]]:
        side1Groups, side2Groups, side1Membership, side2Membership = (
            collectKerningGroups(
                self.context.font, self.context.glyphSet, self.context.isVariable
            )
        )
        self.context.side1Membership = side1Membership
        self.context.side2Membership = side2Membership
        return side1Groups, side2Groups

    def getKerningPairs(
        self,
        side1Classes: Mapping[str, tuple[str, ...]],
        side2Classes: Mapping[str, tuple[str, ...]],
    ) -> list[KerningPair]:
        if self.context.isVariable:
            return getVariableKerningPairs(
                self.context.font,
                self.context.glyphSet,
                self.options,
            )

        glyphSet = self.context.glyphSet
        font = self.context.font
        kerning = font.kerning
        quantization = self.options.quantization

        kerning: Mapping[tuple[str, str], float] = font.kerning
        result = []
        for (side1, side2), value in kerning.items():
            firstIsClass, secondIsClass = (side1 in side1Classes, side2 in side2Classes)
            # Filter out pairs that reference missing groups or glyphs.
            if not firstIsClass and side1 not in glyphSet:
                continue
            if not secondIsClass and side2 not in glyphSet:
                continue
            # Ignore zero-valued class kern pairs. They are the most general
            # kerns, so they don't override anything else like glyph kerns would
            # and zero is the default.
            if firstIsClass and secondIsClass and value == 0:
                continue
            if firstIsClass:
                side1 = side1Classes[side1]
            if secondIsClass:
                side2 = side2Classes[side2]
            value = quantize(value, quantization)
            result.append(KerningPair(side1, side2, value))

        return result

    def _makePairPosRule(self, pair, side1Classes, side2Classes, rtl=False):
        enumerated = pair.firstIsClass ^ pair.secondIsClass
        valuerecord = ast.ValueRecord(
            xPlacement=pair.value if rtl else None,
            yPlacement=0 if rtl else None,
            xAdvance=pair.value,
            yAdvance=0 if rtl else None,
        )

        if pair.firstIsClass:
            glyphs1 = ast.GlyphClassName(side1Classes[pair.side1])
        else:
            glyphs1 = ast.GlyphName(pair.side1)
        if pair.secondIsClass:
            glyphs2 = ast.GlyphClassName(side2Classes[pair.side2])
        else:
            glyphs2 = ast.GlyphName(pair.side2)

        return ast.PairPosStatement(
            glyphs1=glyphs1,
            valuerecord1=valuerecord,
            glyphs2=glyphs2,
            valuerecord2=None,
            enumerated=enumerated,
        )

    def _filterSpacingMarks(self, marks):
        if self.context.isVariable:
            spacing = []
            for mark in marks:
                if all(
                    source.font[mark].width != 0
                    for source in self.context.font.sources
                    if mark in source.font
                ):
                    spacing.append(mark)
            return spacing

        return [mark for mark in marks if self.context.font[mark].width != 0]

    def _makeKerningLookup(self, name, ignoreMarks=True):
        lookup = ast.LookupBlock(name)
        if ignoreMarks and self.options.ignoreMarks:
            # We only want to filter the spacing marks
            marks = set(self.context.gdefClasses.mark or []) & set(
                self.context.glyphSet.keys()
            )

            spacing = []
            if marks:
                spacing = self._filterSpacingMarks(marks)
            if not spacing:
                # Simple case, there are no spacing ("Spacing Combining") marks,
                # do what we've always done.
                lookup.statements.append(ast.makeLookupFlag("IgnoreMarks"))
            else:
                # We want spacing marks to block kerns.
                className = "MFS_%s" % name
                filteringClass = ast.makeGlyphClassDefinitions(
                    {className: spacing}, feaFile=self.context.feaFile
                )[className]
                lookup.statements.append(filteringClass)
                lookup.statements.append(
                    ast.makeLookupFlag(markFilteringSet=filteringClass)
                )
        return lookup

    def knownScriptsPerCodepoint(self, uv: int) -> set[str] | None:
        if not self.context.knownScripts:
            # If there are no languagesystems and nothing to derive from Unicode
            # codepoints, consider everything common; it'll all end in DFLT/dflt
            # anyway.
            return {COMMON_SCRIPT}
        else:
            script_extension = unicodeScriptExtensions(uv)
            return script_extension & (self.context.knownScripts | DFLT_SCRIPTS) or None

    def _makeKerningLookups(self):
        marks = self.context.gdefClasses.mark
        lookups = {}
        pairs = self.context.kerning.pairs

        if self.options.ignoreMarks:
            basePairs, markPairs = self._splitBaseAndMarkPairs(
                self.context.kerning.pairs, marks
            )
            if basePairs:
                self._makeSplitScriptKernLookups(lookups, basePairs)
            if markPairs:
                self._makeSplitScriptKernLookups(
                    lookups, markPairs, ignoreMarks=False, suffix="_marks"
                )
        else:
            self._makeSplitScriptKernLookups(lookups, pairs)
        return lookups

    def _splitBaseAndMarkPairs(
        self, pairs: list[KerningPair], marks: set[str]
    ) -> tuple[list[KerningPair], list[KerningPair]]:
        if not marks:
            return list(pairs), []

        basePairs: list[KerningPair] = []
        markPairs: list[KerningPair] = []
        for pair in pairs:
            # Disentangle kerning between bases and marks by splitting a pair
            # into a list of base-to-base pairs (basePairs) and a list of
            # base-to-mark, mark-to-base and mark-to-mark pairs (markPairs).
            # This ensures that "kerning exceptions" (a kerning pair modifying
            # the effect of another) work as intended because these related
            # pairs end up in the same list together.
            side1Bases: tuple[str, ...] | str | None = None
            side1Marks: tuple[str, ...] | str | None = None
            if pair.firstIsClass:
                side1Bases = tuple(glyph for glyph in pair.side1 if glyph not in marks)
                side1Marks = tuple(glyph for glyph in pair.side1 if glyph in marks)
            else:
                if pair.side1 in marks:
                    side1Marks = pair.side1
                else:
                    side1Bases = pair.side1

            side2Bases: tuple[str, ...] | str | None = None
            side2Marks: tuple[str, ...] | str | None = None
            if pair.secondIsClass:
                side2Bases = tuple(glyph for glyph in pair.side2 if glyph not in marks)
                side2Marks = tuple(glyph for glyph in pair.side2 if glyph in marks)
            else:
                if pair.side2 in marks:
                    side2Marks = pair.side2
                else:
                    side2Bases = pair.side2

            if side1Bases and side2Bases:  # base-to-base
                basePairs.append(KerningPair(side1Bases, side2Bases, value=pair.value))

            if side1Bases and side2Marks:  # base-to-mark
                markPairs.append(KerningPair(side1Bases, side2Marks, value=pair.value))
            if side1Marks and side2Bases:  # mark-to-base
                markPairs.append(KerningPair(side1Marks, side2Bases, value=pair.value))
            if side1Marks and side2Marks:  # mark-to-mark
                markPairs.append(KerningPair(side1Marks, side2Marks, value=pair.value))

        return basePairs, markPairs

    def _makeSplitScriptKernLookups(self, lookups, pairs, ignoreMarks=True, suffix=""):
        bidiGlyphs = self.context.bidiGlyphs
        glyphScripts = self.context.glyphScripts
        kerningPerScript = splitKerning(pairs, glyphScripts)
        side1Classes = self.context.kerning.side1Classes
        side2Classes = self.context.kerning.side2Classes

        newClassDefs, newSide1Classes, newSide2Classes = makeAllGlyphClassDefinitions(
            kerningPerScript, self.context, self.context.feaFile
        )
        # NOTE: Consider duplicate names a bug, even if the classes would carry
        # the same glyphs.
        assert not self.context.kerning.classDefs.keys() & newClassDefs.keys()
        self.context.kerning.classDefs.update(newClassDefs)
        assert not side1Classes.keys() & newSide1Classes.keys()
        side1Classes.update(newSide1Classes)
        assert not side2Classes.keys() & newSide2Classes.keys()
        side2Classes.update(newSide2Classes)

        for scripts, pairs in kerningPerScript.items():
            lookupName = f"kern_{'_'.join(scripts)}{suffix}".replace(
                COMMON_SCRIPT, COMMON_CLASS_NAME
            )
            lookup = self._makeKerningLookup(lookupName, ignoreMarks=ignoreMarks)
            for pair in pairs:
                bidiTypes = {
                    direction
                    for direction, glyphs in bidiGlyphs.items()
                    if not set(pair.glyphs).isdisjoint(glyphs)
                }
                if bidiTypes.issuperset(AMBIGUOUS_BIDIS):
                    LOGGER.info(
                        "Skipping kerning pair <%s %s %s> with ambiguous direction",
                        pair.side1,
                        pair.side2,
                        pair.value,
                    )
                    continue
                directions = {script_direction(script) for script in scripts}
                assert len(directions) == 1
                scriptIsRtl = directions == {"RTL"}
                # Numbers are always shaped LTR even in RTL scripts:
                pairIsRtl = scriptIsRtl and "L" not in bidiTypes
                rule = self._makePairPosRule(
                    pair, side1Classes, side2Classes, pairIsRtl
                )
                lookup.statements.append(rule)
            for script in scripts:
                lookups.setdefault(script, {})[lookupName] = lookup

        # Clean out empty lookups.
        for script, scriptLookups in list(lookups.items()):
            for lookup_name, lookup in list(scriptLookups.items()):
                if not any(
                    stmt
                    for stmt in lookup.statements
                    if not isinstance(stmt, ast.LookupFlagStatement)
                ):
                    del scriptLookups[lookup_name]
            if not scriptLookups:
                del lookups[script]

    def _makeFeatureBlocks(self, lookups):
        features = {}
        feaLanguagesByScript = self.context.feaLanguagesByScript
        if "kern" in self.context.todo:
            kern = ast.FeatureBlock("kern")
            self._registerLookups(kern, lookups, feaLanguagesByScript)
            if kern.statements:
                features["kern"] = kern
        if "dist" in self.context.todo:
            dist = ast.FeatureBlock("dist")
            self._registerLookups(dist, lookups, feaLanguagesByScript)
            if dist.statements:
                features["dist"] = dist
        return features

    @staticmethod
    def _registerLookups(
        feature: ast.FeatureBlock,
        lookups: dict[str, dict[str, ast.LookupBlock]],
        feaLanguagesByScript: Mapping[str, list[str]],
    ) -> None:
        # Ensure we have kerning for pure common script runs (e.g. ">1")
        isKernBlock = feature.name == "kern"
        dfltLookups: list[ast.LookupBlock] = []
        if isKernBlock and COMMON_SCRIPT in lookups:
            dfltLookups.extend(
                lkp for lkp in lookups[COMMON_SCRIPT].values() if lkp not in dfltLookups
            )

        # InDesign bugfix: register kerning lookups for all LTR scripts under DFLT
        # so that the basic composer, without a language selected, will still kern.
        # Register LTR lookups if any, otherwise RTL lookups.
        if isKernBlock:
            lookupsLTR: list[ast.LookupBlock] = []
            lookupsRTL: list[ast.LookupBlock] = []
            for script, scriptLookups in sorted(lookups.items()):
                if script not in DIST_ENABLED_SCRIPTS:
                    if script_direction(script) == "LTR":
                        lookupsLTR.extend(scriptLookups.values())
                    elif script_direction(script) == "RTL":
                        lookupsRTL.extend(scriptLookups.values())
            dfltLookups.extend(
                lkp for lkp in (lookupsLTR or lookupsRTL) if lkp not in dfltLookups
            )

        if dfltLookups:
            languages = feaLanguagesByScript.get("DFLT", ["dflt"])
            ast.addLookupReferences(feature, dfltLookups, "DFLT", languages)

        # Feature blocks use script tags to distinguish what to run for a
        # Unicode script.
        #
        # "Script tags generally correspond to a Unicode script. However, the
        # associations between them may not always be one-to-one, and the
        # OpenType script tags are not guaranteed to be the same as Unicode
        # Script property-value aliases or ISO 15924 script IDs."
        #
        # E.g. {"latn": "Latn", "telu": "Telu", "tel2": "Telu"}
        #
        # Skip DFLT script because we always take care of it above for `kern`.
        # It never occurs in `dist`.
        if isKernBlock:
            scriptsToReference = lookups.keys() - DIST_ENABLED_SCRIPTS
        else:
            scriptsToReference = DIST_ENABLED_SCRIPTS.intersection(lookups.keys())
        for script in sorted(scriptsToReference - DFLT_SCRIPTS):
            for tag in unicodedata.ot_tags_from_script(script):
                # Insert line breaks between statements for niceness :).
                if feature.statements:
                    feature.statements.append(ast.Comment(""))
                # We have something for this script. First add the default
                # lookups, then the script-specific ones
                lookupsForThisScript = {}
                for dfltScript in DFLT_SCRIPTS:
                    if dfltScript in lookups:
                        lookupsForThisScript.update(lookups[dfltScript])
                lookupsForThisScript.update(lookups[script])
                # Register the lookups for all languages defined in the feature
                # file for the script, otherwise kerning is not applied if any
                # language is set at all.
                languages = feaLanguagesByScript.get(tag, ["dflt"])
                ast.addLookupReferences(
                    feature, lookupsForThisScript.values(), tag, languages
                )


# One source's glyph -> group name assignments for a single kern side; lists of
# these are always parallel to the non-sparse sources they were built from.
GroupMap = dict[str, str]


def _sourceGroupMaps(
    font: Any, glyphSet: Mapping[str, str]
) -> tuple[GroupMap, GroupMap]:
    side1Map: GroupMap = {}
    side2Map: GroupMap = {}
    for name, members in font.groups.items():
        members = {g for g in members if g in glyphSet}
        if not members:
            continue
        if name.startswith(SIDE1_PREFIX):
            for member in members:
                side1Map[member] = name
        elif name.startswith(SIDE2_PREFIX):
            for member in members:
                side2Map[member] = name
    return side1Map, side2Map


def _groupMembers(maps: list[GroupMap]) -> dict[str, tuple[str, ...]]:
    """Invert source maps without dropping overlapping groups.

    Inverting the maps rather than font.groups keeps class membership
    consistent with value resolution: a glyph in two same-side groups of one
    source (invalid per UFO3) resolves to the last, lookupKerningValue's own
    tie-break.
    """
    members: dict[str, set[str]] = {}
    for sourceMap in maps:
        for glyph, name in sourceMap.items():
            members.setdefault(name, set()).add(glyph)
    return {name: tuple(sorted(glyphs)) for name, glyphs in members.items()}


def _divergentGlyphs(maps: list[GroupMap]) -> set[str]:
    """Return glyphs whose group assignment differs between sources.

    Ungrouped or absent in a source counts as a distinct assignment.
    """
    divergent: set[str] = set()
    allGlyphs: set[str] = set()
    for sourceMap in maps:
        allGlyphs.update(sourceMap)
    for glyph in allGlyphs:
        if len({sourceMap.get(glyph) for sourceMap in maps}) > 1:
            divergent.add(glyph)
    return divergent


def _refineMembers(
    members: tuple[str, ...], kernedMaps: list[GroupMap]
) -> list[tuple[tuple[str | None, ...], tuple[str, ...]]]:
    """Partition members into refined classes by kerned-group signature.

    A member's signature is its kerned group name in each source (None where it
    has none); members sharing the same signature form one refined class,
    returned as a (signature, members) pair, sorted for deterministic output.
    kernedMaps hold only groups referenced by that source's kerning: an
    unkerned group never reaches the compiled ClassDefs that varLib.merger
    partitions, so its members count as ungrouped here. The members are
    bucketed per source by their group, and classifyTools.classify -- the same
    primitive varLib.merger uses -- derives the coarsest common refinement;
    see ufo2ft#992.
    """
    perSourceSets: list[list[str]] = []
    for kernedMap in kernedMaps:
        byGroup: dict[str | None, list[str]] = {}
        for member in members:
            byGroup.setdefault(kernedMap.get(member), []).append(member)
        perSourceSets.extend(byGroup.values())
    classes, _ = classify(perSourceSets, sort=False)
    return [
        (tuple(kernedMap.get(cell[0]) for kernedMap in kernedMaps), cell)
        for cell in sorted(tuple(sorted(refined)) for refined in classes)
    ]


class _KernSource(NamedTuple):
    location: VariableScalarLocation
    kerning: Mapping[tuple[str, str], float]
    side1Map: GroupMap
    side2Map: GroupMap


@dataclass
class _KernSide:
    """Per-side (kern1 or kern2) partition state for the variable writer.

    Built from the sources' own group maps, it exposes the group union (which,
    unlike first-wins merging, never strands glyphs that still need variable
    values) and refines only classes whose membership diverges across masters.
    Refining splits a class into refined classes: the largest subsets of its
    members that share the same kerned group in every source (a consistent
    class stays whole); pairing side1 and side2 refined classes reproduces
    varLib.merger's refined class matrix, each pair one cell of it. The full
    maps carry what the sources declare, the kerned maps
    what the varLib.merge path (variableFeatures=False) sees in the compiled
    per-master ClassDefs: divergence is detected on the former, the refined
    partition computed on the latter.
    """

    kernedMaps: list[GroupMap]
    groups: dict[str, tuple[str, ...]]
    divergentGlyphs: set[str]
    divergentClasses: set[str]
    _refinedClasses: dict[str, list[tuple[tuple[str | None, ...], tuple[str, ...]]]] = (
        field(default_factory=dict, init=False)
    )

    @classmethod
    def fromSources(cls, sources: list[_KernSource], side: int) -> _KernSide:
        """Build one side's state; side is 1 or 2, matching kern1/kern2."""
        assert side in (1, 2)
        maps = [source.side1Map if side == 1 else source.side2Map for source in sources]
        # Refine against groups referenced by kerning only; unkerned groups do
        # not appear in compiled ClassDefs, so treating them as ungrouped
        # matches varLib.merger.
        kernedMaps = []
        for source, sourceMap in zip(sources, maps):
            kerned = {key[side - 1] for key in source.kerning}
            kernedMaps.append(
                {glyph: name for glyph, name in sourceMap.items() if name in kerned}
            )
        groups = _groupMembers(maps)
        divergentGlyphs = _divergentGlyphs(maps)
        divergentClasses = {
            name
            for name, members in groups.items()
            if divergentGlyphs.intersection(members)
        }
        return cls(kernedMaps, groups, divergentGlyphs, divergentClasses)

    def refine(
        self, name: str
    ) -> Iterator[tuple[str | tuple[str | None, ...], str | tuple[str, ...]]]:
        """Yield (names, glyphs) for one glyph or group name of a kern key.

        names feeds build_scalar -- either one name looked up in every source,
        or a tuple with one name (or None) per source; glyphs is the emitted
        KerningPair side. A divergent class is split into its refined classes,
        singletons included, to match varLib.merger's class-based GPOS.
        """
        members = self.groups.get(name)
        if members is None:  # a bare glyph, not a class
            yield name, name
            return
        if name not in self.divergentClasses:
            yield name, members
            return
        if name not in self._refinedClasses:
            self._refinedClasses[name] = _refineMembers(members, self.kernedMaps)
        yield from self._refinedClasses[name]


def collectKerningGroups(designspaceOrFont, glyphSet, isVariable) -> tuple[
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
    dict[str, str],
    dict[str, str],
]:
    """Merge kern groups for both kern writers.

    Returns merged side1/side2 group maps plus glyph -> truncated-group-name
    memberships. Memberships are backfilled from groups that first-source-wins
    merging drops, so refined classes can still be named.
    """
    allGlyphs = glyphSet

    side1Groups: dict[str, tuple[str, ...]] = {}
    side1Membership: dict[str, str] = {}
    side2Groups: dict[str, tuple[str, ...]] = {}
    side2Membership: dict[str, str] = {}
    # Fallback names for glyphs stranded by first-wins merging, recorded before
    # any drop so a stranded glyph can still name its refined class.
    side1Fallback: dict[str, str] = {}
    side2Fallback: dict[str, str] = {}

    if isinstance(designspaceOrFont, DesignSpaceDocument):
        fonts = [source.font for source in designspaceOrFont.sources]
    else:
        fonts = [designspaceOrFont]

    # Variable builds reconcile cross-source overlaps later, so only static
    # builds warn about dropped groups.
    warn_on_drop = not isVariable

    for font in fonts:
        assert font is not None
        for name, members in font.groups.items():
            # prune non-existent or skipped glyphs
            members = {g for g in members if g in allGlyphs}
            # skip empty groups
            if not members:
                continue
            if name.startswith(SIDE1_PREFIX):
                prefix = SIDE1_PREFIX
                groups, membership = side1Groups, side1Membership
                fallback = side1Fallback
                side_label = "first"
            elif name.startswith(SIDE2_PREFIX):
                prefix = SIDE2_PREFIX
                groups, membership = side2Groups, side2Membership
                fallback = side2Fallback
                side_label = "second"
            else:
                continue
            name_truncated = name[len(prefix) :]
            for member in members:
                fallback.setdefault(member, name_truncated)
            known_members = members.intersection(membership.keys())
            if known_members:
                if warn_on_drop:
                    for glyph_name in known_members:
                        original_name_truncated = membership[glyph_name]
                        if name_truncated != original_name_truncated:
                            log_regrouped_glyph(
                                side_label,
                                name,
                                original_name_truncated,
                                font,
                                glyph_name,
                            )
                # Skip the whole group definition if there is any overlap problem.
                continue
            group = groups.get(name)
            if group is None:
                groups[name] = tuple(sorted(members))
                for member in members:
                    membership[member] = name_truncated
            elif set(group) != members and warn_on_drop:
                log_redefined_group(side_label, name, group, font, members)
    # Apply the fallback names last, keeping already-merged names canonical.
    # Deferred to here (not written mid-merge) because the merge reads
    # membership to decide drops.
    for member, name_truncated in side1Fallback.items():
        side1Membership.setdefault(member, name_truncated)
    for member, name_truncated in side2Fallback.items():
        side2Membership.setdefault(member, name_truncated)
    return side1Groups, side2Groups, side1Membership, side2Membership


def getVariableKerningPairs(
    designspace: DesignSpaceDocument,
    glyphSet: Mapping[str, str],
    options: SimpleNamespace,
) -> list[KerningPair]:
    quantization = options.quantization

    # We may need to provide a default location value to the variation model,
    # find out where that is. The default source is always kept below, even if
    # it has no kerning: it anchors the model, and a kernless default is out of
    # scope for #995.
    default_source = designspace.findDefault()
    assert default_source is not None

    # Resolve each non-sparse source against its own group maps.
    sources: list[_KernSource] = []
    for source in designspace.sources:
        if source.layerName is not None:
            continue
        assert source.font is not None
        # A full (non-layer) source with no kerning contributes no kern GPOS, so
        # skip it: it adds no location to the kern VariableScalars and the model
        # interpolates across it instead of pinning the kern to 0. varLib either
        # excludes such a source (no other GPOS -> VariationMerger drops it) or
        # crashes on it (has marks etc. -> structural mismatch, #350); skipping
        # matches the former and beats the latter.
        # https://github.com/googlefonts/ufo2ft/issues/995
        if source is not default_source and not source.font.kerning:
            continue
        location = VariableScalarLocation(
            get_userspace_location(designspace, source.location)
        )
        side1Map, side2Map = _sourceGroupMaps(source.font, glyphSet)
        sources.append(_KernSource(location, source.font.kerning, side1Map, side2Map))

    kern1 = _KernSide.fromSources(sources, 1)
    kern2 = _KernSide.fromSources(sources, 2)

    divergent = kern1.divergentGlyphs | kern2.divergentGlyphs
    if divergent:
        # Avoid listing hundreds of glyph names in one log record.
        shown = ", ".join(sorted(divergent)[:_MAX_LOGGED_DIVERGENT_GLYPHS])
        if len(divergent) > _MAX_LOGGED_DIVERGENT_GLYPHS:
            shown += f", ... ({len(divergent) - _MAX_LOGGED_DIVERGENT_GLYPHS} more)"
        LOGGER.info(
            "Reconciling kerning groups that differ across masters for %d glyph(s): %s",
            len(divergent),
            shown,
        )

    # The default source (located above) anchors the variation model; find where
    # that is in the VariableScalar coordinate space.
    default_location = VariableScalarLocation(
        get_userspace_location(designspace, default_source.location)
    )

    # Collate every kerning pair *key* in the designspace, as even sources
    # that provide no entry for the pair must contribute a value at their
    # location in the VariableScalar.
    # NOTE: This is required because the DS+UFO kerning model and the
    #       OpenType variation model handle the absence of a kerning value
    #       at a given location differently:
    #       - DS+UFO:
    #           If the missing pair excepts another pair, take its value;
    #           Otherwise, take a value of 0.
    #       - OpenType:
    #           Always interpolate from other locations, ignoring more
    #           general pairs that this one excepts.
    # See discussion: https://github.com/googlefonts/ufo2ft/pull/635
    all_pairs = {pair for source in sources for pair in source.kerning}

    def build_scalar(side1Names, side2Names) -> VariableScalar:
        """Resolve per-source glyph/group names with the DS+UFO kerning cascade.

        A bare name is used for every source; a tuple supplies one name (or
        None) per source. Glyph names use the full cascade; group names match
        only class-level entries; None (no kerned class in that source)
        resolves to 0, varLib.merger's class 0.
        """
        if isinstance(side1Names, str):
            side1Names = (side1Names,) * len(sources)
        if isinstance(side2Names, str):
            side2Names = (side2Names,) * len(sources)
        scalar = VariableScalar()
        for source, side1, side2 in zip(sources, side1Names, side2Names):
            if side1 is None or side2 is None:
                value = 0
            else:
                value = quantize(
                    lookupKerningValue(
                        (side1, side2),
                        source.kerning,
                        {},  # groups unused when explicit maps are passed
                        glyphToFirstGroup=source.side1Map,
                        glyphToSecondGroup=source.side2Map,
                    ),
                    quantization,
                )
            # NOTE: assign .values directly rather than .add_value, which
            # instantiates a new VariableScalarLocation on each call.
            scalar.values[source.location] = value
        # Anchor the default (the model's reference) at 0 when no source
        # sets it; it's a base value, never interpolated.
        if default_location not in scalar.values:
            scalar.values[default_location] = 0
        return scalar

    def resolve_pairs(side1, side2):
        """Yield the variable KerningPair(s) for one source kerning key.

        Most keys yield a single pair resolved with the DS+UFO cascade. The
        exceptions:
        - a key referencing a missing glyph yields nothing;
        - a zero-valued class-to-class kern yields nothing;
        - a glyph-to-class exception is resolved cell by cell. Its value must
          be defined at every location; where a source omits it the cascade
          backfills the class-to-class value, and since glyph-to-class
          outranks class-to-glyph that backfill would shadow a competing
          class-to-glyph exception on a shared cell -- rendering there a value
          the source never resolves to (a "phantom"). So resolve each member
          against the cascade and emit it as its own pair, carrying the value
          that cell actually lands on.
          See https://github.com/googlefonts/ufo2ft/issues/988.
        - a class whose membership diverges across masters is refined into the
          per-master common refinement (see _KernSide.refine, #992).
        """
        firstIsClass = side1 in kern1.groups
        secondIsClass = side2 in kern2.groups

        # Skip pairs that reference a missing glyph.
        if not firstIsClass and side1 not in glyphSet:
            return
        if not secondIsClass and side2 not in glyphSet:
            return

        if not firstIsClass and secondIsClass:
            # The source group maps prune members to the glyph set, so every
            # member resolves to a real pair. Members that agree on a value
            # could share an inline class, but that only compacts the debug
            # feature file: enum-expanded and per-glyph pairs compile to
            # identical GPOS, so keep it simple and emit one pair per member.
            # Per-member resolution also covers divergent membership -- each
            # member takes its own per-source value -- so no refinement is
            # needed here.
            for member in kern2.groups[side2]:
                scalar = build_scalar(side1, member)
                yield KerningPair(side1, member, collapse_varscalar(scalar))
            return

        for names1, glyphs1 in kern1.refine(side1):
            for names2, glyphs2 in kern2.refine(side2):
                pair = KerningPair(
                    glyphs1, glyphs2, collapse_varscalar(build_scalar(names1, names2))
                )
                # Zero class-to-class pairs override nothing, even when refined.
                if firstIsClass and secondIsClass and pair.value == 0:
                    continue
                yield pair

    # The per-cell split can emit a glyph-glyph pair that another key also
    # yields (an explicit pair, or another overlapping class), so dedupe on the
    # output pair. Colliding pairs resolve the same cell, so their values match.
    result: dict[tuple[Any, Any], KerningPair] = {}
    for side1, side2 in all_pairs:
        for pair in resolve_pairs(side1, side2):
            key = (pair.side1, pair.side2)
            if key in result:
                # VariableScalar has no value __eq__, so compare contents.
                a, b = result[key].value, pair.value
                a = a.values if isinstance(a, VariableScalar) else a
                b = b.values if isinstance(b, VariableScalar) else b
                assert a == b, f"conflicting variable kern values for {key}"
            result[key] = pair

    return list(result.values())


def splitKerning(pairs, glyphScripts):
    # Split kerning into per-script buckets, so we can post-process them before
    # continuing. Scripts that have cross-script kerning pairs will be put in
    # the same bucket.
    kerningPerScript = {}
    for pair in pairs:
        for scripts, splitPair in partitionByScript(pair, glyphScripts):
            scripts = tuple(sorted(scripts))
            kerningPerScript.setdefault(scripts, []).append(splitPair)

    kerningPerScript = mergeScripts(kerningPerScript)

    for scripts, pairs in kerningPerScript.items():
        if len(scripts) > 1:
            LOGGER.info(
                "Merging kerning lookups from the following scripts: %s",
                ", ".join(scripts),
            )
        pairs.sort()

    return kerningPerScript


def partitionByScript(
    pair: KerningPair,
    glyphScripts: Mapping[str, set[str]],
) -> Iterator[tuple[str, KerningPair]]:
    """Split a potentially mixed-script pair into pairs that make sense based
    on the dominant script, and yield each combination with its dominant script."""

    side1Directions: dict[str, set[str]] = {}
    side2Directions: dict[str, set[str]] = {}
    resolvedScripts: dict[str, set[str]] = {}
    for glyph in pair.firstGlyphs:
        scripts = glyphScripts.get(glyph, DFLT_SCRIPTS)
        # If a glyph is both common or inherited *and* another script, treat it
        # as just common (throwing Zyyy and Zinh into the same bucket for
        # simplicity). This ensures that a pair appears to the shaper exactly
        # once, as long as every script sees at most 2 lookups (or 3 with mark
        # lookups, but they contain distinct pairs), the common one and the
        # script-specific one.
        if scripts & DFLT_SCRIPTS:
            scripts = COMMON_SCRIPTS_SET
        resolvedScripts[glyph] = scripts
        for direction in (script_direction(script) for script in sorted(scripts)):
            side1Directions.setdefault(direction, set()).add(glyph)
    for glyph in pair.secondGlyphs:
        scripts = glyphScripts.get(glyph, DFLT_SCRIPTS)
        if scripts & DFLT_SCRIPTS:
            scripts = COMMON_SCRIPTS_SET
        resolvedScripts[glyph] = scripts
        for direction in (script_direction(script) for script in sorted(scripts)):
            side2Directions.setdefault(direction, set()).add(glyph)

    for side1Direction, side2Direction in itertools.product(
        side1Directions, side2Directions
    ):
        localSide1: str | tuple[str, ...]
        localSide2: str | tuple[str, ...]
        side1Scripts: set[str] = set()
        side2Scripts: set[str] = set()
        if pair.firstIsClass:
            localSide1 = tuple(sorted(side1Directions[side1Direction]))
            for glyph in localSide1:
                side1Scripts |= resolvedScripts[glyph]
        else:
            assert len(side1Directions[side1Direction]) == 1
            (localSide1,) = side1Directions[side1Direction]
            side1Scripts |= resolvedScripts[localSide1]
        if pair.secondIsClass:
            localSide2 = tuple(sorted(side2Directions[side2Direction]))
            for glyph in localSide2:
                side2Scripts |= resolvedScripts[glyph]
        else:
            assert len(side2Directions[side2Direction]) == 1
            (localSide2,) = side2Directions[side2Direction]
            side2Scripts |= resolvedScripts[localSide2]

        # Skip pairs with mixed direction.
        if side1Direction != side2Direction and not any(
            side == "Auto" for side in (side1Direction, side2Direction)
        ):
            LOGGER.info(
                "Skipping kerning pair <%s %s %s> with mixed direction (%s, %s)",
                pair.side1,
                pair.side2,
                pair.value,
                side1Direction,
                side2Direction,
            )
            continue

        scripts = side1Scripts | side2Scripts
        # If only one side has Common, drop it
        if not all(side & COMMON_SCRIPTS_SET for side in (side1Scripts, side2Scripts)):
            scripts -= COMMON_SCRIPTS_SET

        yield scripts, KerningPair(
            localSide1,
            localSide2,
            pair.value,
        )


def mergeScripts(kerningPerScript):
    """Merge buckets that have common scripts. If we have [A, B], [B, C], and
    [D] buckets, we want to merge the first two into [A, B, C] and leave [D] so
    that all kerning pairs of the three scripts are in the same lookup."""
    sets = [set(scripts) for scripts in kerningPerScript if scripts]
    merged = True
    while merged:
        merged = False
        result = []
        while sets:
            common, rest = sets[0], sets[1:]
            sets = []
            for scripts in rest:
                if scripts.isdisjoint(common):
                    sets.append(scripts)
                else:
                    merged = True
                    common |= scripts
            result.append(common)
        sets = result

    # Now that we have merged all common-script buckets, we need to re-assign
    # the kerning pairs to the new buckets.
    result = {tuple(sorted(scripts)): [] for scripts in sets}
    for scripts, pairs in kerningPerScript.items():
        for scripts2 in sets:
            if scripts2 & set(scripts):
                result[tuple(sorted(scripts2))].extend(pairs)
                break
        else:
            # Shouldn't happen, but just in case.
            raise AssertionError
    return result


def makeAllGlyphClassDefinitions(kerningPerScript, context, feaFile=None):
    # Note: Refer to the context for existing classDefs and mappings of glyph
    # class tuples to feaLib AST to avoid overwriting existing class names,
    # because base and mark kerning pairs might be separate passes.
    newClassDefs = {}
    existingSide1Classes = context.kerning.side1Classes
    existingSide2Classes = context.kerning.side2Classes
    newSide1Classes = {}
    newSide2Classes = {}
    side1Membership = context.side1Membership
    side2Membership = context.side2Membership

    if feaFile is not None:
        classNames = {cdef.name for cdef in ast.iterClassDefinitions(feaFile)}
    else:
        classNames = set()
    classNames.update(context.kerning.classDefs.keys())

    # Generate common class names first so that common classes are correctly
    # named in other lookups.
    for scripts, pairs in kerningPerScript.items():
        if set(scripts) != COMMON_SCRIPTS_SET:
            continue
        for pair in pairs:
            if (
                pair.firstIsClass
                and pair.side1 not in existingSide1Classes
                and pair.side1 not in newSide1Classes
            ):
                addClassDefinition(
                    "kern1",
                    pair.side1,
                    newSide1Classes,
                    side1Membership,
                    newClassDefs,
                    classNames,
                    COMMON_CLASS_NAME,
                )
            if (
                pair.secondIsClass
                and pair.side2 not in existingSide2Classes
                and pair.side2 not in newSide2Classes
            ):
                addClassDefinition(
                    "kern2",
                    pair.side2,
                    newSide2Classes,
                    side2Membership,
                    newClassDefs,
                    classNames,
                    COMMON_CLASS_NAME,
                )

    sortedKerningPerScript = sorted(kerningPerScript.items())
    for scripts, pairs in sortedKerningPerScript:
        if set(scripts) == COMMON_SCRIPTS_SET:
            continue
        script = "_".join(scripts).replace(COMMON_SCRIPT, COMMON_CLASS_NAME)
        for pair in pairs:
            if (
                pair.firstIsClass
                and pair.side1 not in existingSide1Classes
                and pair.side1 not in newSide1Classes
            ):
                addClassDefinition(
                    "kern1",
                    pair.side1,
                    newSide1Classes,
                    side1Membership,
                    newClassDefs,
                    classNames,
                    script,
                )
            if (
                pair.secondIsClass
                and pair.side2 not in existingSide2Classes
                and pair.side2 not in newSide2Classes
            ):
                addClassDefinition(
                    "kern2",
                    pair.side2,
                    newSide2Classes,
                    side2Membership,
                    newClassDefs,
                    classNames,
                    script,
                )

    return newClassDefs, newSide1Classes, newSide2Classes


def addClassDefinition(
    prefix, group, classes, originalMembership, classDefs, classNames, script
):
    firstGlyph = next(iter(group))
    originalGroupName = originalMembership[firstGlyph]
    groupName = f"{prefix}.{script}.{originalGroupName}"
    className = ast.makeFeaClassName(groupName, classNames)
    classNames.add(className)
    classDef = ast.makeGlyphClassDefinition(className, group)
    classes[group] = classDefs[className] = classDef


def log_redefined_group(
    side: str, name: str, group: tuple[str, ...], font: Any, members: set[str]
) -> None:
    LOGGER.warning(
        "incompatible %s groups: %s was previously %s, %s tried to make it %s",
        side,
        name,
        sorted(group),
        font,
        sorted(members),
    )


def log_regrouped_glyph(
    side: str, name: str, original_name: str, font: Any, member: str
) -> None:
    LOGGER.warning(
        "incompatible %s groups: %s tries to put glyph %s in group %s, but it's already in %s, "
        "discarding",
        side,
        font,
        member,
        name,
        original_name,
    )
