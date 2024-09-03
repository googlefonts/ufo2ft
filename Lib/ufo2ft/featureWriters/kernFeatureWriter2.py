"""Alternative implementation of KernFeatureWriter.

This behaves like the primary kern feature writer, with the important difference
of grouping kerning data into lookups by kerning direction, not script, like the
feature writer in ufo2ft v2.30 and older did.

The original idea for the primary splitter was to generate smaller, easier to
pack lookups for each script exclusively, as cross-script kerning dos not work
in browsers. However, other applications may allow it, e.g. Adobe's InDesign.
Subsequently, it was modified to clump together lookups that cross-reference
each other's scripts, negating the size advantages if you design fonts with
cross-script kerning for designer ease.

As a special edge case, InDesign's default text shaper does not properly itemize
text runs, meaning it may group different scripts into the same run unless the
user specifically marks some text as being a specific script or language. To
make all kerning reachable in that case, it must be put into a single broad LTR,
RTL or neutral direction lookup instead of finer script clusters. That will make
it work in all cases, including when there is no cross-script kerning to fuse
different lookups together.

Testing showed that size benefits are clawed back with the use of the HarfBuzz
repacker (during compilation) and GPOS compression (after compilation) at
acceptable speed.
"""

from __future__ import annotations

import enum
import itertools
import logging
import sys
from collections import OrderedDict
from types import SimpleNamespace
from typing import Any, Iterator, Mapping, cast

import fontTools.feaLib.ast as fea_ast
from fontTools import unicodedata
from fontTools.designspaceLib import DesignSpaceDocument
from fontTools.feaLib.variableScalar import Location as VariableScalarLocation
from fontTools.feaLib.variableScalar import VariableScalar
from fontTools.ufoLib.kerning import lookupKerningValue
from fontTools.unicodedata import script_horizontal_direction

from ufo2ft.featureWriters import BaseFeatureWriter, ast
from ufo2ft.util import (
    DFLT_SCRIPTS,
    classifyGlyphs,
    collapse_varscalar,
    describe_ufo,
    get_userspace_location,
    quantize,
)

from .kernFeatureWriter import (
    AMBIGUOUS_BIDIS,
    DIST_ENABLED_SCRIPTS,
    LTR_BIDI_TYPES,
    RTL_BIDI_TYPES,
    SIDE1_PREFIX,
    SIDE2_PREFIX,
    KerningPair,
    addClassDefinition,
    log_redefined_group,
    log_regrouped_glyph,
)

if sys.version_info < (3, 10):
    from typing_extensions import TypeAlias
else:
    from typing import TypeAlias

LOGGER = logging.getLogger(__name__)

KerningGroup: TypeAlias = "Mapping[str, tuple[str, ...]]"


class Direction(enum.Enum):
    Neutral = "dflt"
    LeftToRight = "ltr"
    RightToLeft = "rtl"

    def __lt__(self, other: Direction) -> bool:
        if not isinstance(other, Direction):
            return NotImplemented

        return self.name < other.name


class KernContext(SimpleNamespace):
    bidiGlyphs: dict[Direction, set[str]]
    compiler: Any
    default_source: Any
    existingFeatures: Any
    feaFile: Any
    feaLanguagesByTag: dict[str, list[str]]
    font: Any
    gdefClasses: Any
    glyphBidi: dict[str, set[Direction]]
    glyphDirection: dict[str, set[Direction]]
    glyphSet: OrderedDict[str, Any]
    insertComments: Any
    isVariable: bool
    kerning: Any
    knownScripts: set[str]
    side1Membership: dict[str, str]
    side2Membership: dict[str, str]
    todo: Any


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
      far, so we can determine the bidirectionality class, so we can later
      filter out kerning pairs that would mix RTL and LTR glyphs, which will not
      occur in applications, and put the pairs into their correct lookup.
      Unicode BiDi classes R and AL are considered R. Common characters and
      numbers are considered neutral even when their BiDi class says otherwise,
      so they'll end up in the common lookup available to all scripts.
    * Get the kerning groups from the UFO and filter out glyphs not in the
      glyphset and empty groups. Remember which group a glyph is a member of,
      for kern1 and kern2, so we can later reconstruct per-direction groups.
    * Get the bare kerning pairs from the UFO, filtering out pairs with unknown
      groups or glyphs not in the glyphset and (redundant) zero class-to-class
      kernings and optionally quantizing kerning values.
    * Optionally, split kerning pairs into base (only base against base) and
      mark (mixed mark and base) pairs, according to the glyphs' GDEF category,
      so that kerning against marks can be accounted for correctly later.
    * Go through all kerning pairs and split them up by direction, to put them
      in different lookups. In pairs with common glyphs, assume the direction of
      the dominant script, in pairs of common glyphs, assume no direction. Pairs
      with clashing script directions are dropped.
        * Partition the first and second side of a pair by BiDi direction (as
          above) and emit only those with the same direction or a strong
          direction and neutral one.
        * Discard pairs that mix RTL and LTR BiDi types, because they won't show
          up in applications due to how Unicode text is split into runs.
        * Glyphs will have only one direction assigned to them. * Preserve the
          type of the kerning pair, so class-to-class kerning stays that way,
          even when there's only one glyph on each side.
    * Reconstruct kerning group names for the newly split classes. This is done
      for debuggability; it makes no difference for the final font binary.
        * This first looks at the neutral lookups and then all others, assigning
          new group names are it goes. A class like `@kern1.something = [foo bar
          baz]` may be split up into `@kern1.dflt.something = [foo]` and
          `@kern1.ltr.something = [bar baz]`. Note: If there is no dedicated
          dflt lookup, common glyph classes like `[foo]` might carry the name
          `@kern1.ltr.foo` if the class was first encountered while going over
          the ltr lookup.
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
        ctx: KernContext = cast(
            KernContext, super().setContext(font, feaFile, compiler=compiler)
        )

        if hasattr(font, "findDefault"):
            ctx.default_source = font.findDefault().font
        else:
            ctx.default_source = font

        # Unless we use the legacy append mode (which ignores insertion
        # markers), if the font (Designspace: default source) contains kerning
        # and the feaFile contains `kern` or `dist` feature blocks, but we have
        # no insertion markers (or they were misspelt and ignored), warn the
        # user that the kerning blocks in the feaFile take precedence and other
        # kerning is dropped.
        if (
            self.mode == "skip"
            and ctx.default_source.kerning
            and ctx.existingFeatures & self.features
            and not ctx.insertComments
        ):
            LOGGER.warning(
                "%s: font has kerning, but also manually written kerning features "
                "without an insertion comment. Dropping the former.",
                describe_ufo(ctx.default_source),
            )

        # Remember which languages are defined for which OT tag, as all
        # generated kerning needs to be registered for the script's `dflt`
        # language, but also all those the designer defined manually. Otherwise,
        # setting any language for a script would deactivate kerning.
        feaLanguagesByScript = ast.getScriptLanguageSystems(feaFile, excludeDflt=False)
        ctx.feaLanguagesByTag = {
            otTag: languages
            for _, languageSystems in feaLanguagesByScript.items()
            for otTag, languages in languageSystems
        }

        ctx.glyphSet = self.getOrderedGlyphSet()
        ctx.gdefClasses = self.getGDEFGlyphClasses()
        ctx.knownScripts = self.guessFontScripts()

        # We need the direction of a glyph (with common characters considered
        # neutral or "dflt") to know in which of the three lookups to put the
        # pair.
        cmap = self.makeUnicodeToGlyphNameMapping()
        gsub = self.compileGSUB()
        extras = self.extraSubstitutions()
        dirGlyphs = classifyGlyphs(unicodeScriptDirection, cmap, gsub, extras)
        neutral_glyphs = (
            ctx.glyphSet.keys()
            - dirGlyphs.get(Direction.LeftToRight, set())
            - dirGlyphs.get(Direction.RightToLeft, set())
        )
        dirGlyphs[Direction.Neutral] = neutral_glyphs
        glyphDirection = {}
        for direction, glyphs in dirGlyphs.items():
            for name in glyphs:
                glyphDirection.setdefault(name, set()).add(direction)
        ctx.glyphDirection = glyphDirection

        # We need the BiDi class of a glyph to reject kerning of RTL glyphs
        # against LTR glyphs.
        ctx.bidiGlyphs = classifyGlyphs(unicodeBidiType, cmap, gsub, extras)
        neutral_glyphs = (
            ctx.glyphSet.keys()
            - ctx.bidiGlyphs.get(Direction.LeftToRight, set())
            - ctx.bidiGlyphs.get(Direction.RightToLeft, set())
        )
        ctx.bidiGlyphs[Direction.Neutral] = neutral_glyphs
        glyphBidi = {}
        for direction, glyphs in ctx.bidiGlyphs.items():
            for name in glyphs:
                glyphBidi.setdefault(name, set()).add(direction)
        ctx.glyphBidi = glyphBidi

        ctx.kerning = extract_kerning_data(ctx, cast(SimpleNamespace, self.options))

        return ctx

    def shouldContinue(self):
        if (
            not self.context.kerning.base_pairs_by_direction
            and not self.context.kerning.mark_pairs_by_direction
        ):
            self.log.debug("No kerning data; skipped")
            return False

        return super().shouldContinue()

    def _write(self):
        self.context: KernContext
        self.options: SimpleNamespace
        lookups = make_kerning_lookups(self.context, self.options)
        if not lookups:
            self.log.debug("kerning lookups empty; skipped")
            return False

        features = make_feature_blocks(self.context, lookups)
        if not features:
            self.log.debug("kerning features empty; skipped")
            return False

        # extend feature file with the new generated statements
        feaFile = self.context.feaFile

        # first add the glyph class definitions
        classDefs = self.context.kerning.classDefs
        newClassDefs = [c for _, c in sorted(classDefs.items())]

        lookupGroups = []
        for _, lookupGroup in sorted(lookups.items(), key=lambda x: x[0].value):
            lookupGroups.extend(
                lkp for lkp in lookupGroup.values() if lkp not in lookupGroups
            )

        self._insert(
            feaFile=feaFile,
            classDefs=newClassDefs,
            lookups=lookupGroups,
            features=[features[tag] for tag in ["kern", "dist"] if tag in features],
        )
        return True


def unicodeBidiType(uv: int) -> Direction | None:
    """Return Direction.RightToLeft for characters with strong RTL
    direction, or Direction.LeftToRight for strong LTR and European and Arabic
    numbers, or None for neutral direction.
    """
    bidiType = unicodedata.bidirectional(chr(uv))
    if bidiType in RTL_BIDI_TYPES:
        return Direction.RightToLeft
    elif bidiType in LTR_BIDI_TYPES:
        return Direction.LeftToRight
    return None


def unicodeScriptDirection(uv: int) -> Direction | None:
    script = unicodedata.script(chr(uv))
    if script in DFLT_SCRIPTS:
        return None
    direction = unicodedata.script_horizontal_direction(script, "LTR")
    if direction == "LTR":
        return Direction.LeftToRight
    elif direction == "RTL":
        return Direction.RightToLeft
    raise ValueError(f"Unknown direction {direction}")


def extract_kerning_data(context: KernContext, options: SimpleNamespace) -> Any:
    side1Groups, side2Groups = get_kerning_groups(context)
    if context.isVariable:
        pairs = get_variable_kerning_pairs(context, options, side1Groups, side2Groups)
    else:
        pairs = get_kerning_pairs(context, options, side1Groups, side2Groups)

    if options.ignoreMarks:
        marks = context.gdefClasses.mark
        base_pairs, mark_pairs = split_base_and_mark_pairs(pairs, marks)
    else:
        base_pairs = pairs
        mark_pairs = []

    base_pairs_by_direction = split_kerning(context, base_pairs)
    mark_pairs_by_direction = split_kerning(context, mark_pairs)

    return SimpleNamespace(
        base_pairs_by_direction=base_pairs_by_direction,
        mark_pairs_by_direction=mark_pairs_by_direction,
        side1Classes={},
        side2Classes={},
        classDefs={},
    )


def get_kerning_groups(context: KernContext) -> tuple[KerningGroup, KerningGroup]:
    allGlyphs = context.glyphSet

    side1Groups: dict[str, tuple[str, ...]] = {}
    side1Membership: dict[str, str] = {}
    side2Groups: dict[str, tuple[str, ...]] = {}
    side2Membership: dict[str, str] = {}

    if isinstance(context.font, DesignSpaceDocument):
        fonts = [source.font for source in context.font.sources]
    else:
        fonts = [context.font]

    for font in fonts:
        assert font is not None
        for name, members in font.groups.items():
            # prune non-existent or skipped glyphs
            members = {g for g in members if g in allGlyphs}
            # skip empty groups
            if not members:
                continue
            # skip groups without UFO3 public.kern{1,2} prefix
            if name.startswith(SIDE1_PREFIX):
                name_truncated = name[len(SIDE1_PREFIX) :]
                known_members = members.intersection(side1Membership.keys())
                if known_members:
                    for glyph_name in known_members:
                        original_name_truncated = side1Membership[glyph_name]
                        if name_truncated != original_name_truncated:
                            log_regrouped_glyph(
                                "first",
                                name,
                                original_name_truncated,
                                font,
                                glyph_name,
                            )
                    # Skip the whole group definition if there is any
                    # overlap problem.
                    continue
                group = side1Groups.get(name)
                if group is None:
                    side1Groups[name] = tuple(sorted(members))
                    for member in members:
                        side1Membership[member] = name_truncated
                elif set(group) != members:
                    log_redefined_group("left", name, group, font, members)
            elif name.startswith(SIDE2_PREFIX):
                name_truncated = name[len(SIDE2_PREFIX) :]
                known_members = members.intersection(side2Membership.keys())
                if known_members:
                    for glyph_name in known_members:
                        original_name_truncated = side2Membership[glyph_name]
                        if name_truncated != original_name_truncated:
                            log_regrouped_glyph(
                                "second",
                                name,
                                original_name_truncated,
                                font,
                                glyph_name,
                            )
                    # Skip the whole group definition if there is any
                    # overlap problem.
                    continue
                group = side2Groups.get(name)
                if group is None:
                    side2Groups[name] = tuple(sorted(members))
                    for member in members:
                        side2Membership[member] = name_truncated
                elif set(group) != members:
                    log_redefined_group("right", name, group, font, members)
    context.side1Membership = side1Membership
    context.side2Membership = side2Membership
    return side1Groups, side2Groups


def get_kerning_pairs(
    context: KernContext,
    options: SimpleNamespace,
    side1Classes: KerningGroup,
    side2Classes: KerningGroup,
) -> list[KerningPair]:
    glyphSet = context.glyphSet
    font = context.font
    kerning: Mapping[tuple[str, str], float] = font.kerning
    quantization = options.quantization

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


def get_variable_kerning_pairs(
    context: KernContext,
    options: SimpleNamespace,
    side1Classes: KerningGroup,
    side2Classes: KerningGroup,
) -> list[KerningPair]:
    designspace: DesignSpaceDocument = context.font
    glyphSet = context.glyphSet
    quantization = options.quantization

    # Gather utility variables for faster kerning lookups.
    # TODO: Do we construct these in code elsewhere?
    assert not (set(side1Classes) & set(side2Classes))
    unified_groups = {**side1Classes, **side2Classes}

    glyphToFirstGroup = {
        glyph_name: group_name  # TODO: Is this overwrite safe? User input is adversarial
        for group_name, glyphs in side1Classes.items()
        for glyph_name in glyphs
    }
    glyphToSecondGroup = {
        glyph_name: group_name
        for group_name, glyphs in side2Classes.items()
        for glyph_name in glyphs
    }

    # Collate every kerning pair in the designspace, as even UFOs that
    # provide no entry for the pair must contribute a value at their
    # source's location in the VariableScalar.
    # NOTE: This is required as the DS+UFO kerning model and the OpenType
    #       variation model handle the absence of a kerning value at a
    #       given location differently:
    #       - DS+UFO:
    #           If the missing pair excepts another pair, take its value;
    #           Otherwise, take a value of 0.
    #       - OpenType:
    #           Always interpolate from other locations, ignoring more
    #           general pairs that this one excepts.
    # See discussion: https://github.com/googlefonts/ufo2ft/pull/635
    all_pairs: set[tuple[str, str]] = set()
    for source in designspace.sources:
        if source.layerName is not None:
            continue
        assert source.font is not None
        all_pairs |= set(source.font.kerning)

    kerning_pairs_in_progress: dict[
        tuple[str | tuple[str, ...], str | tuple[str, ...]], VariableScalar
    ] = {}
    for source in designspace.sources:
        # Skip sparse sources, because they can have no kerning.
        if source.layerName is not None:
            continue
        assert source.font is not None

        location = VariableScalarLocation(
            get_userspace_location(designspace, source.location)
        )

        kerning: Mapping[tuple[str, str], float] = source.font.kerning
        for pair in all_pairs:
            side1, side2 = pair
            firstIsClass = side1 in side1Classes
            secondIsClass = side2 in side2Classes

            # Filter out pairs that reference missing groups or glyphs.
            # TODO: Can we do this outside of the loop? We know the pairs already.
            if not firstIsClass and side1 not in glyphSet:
                continue
            if not secondIsClass and side2 not in glyphSet:
                continue

            # Get the kerning value for this source and quantize, following
            # the DS+UFO semantics described above.
            value = quantize(
                lookupKerningValue(
                    pair,
                    kerning,
                    unified_groups,
                    glyphToFirstGroup=glyphToFirstGroup,
                    glyphToSecondGroup=glyphToSecondGroup,
                ),
                quantization,
            )

            if firstIsClass:
                side1 = side1Classes[side1]
            if secondIsClass:
                side2 = side2Classes[side2]

            # TODO: Can we instantiate these outside of the loop? We know the pairs already.
            var_scalar = kerning_pairs_in_progress.setdefault(
                (side1, side2), VariableScalar()
            )
            # NOTE: Avoid using .add_value because it instantiates a new
            # VariableScalarLocation on each call.
            var_scalar.values[location] = value

    # We may need to provide a default location value to the variation
    # model, find out where that is.
    default_source = context.font.findDefault()
    default_location = VariableScalarLocation(
        get_userspace_location(designspace, default_source.location)
    )

    result = []
    for (side1, side2), value in kerning_pairs_in_progress.items():
        # TODO: Should we interpolate a default value if it's not in the
        # sources, rather than inserting a zero? What would varLib do?
        if default_location not in value.values:
            value.values[default_location] = 0
        value = collapse_varscalar(value)
        pair = KerningPair(side1, side2, value)
        # Ignore zero-valued class kern pairs. They are the most general
        # kerns, so they don't override anything else like glyph kerns would
        # and zero is the default.
        if pair.firstIsClass and pair.secondIsClass and pair.value == 0:
            continue
        result.append(pair)

    return result


def split_base_and_mark_pairs(
    pairs: list[KerningPair], marks: set[str]
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
        elif pair.side1 in marks:
            side1Marks = pair.side1
        else:
            side1Bases = pair.side1

        side2Bases: tuple[str, ...] | str | None = None
        side2Marks: tuple[str, ...] | str | None = None
        if pair.secondIsClass:
            side2Bases = tuple(glyph for glyph in pair.side2 if glyph not in marks)
            side2Marks = tuple(glyph for glyph in pair.side2 if glyph in marks)
        elif pair.side2 in marks:
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


def split_kerning(
    context: KernContext,
    pairs: list[KerningPair],
) -> dict[Direction, list[KerningPair]]:
    # Split kerning into per-direction buckets, so we can drop them into their
    # own lookups.
    glyph_bidi = context.glyphBidi
    glyph_direction = context.glyphDirection
    kerning_per_direction: dict[Direction, list[KerningPair]] = {}
    for pair in pairs:
        for direction, split_pair in partition_by_direction(
            pair, glyph_bidi, glyph_direction
        ):
            kerning_per_direction.setdefault(direction, []).append(split_pair)

    for pairs in kerning_per_direction.values():
        pairs.sort()

    return kerning_per_direction


def partition_by_direction(
    pair: KerningPair,
    glyph_bidi: Mapping[str, set[Direction]],
    glyph_direction: Mapping[str, set[Direction]],
) -> Iterator[tuple[Direction, KerningPair]]:
    """Split a potentially mixed-direction pair into pairs of the same
    or compatible direction."""

    side1Bidis: dict[Direction, set[str]] = {}
    side2Bidis: dict[Direction, set[str]] = {}
    side1Directions: dict[Direction, set[str]] = {}
    side2Directions: dict[Direction, set[str]] = {}
    for glyph in pair.firstGlyphs:
        bidis = glyph_bidi[glyph]
        directions = glyph_direction[glyph]
        for bidi in bidis:
            side1Bidis.setdefault(bidi, set()).add(glyph)
        for direction in directions:
            side1Directions.setdefault(direction, set()).add(glyph)
    for glyph in pair.secondGlyphs:
        bidis = glyph_bidi[glyph]
        directions = glyph_direction[glyph]
        for bidi in bidis:
            side2Bidis.setdefault(bidi, set()).add(glyph)
        for direction in directions:
            side2Directions.setdefault(direction, set()).add(glyph)

    for side1Direction, side2Direction in itertools.product(
        sorted(side1Directions), sorted(side2Directions)
    ):
        localSide1: str | tuple[str, ...]
        localSide2: str | tuple[str, ...]
        if pair.firstIsClass:
            localSide1 = tuple(sorted(side1Directions[side1Direction]))
        else:
            assert len(side1Directions[side1Direction]) == 1
            (localSide1,) = side1Directions[side1Direction]
        if pair.secondIsClass:
            localSide2 = tuple(sorted(side2Directions[side2Direction]))
        else:
            assert len(side2Directions[side2Direction]) == 1
            (localSide2,) = side2Directions[side2Direction]

        # Skip pairs with clashing directions (e.g. "a" to "alef-ar").
        if side1Direction != side2Direction and not any(
            side is Direction.Neutral for side in (side1Direction, side2Direction)
        ):
            LOGGER.info(
                "Skipping part of a kerning pair <%s %s %s> with mixed direction (%s, %s)",
                localSide1,
                localSide2,
                pair.value,
                side1Direction.name,
                side2Direction.name,
            )
            continue

        # Skip pairs with clashing BiDi classes (e.g. "alef-ar" to "one-ar").
        localSide1Bidis = {
            bidi
            for glyph in side1Directions[side1Direction]
            for bidi in glyph_bidi[glyph]
        }
        localSide2Bidis = {
            bidi
            for glyph in side2Directions[side2Direction]
            for bidi in glyph_bidi[glyph]
        }
        if localSide1Bidis != localSide2Bidis and not any(
            Direction.Neutral in side for side in (localSide1Bidis, localSide2Bidis)
        ):
            LOGGER.info(
                "Skipping part of a kerning pair <%s %s %s> with conflicting BiDi classes",
                localSide1,
                localSide2,
                pair.value,
            )
            continue

        dominant_direction = (
            side1Direction if side2Direction is Direction.Neutral else side2Direction
        )
        yield (dominant_direction, KerningPair(localSide1, localSide2, pair.value))


def make_kerning_lookups(
    context: KernContext, options: SimpleNamespace
) -> dict[Direction, dict[str, fea_ast.LookupBlock]]:
    lookups: dict[Direction, dict[str, fea_ast.LookupBlock]] = {}
    if context.kerning.base_pairs_by_direction:
        make_split_kerning_lookups(
            context, options, lookups, context.kerning.base_pairs_by_direction
        )
    if context.kerning.mark_pairs_by_direction:
        make_split_kerning_lookups(
            context,
            options,
            lookups,
            context.kerning.mark_pairs_by_direction,
            ignoreMarks=False,
            suffix="_marks",
        )
    return lookups


def make_split_kerning_lookups(
    context: KernContext,
    options: SimpleNamespace,
    lookups: dict[Direction, dict[str, fea_ast.LookupBlock]],
    kerning_per_direction: dict[Direction, list[KerningPair]],
    ignoreMarks: bool = True,
    suffix: str = "",
) -> None:
    bidiGlyphs = context.bidiGlyphs
    side1Classes = context.kerning.side1Classes
    side2Classes = context.kerning.side2Classes

    newClassDefs, newSide1Classes, newSide2Classes = make_all_glyph_class_definitions(
        kerning_per_direction, context, context.feaFile
    )
    # NOTE: Consider duplicate names a bug, even if the classes would carry
    # the same glyphs.
    assert not context.kerning.classDefs.keys() & newClassDefs.keys()
    context.kerning.classDefs.update(newClassDefs)
    assert not side1Classes.keys() & newSide1Classes.keys()
    side1Classes.update(newSide1Classes)
    assert not side2Classes.keys() & newSide2Classes.keys()
    side2Classes.update(newSide2Classes)

    for direction, pairs in kerning_per_direction.items():
        lookupName = f"kern_{direction.value}{suffix}"
        lookup = make_kerning_lookup(
            context, options, lookupName, ignoreMarks=ignoreMarks
        )
        for pair in pairs:
            bidiTypes = {
                direction
                for direction, glyphs in bidiGlyphs.items()
                if not set(pair.glyphs).isdisjoint(glyphs)
            }
            if bidiTypes.issuperset(AMBIGUOUS_BIDIS):
                assert None, "this should have been caught by the splitter"
            # European and Arabic Numbers are always shaped LTR even in RTL scripts:
            pairIsRtl = (
                direction == Direction.RightToLeft
                and Direction.LeftToRight not in bidiTypes
            )
            rule = make_pairpos_rule(pair, side1Classes, side2Classes, pairIsRtl)
            lookup.statements.append(rule)
        lookups.setdefault(direction, {})[lookupName] = lookup


def make_all_glyph_class_definitions(
    kerning_per_direction: dict[Direction, list[KerningPair]],
    context: KernContext,
    feaFile: fea_ast.FeatureFile | None = None,
):
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
    for direction in (
        Direction.Neutral,
        Direction.LeftToRight,
        Direction.RightToLeft,
    ):
        for pair in kerning_per_direction.get(direction, []):
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
                    direction.value,
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
                    direction.value,
                )

    return newClassDefs, newSide1Classes, newSide2Classes


def make_kerning_lookup(
    context: KernContext, options: SimpleNamespace, name: str, ignoreMarks: bool = True
) -> fea_ast.LookupBlock:
    lookup = fea_ast.LookupBlock(name)
    if ignoreMarks and options.ignoreMarks:
        # We only want to filter the spacing marks
        marks = set(context.gdefClasses.mark or []) & set(context.glyphSet.keys())

        spacing = []
        if marks:
            spacing = filter_spacing_marks(context, marks)
        if not spacing:
            # Simple case, there are no spacing ("Spacing Combining") marks,
            # do what we've always done.
            lookup.statements.append(ast.makeLookupFlag("IgnoreMarks"))
        else:
            # We want spacing marks to block kerns.
            className = f"MFS_{name}"
            filteringClass = ast.makeGlyphClassDefinitions(
                {className: spacing}, feaFile=context.feaFile
            )[className]
            lookup.statements.append(filteringClass)
            lookup.statements.append(
                ast.makeLookupFlag(markFilteringSet=filteringClass)
            )
    return lookup


def filter_spacing_marks(context: KernContext, marks: set[str]) -> list[str]:
    if context.isVariable:
        spacing = []
        for mark in marks:
            if all(
                source.font[mark].width != 0
                for source in context.font.sources
                if mark in source.font
            ):
                spacing.append(mark)
        return spacing

    return [mark for mark in marks if context.font[mark].width != 0]


def make_pairpos_rule(
    pair: KerningPair, side1Classes, side2Classes, rtl: bool = False
) -> fea_ast.PairPosStatement:
    enumerated = pair.firstIsClass ^ pair.secondIsClass
    valuerecord = fea_ast.ValueRecord(
        xPlacement=pair.value if rtl else None,
        yPlacement=0 if rtl else None,
        xAdvance=pair.value,
        yAdvance=0 if rtl else None,
    )

    if pair.firstIsClass:
        glyphs1 = fea_ast.GlyphClassName(side1Classes[pair.side1])
    else:
        glyphs1 = fea_ast.GlyphName(pair.side1)
    if pair.secondIsClass:
        glyphs2 = fea_ast.GlyphClassName(side2Classes[pair.side2])
    else:
        glyphs2 = fea_ast.GlyphName(pair.side2)

    return fea_ast.PairPosStatement(
        glyphs1=glyphs1,
        valuerecord1=valuerecord,
        glyphs2=glyphs2,
        valuerecord2=None,
        enumerated=enumerated,
    )


def make_feature_blocks(
    context: KernContext, lookups: dict[Direction, dict[str, Any]]
) -> Any:
    features = {}
    if "kern" in context.todo:
        kern = fea_ast.FeatureBlock("kern")
        register_lookups(context, kern, lookups)
        if kern.statements:
            features["kern"] = kern
    if "dist" in context.todo:
        dist = fea_ast.FeatureBlock("dist")
        register_lookups(context, dist, lookups)
        if dist.statements:
            features["dist"] = dist
    return features


def register_lookups(
    context: KernContext,
    feature: fea_ast.FeatureBlock,
    lookups: dict[Direction, dict[str, fea_ast.LookupBlock]],
) -> None:
    # Ensure we have kerning for pure common script runs (e.g. ">1")
    isKernBlock = feature.name == "kern"
    lookupsNeutral: list[fea_ast.LookupBlock] = []
    if isKernBlock and Direction.Neutral in lookups:
        lookupsNeutral.extend(
            lkp
            for lkp in lookups[Direction.Neutral].values()
            if lkp not in lookupsNeutral
        )

    # InDesign bugfix: register kerning lookups for all LTR scripts under DFLT
    # so that the basic composer, without a language selected, will still kern.
    # Register LTR lookups if any, otherwise RTL lookups.
    if isKernBlock:
        lookupsLTR: list[fea_ast.LookupBlock] = (
            list(lookups[Direction.LeftToRight].values())
            if Direction.LeftToRight in lookups
            else []
        )
        lookupsRTL: list[fea_ast.LookupBlock] = (
            list(lookups[Direction.RightToLeft].values())
            if Direction.RightToLeft in lookups
            else []
        )
        lookupsNeutral.extend(
            lkp for lkp in (lookupsLTR or lookupsRTL) if lkp not in lookupsNeutral
        )

    if lookupsNeutral:
        languages = context.feaLanguagesByTag.get("DFLT", ["dflt"])
        ast.addLookupReferences(feature, lookupsNeutral, "DFLT", languages)

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
        scriptsToReference: set[str] = context.knownScripts - DIST_ENABLED_SCRIPTS
    else:
        scriptsToReference = DIST_ENABLED_SCRIPTS.intersection(context.knownScripts)
    scriptsToReference -= DFLT_SCRIPTS
    for script in sorted(scriptsToReference):
        script_direction = script_horizontal_direction(script, "LTR")
        for tag in unicodedata.ot_tags_from_script(script):
            lookupsForThisScript = {}
            if Direction.Neutral in lookups:
                lookupsForThisScript.update(lookups[Direction.Neutral])
            if script_direction == "LTR" and Direction.LeftToRight in lookups:
                lookupsForThisScript.update(lookups[Direction.LeftToRight])
            if script_direction == "RTL" and Direction.RightToLeft in lookups:
                lookupsForThisScript.update(lookups[Direction.RightToLeft])
            if not lookupsForThisScript:
                continue
            if feature.statements:
                feature.statements.append(fea_ast.Comment(""))
            # Register the lookups for all languages defined in the feature
            # file for the script, otherwise kerning is not applied if any
            # language is set at all.
            languages = context.feaLanguagesByTag.get(tag, ["dflt"])
            ast.addLookupReferences(
                feature, lookupsForThisScript.values(), tag, languages
            )
