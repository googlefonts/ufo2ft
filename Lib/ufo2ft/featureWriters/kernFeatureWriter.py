from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Iterator, Mapping

from fontTools import unicodedata
from fontTools.unicodedata import script_horizontal_direction

from ufo2ft.constants import COMMON_SCRIPT, INDIC_SCRIPTS, USE_SCRIPTS
from ufo2ft.featureWriters import BaseFeatureWriter, ast
from ufo2ft.util import (
    DFLT_SCRIPTS,
    classifyGlyphs,
    describe_ufo,
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


@dataclass(frozen=True, order=False)
class KerningPair:
    __slots__ = ("side1", "side2", "value")

    side1: str | tuple[str, ...]
    side2: str | tuple[str, ...]
    value: float

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
      splitting by direction, as previously done.
        * Partition the first and second side of a pair by script and emit only
          those with the same script (e.g. `a` and `b` are both "Latn", `period`
          and `period` are both "Default", but `a` and `a-cy` would mix "Latn"
          and "Cyrl" and are dropped) or those that kern an explicit against a
          "common" or "inherited" script, e.g. `a` and `period`.
        * Glyphs can have multiple scripts assigned to them (legitimately, e.g.
          U+0951 DEVANAGARI STRESS SIGN UDATTA, or for random reasons like
          having both `sub h by h.sc` and `sub Etaprosgegrammeni by h.sc;`).
          Only scripts that were determined earlier to be supported by the font
          will be considered. Usually, we will emit pairs where both sides have
          the same script and no splitting is necessary. The only mixed script
          pairs we emit are common or inherited (Zyyy or Zinh) against explicit
          (e.g. Latn) scripts. A glyph can be part of both for weird reasons, so
          we always treat any glyph with a common or inherited script as a
          purely common (not inherited) glyph for bucketing purposes. This
          avoids creating overlapping groups with the multi-script glyph in a
          lookup.
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
        # markers), if the font contains kerning and the feaFile contains `kern`
        # or `dist` feature blocks, but we have no insertion markers (or they
        # were misspelt and ignored), warn the user that the kerning blocks in
        # the feaFile take precedence and other kerning is dropped.
        if (
            self.mode == "skip"
            and font.kerning
            and ctx.existingFeatures & self.features
            and not ctx.insertComments
        ):
            LOGGER.warning(
                "%s: font has kerning, but also manually written kerning features "
                "without an insertion comment. Dropping the former.",
                describe_ufo(font),
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

        lookupGroups = []
        for _, lookupGroup in sorted(lookups.items()):
            lookupGroups.extend(lookupGroup.values())

        # NOTE: We don't write classDefs because we literalise all classes.
        self._insert(
            feaFile=feaFile,
            classDefs=newClassDefs,
            lookups=lookupGroups,
            features=[features[tag] for tag in ["kern", "dist"] if tag in features],
        )
        return True

    def getKerningData(self):
        side1Groups, side2Groups = self.getKerningGroups()
        pairs = self.getKerningPairs(side1Groups, side2Groups)
        # side(1|2)Classes and classDefs will hold the feaLib AST to write out.
        return SimpleNamespace(
            side1Classes={}, side2Classes={}, classDefs={}, pairs=pairs
        )

    def getKerningGroups(self):
        font = self.context.font
        allGlyphs = self.context.glyphSet
        side1Groups = {}
        side2Groups = {}
        side1Membership = {}
        side2Membership = {}
        for name, members in font.groups.items():
            # prune non-existent or skipped glyphs
            members = {g for g in members if g in allGlyphs}
            if not members:
                # skip empty groups
                continue
            # skip groups without UFO3 public.kern{1,2} prefix
            if name.startswith(SIDE1_PREFIX):
                side1Groups[name] = tuple(sorted(members))
                name_truncated = name[len(SIDE1_PREFIX) :]
                for member in members:
                    side1Membership[member] = name_truncated
            elif name.startswith(SIDE2_PREFIX):
                side2Groups[name] = tuple(sorted(members))
                name_truncated = name[len(SIDE2_PREFIX) :]
                for member in members:
                    side2Membership[member] = name_truncated
        self.context.side1Membership = side1Membership
        self.context.side2Membership = side2Membership
        return side1Groups, side2Groups

    def getKerningPairs(self, side1Classes, side2Classes):
        glyphSet = self.context.glyphSet
        font = self.context.font
        kerning = font.kerning
        quantization = self.options.quantization

        kerning = font.kerning
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

    def _makeKerningLookup(self, name, ignoreMarks=True):
        lookup = ast.LookupBlock(name)
        if ignoreMarks and self.options.ignoreMarks:
            # We only want to filter the spacing marks
            marks = set(self.context.gdefClasses.mark or []) & set(
                self.context.glyphSet.keys()
            )

            spacing = []
            if marks:
                spacing = [mark for mark in marks if self.context.font[mark].width != 0]
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

    def knownScriptsPerCodepoint(self, uv: int) -> set[str]:
        if not self.context.knownScripts:
            # If there are no languagesystems and nothing to derive from Unicode
            # codepoints, consider everything common; it'll all end in DFLT/dflt
            # anyway.
            return {COMMON_SCRIPT}
        else:
            script_extension = unicodeScriptExtensions(uv)
            return script_extension & (self.context.knownScripts | DFLT_SCRIPTS)

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

        for script, pairs in kerningPerScript.items():
            scriptLookups = lookups.setdefault(script, {})

            key = f"kern_{script}{suffix}"
            lookup = scriptLookups.get(key)
            if not lookup:
                # For neatness:
                lookup = self._makeKerningLookup(
                    key.replace(COMMON_SCRIPT, COMMON_CLASS_NAME),
                    ignoreMarks=ignoreMarks,
                )
                scriptLookups[key] = lookup
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
                scriptIsRtl = script_horizontal_direction(script, "LTR") == "RTL"
                # Numbers are always shaped LTR even in RTL scripts:
                pairIsRtl = scriptIsRtl and "L" not in bidiTypes
                rule = self._makePairPosRule(
                    pair, side1Classes, side2Classes, pairIsRtl
                )
                lookup.statements.append(rule)

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
        if isKernBlock and COMMON_SCRIPT in lookups:
            languages = feaLanguagesByScript.get("DFLT", ["dflt"])
            ast.addLookupReferences(
                feature, lookups[COMMON_SCRIPT].values(), "DFLT", languages
            )

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
                lookupsForThisScript = []
                for dfltScript in DFLT_SCRIPTS:
                    if dfltScript in lookups:
                        lookupsForThisScript.extend(lookups[dfltScript].values())
                lookupsForThisScript.extend(lookups[script].values())
                # Register the lookups for all languages defined in the feature
                # file for the script, otherwise kerning is not applied if any
                # language is set at all.
                languages = feaLanguagesByScript.get(tag, ["dflt"])
                ast.addLookupReferences(feature, lookupsForThisScript, tag, languages)


def splitKerning(pairs, glyphScripts):
    # Split kerning into per-script buckets, so we can post-process them before
    # continuing.
    kerningPerScript = {}
    for pair in pairs:
        for script, splitPair in partitionByScript(pair, glyphScripts):
            kerningPerScript.setdefault(script, []).append(splitPair)

    for pairs in kerningPerScript.values():
        pairs.sort()

    return kerningPerScript


def partitionByScript(
    pair: KerningPair,
    glyphScripts: Mapping[str, set[str]],
) -> Iterator[tuple[str, KerningPair]]:
    """Split a potentially mixed-script pair into pairs that make sense based
    on the dominant script, and yield each combination with its dominant script."""

    side1Scripts: dict[str, set[str]] = {}
    side2Scripts: dict[str, set[str]] = {}
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
        for script in scripts:
            side1Scripts.setdefault(script, set()).add(glyph)
    for glyph in pair.secondGlyphs:
        scripts = glyphScripts.get(glyph, DFLT_SCRIPTS)
        if scripts & DFLT_SCRIPTS:
            scripts = COMMON_SCRIPTS_SET
        for script in scripts:
            side2Scripts.setdefault(script, set()).add(glyph)

    for firstScript, secondScript in itertools.product(side1Scripts, side2Scripts):
        # Preserve the type (glyph or class) of each side.
        localGlyphs: set[str] = set()
        localSide1: str | tuple[str, ...]
        localSide2: str | tuple[str, ...]
        if pair.firstIsClass:
            localSide1 = tuple(sorted(side1Scripts[firstScript]))
            localGlyphs.update(localSide1)
        else:
            assert len(side1Scripts[firstScript]) == 1
            (localSide1,) = side1Scripts[firstScript]
            localGlyphs.add(localSide1)
        if pair.secondIsClass:
            localSide2 = tuple(sorted(side2Scripts[secondScript]))
            localGlyphs.update(localSide2)
        else:
            assert len(side2Scripts[secondScript]) == 1
            (localSide2,) = side2Scripts[secondScript]
            localGlyphs.add(localSide2)

        if firstScript == secondScript or secondScript == COMMON_SCRIPT:
            localScript = firstScript
        elif firstScript == COMMON_SCRIPT:
            localScript = secondScript
        # Two different explicit scripts:
        else:
            LOGGER.info(
                "Skipping kerning pair <%s %s %s> with mixed script (%s, %s)",
                pair.side1,
                pair.side2,
                pair.value,
                firstScript,
                secondScript,
            )
            continue

        yield localScript, KerningPair(
            localSide1,
            localSide2,
            pair.value,
        )


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
    if COMMON_SCRIPT in kerningPerScript:
        common_pairs = kerningPerScript[COMMON_SCRIPT]
        for pair in common_pairs:
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
    for script, pairs in sortedKerningPerScript:
        if script == COMMON_SCRIPT:
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
