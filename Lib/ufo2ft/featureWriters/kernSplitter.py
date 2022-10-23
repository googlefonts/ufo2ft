from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from itertools import groupby
from typing import Iterator, Literal, Mapping

from fontTools import unicodedata
from fontTools.misc.classifyTools import classify

from ufo2ft.util import DFLT_SCRIPTS, quantize
from .ast import addLookupReferences

from .ast import ast
from .kernFeatureWriter import (
    COMMON_SCRIPT,
    COMMON_SCRIPTS_SET,
    DIST_ENABLED_SCRIPTS,
    KerningPair,
)


def getAndSplitKerningData(
    kerning: Mapping[tuple[str, str], float],
    side1Classes: Mapping[str, ast.GlyphClassDefinition],
    side2Classes: Mapping[str, ast.GlyphClassDefinition],
    glyphSet: set[str],
    glyphScripts: dict[str, set[str]],
) -> dict[str, list[KerningPair]]:
    all_pairs: list[KerningPair] = []
    kerning_per_script: dict[str, list[KerningPair]] = {}
    for (side1, side2), value in kerning.items():
        firstIsClass, secondIsClass = (side1 in side1Classes, side2 in side2Classes)
        # Filter out pairs that reference missing groups or glyphs.
        if not firstIsClass and side1 not in glyphSet:
            continue
        if not secondIsClass and side2 not in glyphSet:
            continue
        # Ignore zero-valued class kern pairs.
        if firstIsClass and secondIsClass and value == 0:
            continue
        if firstIsClass:
            side1 = side1Classes[side1]
        if secondIsClass:
            side2 = side2Classes[side2]

        pair = KerningPair(side1, side2, value)
        all_pairs.append(pair)
        # Split pairs into per-script buckets.
        for script, split_pair in pair.partitionByScript(glyphScripts):
            kerning_per_script.setdefault(script, []).append(split_pair)

    # Sanity check before splitting. Remove for production.
    try:
        ensure_unique_group_membership(all_pairs)
    except Exception as e:
        raise Exception(f"Before splitting: {e}")
    # Sanity check after splitting. Remove for production.
    for script, pairs in kerning_per_script.items():
        try:
            ensure_unique_group_membership(pairs)
        except Exception as e:
            raise Exception(f"In {script}: {e}")

    # Ensure that kern1 classes in class-to-class pairs are disjoint after
    # splitting, to ensure that subtable coverage (kern1 coverage) within a
    # lookup is disjoint. Shapers only consider the first subtable to cover a
    # kern1 class and kerning will be lost in subsequent subtables. See
    # https://github.com/fonttools/fonttools/issues/2793.
    for script, pairs in kerning_per_script.items():
        new_pairs: list[KerningPair] = []

        pairs_to_split: list[KerningPair] = []
        kern1_classes: list[list[str]] = []
        for pair in pairs:
            # We only care about class-to-class pairs, leave rest as is.
            if not (pair.firstIsClass and pair.secondIsClass):
                new_pairs.append(pair)
                continue
            kern1_class = [name.glyph for name in pair.side1.glyphSet()]
            kern1_classes.append(kern1_class)
            pairs_to_split.append(pair)

        mapping: dict[str, set[str]]
        _, mapping = classify(kern1_classes)
        for pair in pairs_to_split:
            smaller_kern1s = [mapping[name.glyph] for name in pair.side1.glyphSet()]
            smaller_kern1s.sort()  # groupby expects sorted input.
            for smaller_kern1, _ in groupby(smaller_kern1s):
                assert not isinstance(pair.side2, ast.GlyphName)
                new_pairs.append(
                    KerningPair(
                        smaller_kern1,
                        pair.side2,
                        pair.value,
                        pair.scripts,
                        pair.directions,
                        pair.bidiTypes,
                    )
                )

        pairs[:] = new_pairs

    # Sanity check after disjointing. Remove for production.
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

    return kerning_per_script


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
                elif (membership := kern1_membership[name]) != kern1:
                    raise Exception(
                        f"Glyph {name} in multiple kern1 groups, originally in {membership} but now also in {kern1}"
                    )
        if pair.secondIsClass:
            kern2 = {name.glyph for name in pair.side2.glyphSet()}
            for name in kern2:
                if name not in kern2_membership:
                    kern2_membership[name] = kern2
                elif (membership := kern2_membership[name]) != kern2:
                    raise Exception(
                        f"Glyph {name} in multiple kern2 groups, originally in {membership} but now also in {kern2}"
                    )


@dataclass(frozen=True)
class Pair:
    __slots__ = "side1", "side2", "value"
    side1: str | set[str]
    side2: str | set[str]
    value: float

    def __post_init__(self):
        if isinstance(self.side1, set):
            assert len(self.side1)
        if isinstance(self.side2, set):
            assert len(self.side2)

    def __lt__(self, other: Pair) -> bool:
        if not isinstance(other, Pair):
            return NotImplemented

        self_first_kern1_glyph = (
            self.side1 if not self.first_is_class else sorted(self.side1)[0]
        )
        self_first_kern2_glyph = (
            self.side2 if not self.second_is_class else sorted(self.side2)[0]
        )
        self_tuple = (
            isinstance(self.side1, set),
            isinstance(self.side2, set),
            self_first_kern1_glyph,
            self_first_kern2_glyph,
            self.value,
        )
        other_first_kern1_glyph = (
            other.side1 if not other.first_is_class else sorted(other.side1)[0]
        )
        other_first_kern2_glyph = (
            other.side2 if not other.second_is_class else sorted(other.side2)[0]
        )
        other_tuple = (
            isinstance(other.side1, set),
            isinstance(other.side2, set),
            other_first_kern1_glyph,
            other_first_kern2_glyph,
            other.value,
        )
        return self_tuple < other_tuple

    @property
    def first_is_class(self) -> bool:
        return isinstance(self.side1, set)

    @property
    def second_is_class(self) -> bool:
        return isinstance(self.side2, set)

    @property
    def glyphs(self) -> Iterator[str]:
        # Use isinstance instead of our properties because type checkers.
        if isinstance(self.side1, set):
            yield from self.side1
        else:
            yield self.side1
        if isinstance(self.side2, set):
            yield from self.side2
        else:
            yield self.side2


# TODO: take marks set and filter into base and marks pairs
def get_and_split_kerning_data(
    kerning: Mapping[tuple[str, str], float],
    groups: Mapping[str, list[str]],
    glyph_set: set[str],
    glyph_scripts: Mapping[str, set[str]],
) -> dict[str, list[Pair]]:
    group_scripts, groups_by_script = split_kerning_groups(groups, glyph_scripts)

    kerning_per_script: dict[str, list[Pair]] = {}
    for (first, second), value in kerning.items():
        first_is_class, second_is_class = (first in groups, second in groups)
        # Filter out pairs that reference missing groups or glyphs.
        if not first_is_class and first not in glyph_set:
            continue
        if not second_is_class and second not in glyph_set:
            continue
        # Ignore zero-valued class kern pairs.
        if first_is_class and second_is_class and value == 0:
            continue

        # Split pairs into per-script buckets.
        for script, split_pair in split_kerning_pair(
            first, second, value, glyph_scripts, group_scripts, groups_by_script
        ):
            kerning_per_script.setdefault(script, []).append(split_pair)

    # Sanity check after splitting. Remove for production.
    for script, pairs in kerning_per_script.items():
        try:
            ensure_unique_group_membership2(pairs)
        except Exception as e:
            raise Exception(f"In {script}: {e}")

    # Sort Kerning pairs so that glyph to glyph comes first, then glyph to
    # class, class to glyph, and finally class to class. This makes "kerning
    # exceptions" work, where more specific glyph pair values override less
    # specific class kerning.
    for script, pairs in kerning_per_script.items():
        pairs.sort()

    return kerning_per_script


# TODO: generate new @class definitions from the split groups in use
def split_kerning_groups(
    groups: Mapping[str, list[str]], glyph_scripts: Mapping[str, set[str]]
) -> tuple[dict[str, set[str]], dict[str, dict[str, set[str]]]]:
    # TODO: don't generate everything up front, instead write a getter that generates
    # (and caches) by-script groups on demand

    group_scripts: dict[str, set[str]] = {}
    by_script: dict[str, dict[str, set[str]]] = {}
    for name, members in groups.items():
        if not name.startswith(("public.kern1.", "public.kern2.")):
            continue
        for member in members:
            for script in glyph_scripts.get(member, COMMON_SCRIPTS_SET):
                by_script.setdefault(script, {}).setdefault(name, set()).add(member)
                group_scripts.setdefault(name, set()).add(script)

    return group_scripts, by_script


def split_kerning_pair(
    first: str,
    second: str,
    value: float,
    glyph_scripts: Mapping[str, set[str]],
    group_scripts: Mapping[str, set[str]],
    groups_by_script: Mapping[str, Mapping[str, set[str]]],
) -> Iterator[tuple[str, Pair]]:
    first_is_class, second_is_class = first in group_scripts, second in group_scripts

    if first_is_class:
        first_scripts = group_scripts[first]
    else:
        first_scripts = glyph_scripts.get(first, COMMON_SCRIPTS_SET)
    if second_is_class:
        second_scripts = group_scripts[second]
    else:
        second_scripts = glyph_scripts.get(second, COMMON_SCRIPTS_SET)

    for first_script, second_script in itertools.product(first_scripts, second_scripts):
        split_first: str | set[str] = first
        if first_is_class:
            split_first = groups_by_script[first_script][first]
        split_second: str | set[str] = second
        if second_is_class:
            split_second = groups_by_script[second_script][second]
        split_pair = Pair(split_first, split_second, value)

        if first_script == second_script:
            yield first_script, split_pair
        elif second_script in DFLT_SCRIPTS:
            yield first_script, split_pair
        elif first_script in DFLT_SCRIPTS:
            yield second_script, split_pair
        else:
            logging.getLogger(__file__).info(
                "Mixed script kerning pair %s ignored" % split_pair
            )


def ensure_unique_group_membership2(pairs: list[Pair]) -> None:
    """Raises an exception when a glyph is found to belong to multiple groups per
    side.

    Group membership must be exclusive per side per lookup (script bucket).
    """

    kern1_membership: dict[str, set[str]] = {}
    kern2_membership: dict[str, set[str]] = {}

    for pair in pairs:
        kern1 = pair.side1
        if isinstance(kern1, set):
            for name in kern1:
                if name not in kern1_membership:
                    kern1_membership[name] = kern1
                elif (membership := kern1_membership[name]) != kern1:
                    raise Exception(
                        f"Glyph {name} in multiple kern1 groups, originally "
                        f"in {membership} but now also in {kern1}"
                    )
        kern2 = pair.side2
        if isinstance(kern2, set):
            for name in kern2:
                if name not in kern2_membership:
                    kern2_membership[name] = kern2
                elif (membership := kern2_membership[name]) != kern2:
                    raise Exception(
                        f"Glyph {name} in multiple kern2 groups, originally "
                        f"in {membership} but now also in {kern2}"
                    )


def make_lookups(
    all_pairs: Mapping[str, list[Pair]],
    bidi_types: Mapping[str, set[str]],
    quantization: int = 1,
) -> dict[str, dict[str, ast.LookupBlock]]:
    lookups: dict[str, dict[str, ast.LookupBlock]] = {}
    for script, pairs in all_pairs.items():
        lookup = ast.LookupBlock(f"kern_{script}")
        # if ignoreMarks and self.options.ignoreMarks:
        #     lookup.statements.append(makeLookupFlag("IgnoreMarks"))
        script_is_rtl = unicodedata.script_horizontal_direction(script) == "RTL"
        for pair in pairs:
            # Numbers are always shaped LTR even in RTL scripts:
            if script_is_rtl:
                pair_is_rtl = not any(
                    bidi_types.get(name) == "L" for name in pair.glyphs
                )
            else:
                pair_is_rtl = False
            rule = make_pair_pos_rule(pair, script_is_rtl and pair_is_rtl, quantization)
            lookup.statements.append(rule)
        lookups[script] = lookup
    return lookups


def make_pair_pos_rule(
    pair: Pair, rtl: bool = False, quantization: int = 1
) -> ast.PairPosStatement:
    enumerated = pair.first_is_class ^ pair.second_is_class
    value = quantize(pair.value, quantization)
    valuerecord = ast.ValueRecord(
        xPlacement=value if rtl else None,
        yPlacement=0 if rtl else None,
        xAdvance=value,
        yAdvance=0 if rtl else None,
    )
    if pair.first_is_class:
        glyphs1 = ast.GlyphClass(ast.GlyphName(name) for name in sorted(pair.side1))
    else:
        glyphs1 = ast.GlyphName(pair.side1)
    if pair.second_is_class:
        glyphs2 = ast.GlyphClass(ast.GlyphName(name) for name in sorted(pair.side2))
    else:
        glyphs2 = ast.GlyphName(pair.side2)
    return ast.PairPosStatement(
        glyphs1=glyphs1,
        valuerecord1=valuerecord,
        glyphs2=glyphs2,
        valuerecord2=None,
        enumerated=enumerated,
    )


def make_feature_blocks(
    features: ast.FeatureFile,
    lookups: dict[str, ast.LookupBlock],
    make_kern: bool = True,
    make_dist: bool = True,
) -> dict[str, ast.FeatureBlock]:
    feature_blocks: dict[str, ast.FeatureBlock] = {}
    if make_kern:
        kern = make_feature_block(features, "kern", lookups)
        if kern.statements:
            feature_blocks["kern"] = kern
    if make_dist:
        dist = make_feature_block(features, "dist", lookups)
        if dist.statements:
            feature_blocks["dist"] = dist
    return feature_blocks


def make_feature_block(
    block: ast.FeatureBlock,
    name: Literal["kern"] | Literal["dist"],
    lookups: dict[str, ast.LookupBlock],
) -> ast.FeatureBlock:
    block = ast.FeatureBlock(name)

    # Ensure we have kerning for pure common script runs (e.g. ">1")
    if name == "kern" and COMMON_SCRIPT in lookups:
        addLookupReferences(block, [lookups[COMMON_SCRIPT]], "DFLT", ["dflt"])

    if name == "kern":
        scripts_to_reference = lookups.keys() - DIST_ENABLED_SCRIPTS - DFLT_SCRIPTS
    else:
        scripts_to_reference = (
            DIST_ENABLED_SCRIPTS.intersection(lookups.keys()) - DFLT_SCRIPTS
        )
    for script in scripts_to_reference:
        lookups_for_this_script: list[ast.LookupBlock] = []
        ot_tags = unicodedata.ot_tags_from_script(script)
        if block.statements:
            block.statements.append(ast.Comment(""))
        # We have something for this script. First add the default
        # lookups, then the script-specific ones
        for dflt_script in DFLT_SCRIPTS:
            if dflt_script in lookups:
                lookups_for_this_script.append(lookups[dflt_script])
        lookups_for_this_script.append(lookups[script])
        for ot_tag in ot_tags:
            addLookupReferences(block, lookups_for_this_script, ot_tag, ["dflt"])

    return block
