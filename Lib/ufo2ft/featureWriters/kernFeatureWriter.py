from __future__ import annotations

import itertools
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING

from fontTools import unicodedata
from fontTools.feaLib import ast

from ufo2ft.constants import COMMON_SCRIPT, INDIC_SCRIPTS, USE_SCRIPTS
from ufo2ft.errors import Error
from ufo2ft.featureWriters import BaseFeatureWriter
from ufo2ft.featureWriters.ast import addLookupReferences, makeLookupFlag
from ufo2ft.util import DFLT_SCRIPTS, classifyGlyphs, quantize

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
BAD_BIDIS = {"R", "L"}


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

    __slots__ = ("side1", "side2", "value", "scripts", "bidiTypes")

    def __init__(
        self,
        side1: str | set[str],  # XXX: use sorted tuple instead?
        side2: str | set[str],  # XXX: use sorted tuple instead?
        value: float,
        scripts: set[str],
        bidiTypes: set[str],
    ) -> None:
        if not isinstance(side1, (str, set)):
            raise TypeError(type(side1))
        if not isinstance(side2, (str, set)):
            raise TypeError(type(side2))
        self.side1 = side1
        self.side2 = side2
        self.value: float = value
        self.scripts: set[str] = scripts
        self.bidiTypes: set[str] = bidiTypes

    def __lt__(self, other: KerningPair) -> bool:
        if not isinstance(other, KerningPair):
            return NotImplemented

        selfTuple = (
            self.firstIsClass,
            self.secondIsClass,
            sorted(self.firstGlyphs),
            sorted(self.secondGlyphs),
        )
        otherTuple = (
            other.firstIsClass,
            other.secondIsClass,
            sorted(other.firstGlyphs),
            sorted(other.secondGlyphs),
        )
        return selfTuple < otherTuple

    def __eq__(self, other: KerningPair) -> bool:
        if other.__class__ is not self.__class__:
            return False

        return (
            self.firstIsClass,
            self.secondIsClass,
            sorted(self.firstGlyphs),
            sorted(self.secondGlyphs),
            self.value,
            self.scripts,
            self.bidiTypes,
        ) == (
            other.firstIsClass,
            other.secondIsClass,
            sorted(other.firstGlyphs),
            sorted(other.secondGlyphs),
            other.value,
            other.scripts,
            other.bidiTypes,
        )

    def partitionByScript(
        self, glyphScripts: Mapping[str, set[str]], bidiGlyphs: dict[str, set[str]]
    ) -> Iterator[tuple[str, KerningPair]]:
        """Split a potentially mixed-script pair into pairs that make sense based
        on the dominant script, and yield each combination with its dominant script."""

        # First, partition the pair by their assigned scripts. Glyphs can have
        # multiple scripts assigned to them (legitimately, e.g. U+0951
        # DEVANAGARI STRESS SIGN UDATTA, or for random reasons like having both
        # `sub h by h.sc` and `sub Etaprosgegrammeni by h.sc;`). Usually, we
        # will emit pairs where both sides have the same script and no splitting
        # is necessary. The only mixed script pairs we emit are implicit (e.g.
        # Zyyy) against explicit (e.g. Latn) scripts. A glyph can be part of
        # both for weird reasons, so we always treat any glyph with an implicit
        # script as a purely implicit glyph. This avoids creating overlapping
        # groups with the multi-script glyph in a lookup.
        side1Scripts: dict[str, set[str]] = {}
        side2Scripts: dict[str, set[str]] = {}
        for glyph in self.firstGlyphs:
            scripts = glyphScripts.get(glyph, COMMON_SCRIPTS_SET)
            # If a glyph is both common *and* another script, treat it as
            # common. This ensures that a pair appears to the shaper exactly
            # once (as long as every script sees at most 2 lookups (disregarding
            # mark lookups), the common one and the script-specific one.
            if scripts & COMMON_SCRIPTS_SET:
                scripts = scripts & COMMON_SCRIPTS_SET
            for script in scripts:
                side1Scripts.setdefault(script, set()).add(glyph)
        for glyph in self.secondGlyphs:
            scripts = glyphScripts.get(glyph, COMMON_SCRIPTS_SET)
            if scripts & COMMON_SCRIPTS_SET:
                scripts = scripts & COMMON_SCRIPTS_SET
            for script in scripts:
                side2Scripts.setdefault(script, set()).add(glyph)

        # NOTE: Always split a pair, even if both sides have matching scripts,
        # because turning all classes into literal ones below makes some kerning
        # work, whereas emitting some as-is results in a mixture of literal and
        # named glyph classes, which for some reason drops a lot of kerning
        # (e.g. run kerning-validator on Mystery.ufo).
        for firstScript, secondScript in itertools.product(side1Scripts, side2Scripts):
            # Preserve the type (glyph or class) of each side.
            localGlyphs: set[str] = set()
            if self.firstIsClass:
                localSide1: str | set[str] = side1Scripts[firstScript]
                localGlyphs.update(localSide1)
            else:
                assert len(side1Scripts[firstScript]) == 1
                (localSide1,) = side1Scripts[firstScript]
                localGlyphs.add(localSide1)
            if self.secondIsClass:
                localSide2: str | set[str] = side2Scripts[secondScript]
                localGlyphs.update(localSide2)
            else:
                assert len(side2Scripts[secondScript]) == 1
                (localSide2,) = side2Scripts[secondScript]
                localGlyphs.add(localSide2)

            # Handle very obvious common cases: one script, same on both sides
            if firstScript == secondScript or secondScript in DFLT_SCRIPTS:
                localScript = firstScript
            # First is common, second is single script
            elif firstScript in DFLT_SCRIPTS:
                localScript = secondScript
            # One script and it's different on both sides and it's not common
            else:
                logger = ".".join([self.__class__.__module__, self.__class__.__name__])
                logging.getLogger(logger).info(
                    "Skipping kerning pair <%s %s %s> with mixed script (%s, %s)",
                    self.displayFirst,
                    self.displaySecond,
                    self.value,
                    firstScript,
                    secondScript,
                )
                continue

            bidiTypes = set()
            for key, glyphs in bidiGlyphs.items():
                if not localGlyphs.isdisjoint(glyphs):
                    bidiTypes.add(key)
            if bidiTypes.issuperset(BAD_BIDIS):
                logger = ".".join([self.__class__.__module__, self.__class__.__name__])
                logging.getLogger(logger).info(
                    "Skipping kerning pair <%s %s %s> with ambiguous direction",
                    self.displayFirst,
                    self.displaySecond,
                    self.value,
                )
                continue

            yield localScript, KerningPair(
                localSide1,
                localSide2,
                self.value,
                scripts={localScript},
                bidiTypes=bidiTypes,
            )

    @property
    def firstIsClass(self) -> bool:
        return isinstance(self.side1, set)

    @property
    def secondIsClass(self) -> bool:
        return isinstance(self.side2, set)

    @property
    def firstGlyphs(self) -> set[str]:
        if isinstance(self.side1, set):
            return self.side1
        else:
            return {self.side1}

    @property
    def secondGlyphs(self) -> set[str]:
        if isinstance(self.side2, set):
            return self.side2
        else:
            return {self.side2}

    @property
    def glyphs(self) -> set[str]:
        return self.firstGlyphs | self.secondGlyphs

    @property
    def displayFirst(self) -> str | tuple[str, ...]:
        return self.side1 if isinstance(self.side1, str) else tuple(sorted(self.side1))

    @property
    def displaySecond(self) -> str | tuple[str, ...]:
        return self.side2 if isinstance(self.side2, str) else tuple(sorted(self.side2))

    def __repr__(self) -> str:
        return "<{} {} {} {} {} {}>".format(
            self.__class__.__name__,
            self.displayFirst,
            self.displaySecond,
            self.value,
            self.scripts,
            self.bidiTypes,
        )

    @property
    def uniqueness_key(
        self,
    ) -> tuple[str | tuple[str, ...], str | tuple[str, ...], float]:
        """Returns a key for deduplication."""
        return (self.displayFirst, self.displaySecond, self.value)

    def make_pair_pos_rule(self, script: str) -> ast.PairPosStatement:
        script_is_rtl = unicodedata.script_horizontal_direction(script) == "RTL"
        # Numbers are always shaped LTR even in RTL scripts:
        assert not self.bidiTypes.issuperset(BAD_BIDIS)
        pair_is_rtl = "L" not in self.bidiTypes
        rtl = script_is_rtl and pair_is_rtl
        enumerated = self.firstIsClass ^ self.secondIsClass
        valuerecord = ast.ValueRecord(
            xPlacement=self.value if rtl else None,
            yPlacement=0 if rtl else None,
            xAdvance=self.value,
            yAdvance=0 if rtl else None,
        )
        # XXX: Do this elsewhere where we can cache the result?
        if isinstance(self.side1, str):
            side1 = ast.GlyphName(self.side1)
        else:
            side1 = ast.GlyphClass([ast.GlyphName(g) for g in sorted(self.side1)])
        if isinstance(self.side2, str):
            side2 = ast.GlyphName(self.side2)
        else:
            side2 = ast.GlyphClass([ast.GlyphName(g) for g in sorted(self.side2)])
        return ast.PairPosStatement(
            glyphs1=side1,
            valuerecord1=valuerecord,
            glyphs2=side2,
            valuerecord2=None,
            enumerated=enumerated,
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

        # TODO: Also include substitution information from Designspace rules to
        # correctly the scripts of variable substitution glyphs, maybe add
        # `glyphUnicodeMapping: dict[str, int] | None` to `BaseFeatureCompiler`?
        cmap = self.makeUnicodeToGlyphNameMapping()
        gsub = self.compileGSUB()
        scriptGlyphs = classifyGlyphs(script_extensions_for_codepoint, cmap, gsub)
        bidiGlyphs = classifyGlyphs(unicodeBidiType, cmap, gsub)
        ctx.bidiGlyphs = bidiGlyphs

        glyphScripts = {}
        for script, glyphs in scriptGlyphs.items():
            for g in glyphs:
                glyphScripts.setdefault(g, set()).add(script)
        ctx.glyphScripts = glyphScripts

        ctx.kerning = self.getKerningData(
            font,
            self.options.quantization,
            scriptGlyphs,  # type: ignore
            bidiGlyphs,  # type: ignore
            self.getOrderedGlyphSet(),
        )

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

        lookupGroups = []
        for _, lookupGroup in sorted(lookups.items()):
            lookupGroups.extend(lookupGroup.values())

        # NOTE: We don't write classDefs because we literalise all classes.
        self._insert(
            feaFile=feaFile,
            lookups=lookupGroups,
            features=[features[tag] for tag in ["kern", "dist"] if tag in features],
        )
        return True

    @classmethod
    def getKerningData(
        cls,
        font: Any,
        quantization: int,
        scriptGlyphs: Mapping[str, set[str]],
        bidiGlyphs: Mapping[str, set[str]],
        glyphSet: dict[str, Any],
    ) -> SimpleNamespace:
        side1Groups, side2Groups = cls.getKerningGroups(font, glyphSet)
        pairs = cls.getKerningPairs(
            font,
            side1Groups,
            side2Groups,
            quantization,
            scriptGlyphs,
            bidiGlyphs,
            glyphSet,
        )
        return SimpleNamespace(
            side1Groups=side1Groups, side2Groups=side2Groups, pairs=pairs
        )

    @staticmethod
    def getKerningGroups(
        font, glyphSet
    ) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        side1Groups: dict[str, set[str]] = {}
        side2Groups: dict[str, set[str]] = {}
        for name, members in font.groups.items():
            # prune non-existent or skipped glyphs
            # XXX: use sorted tuple instead?
            members = {g for g in members if g in glyphSet}
            if not members:
                # skip empty groups
                continue
            # skip groups without UFO3 public.kern{1,2} prefix
            if name.startswith(SIDE1_PREFIX):
                side1Groups[name] = members
            elif name.startswith(SIDE2_PREFIX):
                side2Groups[name] = members
        return side1Groups, side2Groups

    @staticmethod
    def getKerningPairs(
        font: Any,
        side1Groups: Mapping[str, set[str]],
        side2Groups: Mapping[str, set[str]],
        quantization: int,
        scriptGlyphs: Mapping[str, set[str]],
        bidiGlyphs: Mapping[str, set[str]],
        glyphSet: Mapping[str, Any],
    ) -> list[KerningPair]:
        kerning: Mapping[tuple[str, str], float] = font.kerning
        result: list[KerningPair] = []
        for (side1, side2), value in kerning.items():
            firstIsClass, secondIsClass = (side1 in side1Groups, side2 in side2Groups)
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

            pair_glyphs = set()
            if firstIsClass:
                side1 = side1Groups[side1]
                pair_glyphs.update(side1)
            else:
                pair_glyphs.add(side1)
            if secondIsClass:
                side2 = side2Groups[side2]
                pair_glyphs.update(side2)
            else:
                pair_glyphs.add(side2)

            value = quantize(value, quantization)
            scripts = set()
            for key, glyphs in scriptGlyphs.items():
                if not pair_glyphs.isdisjoint(glyphs):
                    scripts.add(key)
            # XXX: Do we need to do BiDi types here when they only really matter
            # for splitting?
            bidiTypes = set()
            for key, glyphs in bidiGlyphs.items():
                if not pair_glyphs.isdisjoint(glyphs):
                    bidiTypes.add(key)
            result.append(KerningPair(side1, side2, value, scripts, bidiTypes))

        return result

    def _makeKerningLookups(self) -> dict[str, dict[str, ast.LookupBlock]]:
        lookups: dict[str, dict[str, ast.LookupBlock]] = {}
        glyphScripts = self.context.glyphScripts
        pairs = self.context.kerning.pairs
        ignoreMarks: bool = self.options.ignoreMarks
        bidiGlyphs: dict[str, set[str]] = self.context.bidiGlyphs
        if ignoreMarks:
            marks = self.context.gdefClasses.mark
            basePairs, markPairs = self._splitBaseAndMarkPairs(pairs, marks)
            if basePairs:
                make_split_script_kern_lookups(
                    lookups, basePairs, glyphScripts, bidiGlyphs, ignoreMarks
                )
            if markPairs:
                make_split_script_kern_lookups(
                    lookups,
                    markPairs,
                    glyphScripts,
                    bidiGlyphs,
                    ignoreMarks=False,
                    suffix="_marks",
                )
        else:
            make_split_script_kern_lookups(
                lookups, pairs, glyphScripts, bidiGlyphs, ignoreMarks
            )
        return lookups

    @staticmethod
    def _splitBaseAndMarkPairs(pairs, marks):
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

    @staticmethod
    def _registerLookups(
        feature: ast.FeatureBlock, lookups: dict[str, dict[str, ast.LookupBlock]]
    ) -> None:
        # Ensure we have kerning for pure common script runs (e.g. ">1")
        is_kern_block = feature.name == "kern"
        if is_kern_block and COMMON_SCRIPT in lookups:
            addLookupReferences(
                feature, lookups[COMMON_SCRIPT].values(), "DFLT", ["dflt"]
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
        if is_kern_block:
            scripts_to_reference = lookups.keys() - DIST_ENABLED_SCRIPTS
        else:
            scripts_to_reference = DIST_ENABLED_SCRIPTS.intersection(lookups.keys())
        for script in sorted(scripts_to_reference - DFLT_SCRIPTS):
            for tag in unicodedata.ot_tags_from_script(script):
                # Insert line breaks between statements for niceness :).
                if feature.statements:
                    feature.statements.append(ast.Comment(""))
                # We have something for this script. First add the default
                # lookups, then the script-specific ones
                lookups_for_this_script = []
                for dflt_script in DFLT_SCRIPTS:
                    if dflt_script in lookups:
                        lookups_for_this_script.extend(lookups[dflt_script].values())
                lookups_for_this_script.extend(lookups[script].values())
                # NOTE: We always use the `dflt` language because there is no
                # language-specific kerning to be derived from UFO (kerning.plist)
                # sources and we are independent of what's going on in the rest of
                # the features.fea file.
                addLookupReferences(feature, lookups_for_this_script, tag, ["dflt"])


def script_extensions_for_codepoint(uv: int) -> set[str]:
    return unicodedata.script_extension(chr(uv))


def make_split_script_kern_lookups(
    lookups: dict[str, dict[str, ast.LookupBlock]],
    pairs: list[KerningPair],
    glyphScripts: Mapping[str, set[str]],
    bidiGlyphs: dict[str, set[str]],
    ignoreMarks: bool,
    suffix: str = "",
) -> None:
    kerning_per_script = split_kerning(pairs, glyphScripts, bidiGlyphs)
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
            rule = pair.make_pair_pos_rule(script)
            lookup.statements.append(rule)


def split_kerning(
    pairs: list[KerningPair],
    glyphScripts: Mapping[str, set[str]],
    bidiGlyphs: dict[str, set[str]],
) -> dict[str, list[KerningPair]]:
    # Split kerning into per-script buckets, so we can post-process them before
    # continuing. NOTE: this replaces class names (`@kern1.something`) with
    # class literals (`[a b c]`). There is no space saving to be had by trying
    # to assign them names again, because names don't exist at the OpenType
    # level.
    kerning_per_script: dict[str, list[KerningPair]] = {}
    for pair in pairs:
        for script, split_pair in pair.partitionByScript(glyphScripts, bidiGlyphs):
            kerning_per_script.setdefault(script, []).append(split_pair)

    # Sanity checking to ensure we don't produce overlapping groups or
    # duplicates in a lookup. Remove once reasonably sure we never do this.
    for script, pairs in kerning_per_script.items():
        try:
            ensure_unique_class_class_membership(pairs)
            ensure_no_duplicates(pairs)
        except Exception as e:
            raise Error(f"In {script}: {e}") from e

    # Sort Kerning pairs so that glyph to glyph comes first, then glyph to
    # class, class to glyph, and finally class to class. This makes "kerning
    # exceptions" work, where more specific glyph pair values override less
    # specific class kerning.
    for pairs in kerning_per_script.values():
        pairs.sort()

    return kerning_per_script


def ensure_unique_class_class_membership(pairs: list[KerningPair]) -> None:
    """Raises an exception when a glyph is found to belong to multiple classes
    per side.

    Group membership must be exclusive per side per lookup (script bucket).
    """

    kern1_membership: dict[str, set[str]] = {}
    kern2_membership: dict[str, set[str]] = {}

    for pair in pairs:
        if pair.firstIsClass:
            kern1 = pair.firstGlyphs
            for name in kern1:
                if name not in kern1_membership:
                    kern1_membership[name] = kern1
                elif kern1_membership[name] != kern1:
                    membership = kern1_membership[name]
                    raise Exception(
                        f"Glyph {name} in multiple kern1 groups, originally "
                        f"in {membership} but now also in {kern1} according "
                        f"to pair {pair}"
                    )
        if pair.secondIsClass:
            kern2 = pair.secondGlyphs
            for name in kern2:
                if name not in kern2_membership:
                    kern2_membership[name] = kern2
                elif kern2_membership[name] != kern2:
                    membership = kern2_membership[name]
                    raise Exception(
                        f"Glyph {name} in multiple kern2 groups, originally "
                        f"in {membership} but now also in {kern2} according "
                        f"to pair {pair}"
                    )


def ensure_no_duplicates(pairs: list[KerningPair]) -> None:
    unique_pairs: set[tuple[str | tuple[str, ...], str | tuple[str, ...], float]]
    unique_pairs = set()
    for pair in pairs:
        pair_key = pair.uniqueness_key
        if pair_key not in unique_pairs:
            unique_pairs.add(pair_key)
        else:
            raise Exception(f"Duplicate pair {pair}")
