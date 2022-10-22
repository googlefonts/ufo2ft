from __future__ import annotations

from itertools import groupby
from typing import Mapping

from fontTools.misc.classifyTools import classify

from .ast import ast
from .kernFeatureWriter import KerningPair


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

    Group memebership must be exclusive per side per lookup (script bucket).
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
