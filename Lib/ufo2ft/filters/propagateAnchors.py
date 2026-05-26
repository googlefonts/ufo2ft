# Copyright 2016 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Anchor propagation algorithm ported from:
#   glyphsLib (Apache-2.0): glyphsLib/builder/transformations/propagate_anchors.py

import logging
from collections import deque
from dataclasses import dataclass
from math import atan2, degrees, isinf

from fontTools.misc.transform import Transform

from ufo2ft.constants import (
    _PRELIMINARY_CATEGORIES_KEY,
    GLYPHS_COMPONENT_INFO_KEY,
    OPENTYPE_CATEGORIES_KEY,
)
from ufo2ft.filters import BaseFilter, BaseIFilter
from ufo2ft.util import OpenTypeCategories, _GlyphSet, zip_strict

logger = logging.getLogger(__name__)


@dataclass
class AnchorData:
    name: str
    x: float
    y: float


def _depth_sorted_glyphs(glyph_set):
    """Return glyph names in dependency order (simple glyphs first, then
    composites ordered by increasing component depth).

    Handles missing components and cycles gracefully with warnings.
    """
    queue = deque()
    depths = {}
    waiting_for = {}

    for name in glyph_set:
        glyph = glyph_set[name]
        if not glyph.components:
            depths[name] = 0
        else:
            queue.append(name)

    while queue:
        name = queue.popleft()
        glyph = glyph_set[name]
        comp_names = {c.baseGlyph for c in glyph.components if c.baseGlyph in glyph_set}
        if all(c in depths for c in comp_names):
            depths[name] = max((depths[c] for c in comp_names), default=-1) + 1
            waiting_for.pop(name, None)
        else:
            last_queue_len = waiting_for.get(name)
            waiting_for[name] = len(queue)
            if last_queue_len != len(queue):
                queue.append(name)
            else:
                depths[name] = float("inf")
                waiting_for.pop(name, None)
                logger.warning("glyph '%s' has cyclical components", name)

    for name in glyph_set:
        if name not in depths:
            depths[name] = 0

    return [
        name for _, name in sorted((d, n) for n, d in depths.items() if not isinf(d))
    ]


def get_xy_rotation(transform):
    """Extract scale factors (with sign for flip) from a Transform."""
    a, b = transform[:2]
    angle = atan2(b, a)
    rotated = transform.rotate(-angle)
    xscale, yscale = rotated[0], rotated[3]
    if abs(degrees(angle) - 180) < 0.001:
        xscale = -xscale
        yscale = -yscale
    return xscale, yscale


def rename_anchor_for_scale(name, xscale, yscale):
    """Swap left<->right if xscale<0, bottom<->top if yscale<0,
    exit<->entry if xscale<0."""

    def swap_pair(s, one, two):
        if one in s:
            return s.replace(one, two)
        elif two in s:
            return s.replace(two, one)
        return s

    if xscale < 0.0:
        name = swap_pair(name, "left", "right")
        name = swap_pair(name, "exit", "entry")
    if yscale < 0.0:
        name = swap_pair(name, "bottom", "top")
    return name


def make_liga_anchor_name(name, base_number):
    """Convert 'top' -> 'top_N' for ligature numbering."""
    if "_" in name:
        name, suffix = name.split("_", 1)
        try:
            num = int(suffix)
        except ValueError:
            num = 1
        return f"{name}_{base_number + num}"
    return f"{name}_{base_number + 1}"


def maybe_rename_component_anchor(comp_name, anchors):
    """Handle component attachment anchors like 'top_2'."""
    if "_" not in comp_name:
        return
    sub_name = comp_name[: comp_name.index("_")]
    mark_name = f"_{sub_name}"
    if any(a.name == sub_name for a in anchors) and any(
        a.name == mark_name for a in anchors
    ):
        for a in anchors:
            if a.name == sub_name:
                a.name = comp_name
                break


def origin_adjusted_anchors(anchors):
    """Apply *origin anchor offset and exclude *origin from output."""
    origin_x, origin_y = 0.0, 0.0
    for a in anchors:
        if a.name == "*origin":
            origin_x, origin_y = a.x, a.y
            break
    return [
        AnchorData(name=a.name, x=a.x - origin_x, y=a.y - origin_y)
        for a in anchors
        if a.name != "*origin"
    ]


def _anchors_from_glyph(glyph):
    """Read anchors from a glyph object into AnchorData list."""
    return [AnchorData(name=a.name, x=a.x, y=a.y) for a in glyph.anchors]


def _classify_glyphs(glyph_set, categories):
    """Return (marks, ligatures) sets of glyph names.

    Uses public.openTypeCategories when available, falls back to heuristics.
    """
    marks = set(categories.mark)
    ligatures = set(categories.ligature)

    if categories.is_empty:
        logger.warning(
            "public.openTypeCategories not found or empty; anchor propagation "
            "may differ from fontc/Glyphs.app for mark and ligature glyphs."
        )
        for name in glyph_set:
            glyph = glyph_set[name]
            if any(a.name.startswith("_") for a in glyph.anchors):
                marks.add(name)

    return marks, ligatures


def _finalize_categories(preliminary_categories, done_anchors):
    """Refine preliminary categories after anchor propagation.

    Matches fontc's recompute_gdef_categories: marks are kept as-is,
    ligatures are kept only if they gained attaching anchors, and bases
    are inferred from attaching anchors for all remaining glyphs.
    """
    finalized = {}
    for name, anchors in done_anchors.items():
        has_attaching = any(a.name and not a.name.startswith("_") for a in anchors)
        preliminary = preliminary_categories.get(name)
        if preliminary == "mark":
            finalized[name] = "mark"
        elif preliminary == "ligature" and has_attaching:
            finalized[name] = "ligature"
        elif has_attaching and preliminary != "mark":
            finalized[name] = "base"
    return finalized


def _get_component_anchors(glyph):
    """Read Glyphs component attachment anchors from a glyph's lib.

    Returns a dict mapping component index to the explicit anchor attachment
    name (e.g. {1: "top_1", 2: "top_2"}).
    """
    info = getattr(glyph, "lib", {}).get(GLYPHS_COMPONENT_INFO_KEY, [])
    return {
        entry["index"]: entry["anchor"]
        for entry in info
        if "index" in entry and "anchor" in entry
    }


def anchors_traversing_components(
    glyph_name,
    existing_anchors,
    components,
    is_mark,
    is_ligature,
    done_anchors,
    base_glyph_counts,
    component_anchor_map=None,
):
    """Compute anchors for a glyph, propagating from its components.

    This is a port of the glyphsLib/fontc algorithm adapted for defcon objects.
    """
    if not existing_anchors and not components:
        return []

    if existing_anchors and is_mark:
        return list(origin_adjusted_anchors(existing_anchors))

    has_underscore = any(a.name.startswith("_") for a in existing_anchors)
    number_of_base_glyphs = 0
    all_anchors = {}

    for component_idx, component in enumerate(components):
        comp_name = component.baseGlyph
        if comp_name not in done_anchors:
            logger.warning(
                "Anchors not propagated for inexistent component %s " "in glyph %s",
                comp_name,
                glyph_name,
            )
            continue

        anchors = [
            AnchorData(name=a.name, x=a.x, y=a.y) for a in done_anchors[comp_name]
        ]

        if component_anchor_map and component_idx in component_anchor_map:
            maybe_rename_component_anchor(component_anchor_map[component_idx], anchors)

        component_number_of_base_glyphs = base_glyph_counts.get(comp_name, 0)

        comb_has_underscore = any(
            len(a.name) >= 2 and a.name.startswith("_") for a in anchors
        )
        comb_has_exit = any(a.name.startswith("exit") for a in anchors)
        if not (comb_has_underscore or comb_has_exit):
            all_anchors = {
                n: a for n, a in all_anchors.items() if not n.startswith("exit")
            }

        component_transform = Transform(*component.transformation)
        xscale, yscale = get_xy_rotation(component_transform)

        for anchor in anchors:
            new_has_underscore = anchor.name.startswith("_")
            if (component_idx > 0 or has_underscore) and new_has_underscore:
                continue
            if component_idx > 0 and anchor.name.startswith("entry"):
                continue

            new_anchor_name = rename_anchor_for_scale(anchor.name, xscale, yscale)
            if (
                is_ligature
                and component_number_of_base_glyphs > 0
                and not new_has_underscore
                and not (
                    new_anchor_name.startswith("exit")
                    or new_anchor_name.startswith("entry")
                )
            ):
                new_anchor_name = make_liga_anchor_name(
                    new_anchor_name, number_of_base_glyphs
                )

            pos = component_transform.transformPoint((anchor.x, anchor.y))
            anchor.x = round(pos[0], 6)
            anchor.y = round(pos[1], 6)
            anchor.name = new_anchor_name
            all_anchors[anchor.name] = anchor
            has_underscore |= new_has_underscore

        number_of_base_glyphs += base_glyph_counts.get(comp_name, 0)

    # Apply explicitly defined anchors on this glyph (overrides component ones)
    all_anchors.update((a.name, a) for a in origin_adjusted_anchors(existing_anchors))

    # Count base glyphs from anchors
    has_underscore_anchor = False
    has_mark_anchor = False
    component_count_from_anchors = 0
    for name in all_anchors:
        has_underscore_anchor |= name.startswith("_")
        has_mark_anchor |= bool(name) and name[0].isalpha() and name[0].isascii()
        if (
            not is_ligature
            and number_of_base_glyphs == 0
            and not name.startswith("_")
            and not (name.startswith("exit") or name.startswith("entry"))
            and "_" in name
        ):
            suffix = name[name.index("_") + 1 :]
            maybe_add_one = 1 if name.startswith("caret") else 0
            anchor_index = 0
            try:
                anchor_index = int(suffix) + maybe_add_one
            except ValueError:
                pass
            component_count_from_anchors = max(
                component_count_from_anchors, anchor_index
            )
    if not has_underscore_anchor and number_of_base_glyphs == 0 and has_mark_anchor:
        number_of_base_glyphs += 1
    number_of_base_glyphs = max(number_of_base_glyphs, component_count_from_anchors)

    # Bottom/top cancellation (matches glyphsLib propagate_anchors.py:592-597)
    if any(a.name == "_bottom" for a in existing_anchors):
        all_anchors.pop("top", None)
        all_anchors.pop("_top", None)
    if any(a.name == "_top" for a in existing_anchors):
        all_anchors.pop("bottom", None)
        all_anchors.pop("_bottom", None)

    base_glyph_counts[glyph_name] = number_of_base_glyphs

    return sorted(all_anchors.values(), key=lambda a: a.name)


def _compute_component_closure(glyph_set, root_names):
    """Given a set of included root glyph names, return the full closure
    including all transitive component dependencies."""
    closure = set()
    stack = list(root_names)
    while stack:
        name = stack.pop()
        if name in closure or name not in glyph_set:
            continue
        closure.add(name)
        glyph = glyph_set[name]
        for comp in glyph.components:
            if comp.baseGlyph not in closure and comp.baseGlyph in glyph_set:
                stack.append(comp.baseGlyph)
    return closure


def _combined_glyph_set(glyph_sets):
    """Return a representative glyph set with unioned component dependencies."""
    all_glyph_names = set()
    for glyph_set in glyph_sets:
        all_glyph_names.update(glyph_set.keys())

    combined = {}
    for name in all_glyph_names:
        components = []
        representative = None
        for glyph_set in glyph_sets:
            if name not in glyph_set:
                continue
            glyph = glyph_set[name]
            if representative is None:
                representative = glyph
            components.extend(glyph.components)
        if representative is not None:
            combined[name] = _CombinedGlyph(representative, components)
    return combined


class _CombinedGlyph:
    def __init__(self, glyph, components):
        self._glyph = glyph
        self.components = components

    def __getattr__(self, name):
        return getattr(self._glyph, name)


def _write_anchors_to_glyph(glyph, new_anchors):
    """Write AnchorData list to a glyph, replacing existing anchors.

    Preserves existing anchor identifiers where names match.
    Returns True if the glyph was actually modified.
    """
    old = [(a.name, round(a.x, 6), round(a.y, 6)) for a in glyph.anchors]
    new = [(a.name, round(a.x, 6), round(a.y, 6)) for a in new_anchors]
    if old == new:
        return False

    old_by_name = {}
    for a in glyph.anchors:
        old_by_name.setdefault(a.name, a)

    glyph.clearAnchors()
    for ad in new_anchors:
        anchor_dict = {"name": ad.name, "x": ad.x, "y": ad.y}
        existing = old_by_name.get(ad.name)
        if existing is not None and hasattr(existing, "identifier"):
            ident = getattr(existing, "identifier", None)
            if ident:
                anchor_dict["identifier"] = ident
        try:
            glyph.appendAnchor(anchor_dict)
        except TypeError:
            glyph.appendAnchor(ad.name, (ad.x, ad.y))
    return True


class PropagateAnchorsFilter(BaseFilter):
    # must run before decomposition, while components are still present
    _pre = True

    def __call__(self, font, glyphSet=None):
        fontName = font.__class__.__name__
        logger.info("Running %s on %s", self.name, fontName)

        if glyphSet is None:
            glyphSet = _GlyphSet.from_layer(font)

        categories = OpenTypeCategories.load(font)
        preliminary = None
        if categories.is_empty:
            preliminary = font.lib.get(_PRELIMINARY_CATEGORIES_KEY)
            if preliminary:
                categories = OpenTypeCategories.from_dict(preliminary)
        marks, ligatures = _classify_glyphs(glyphSet, categories)

        sorted_glyphs = _depth_sorted_glyphs(glyphSet)

        done_anchors = {}
        base_glyph_counts = {}

        for name in sorted_glyphs:
            glyph = glyphSet[name]
            existing = _anchors_from_glyph(glyph)
            is_mark = name in marks
            is_ligature = name in ligatures

            result = anchors_traversing_components(
                name,
                existing,
                glyph.components,
                is_mark,
                is_ligature,
                done_anchors,
                base_glyph_counts,
                component_anchor_map=_get_component_anchors(glyph),
            )
            done_anchors[name] = result

        if preliminary:
            finalized = _finalize_categories(preliminary, done_anchors)
            font.lib[OPENTYPE_CATEGORIES_KEY] = finalized
            font.lib.pop(_PRELIMINARY_CATEGORIES_KEY, None)
            logger.info(
                "Finalized preliminary categories: %d base, %d ligature, %d mark",
                sum(1 for v in finalized.values() if v == "base"),
                sum(1 for v in finalized.values() if v == "ligature"),
                sum(1 for v in finalized.values() if v == "mark"),
            )

        # Determine which glyphs to write: included roots + component closure
        include = self.include
        included_roots = {name for name in glyphSet if include(glyphSet[name])}
        write_set = _compute_component_closure(glyphSet, included_roots)

        modified = set()
        for name in sorted_glyphs:
            if name not in write_set:
                continue
            glyph = glyphSet[name]
            if not glyph.components:
                continue
            new_anchors = done_anchors[name]
            if _write_anchors_to_glyph(glyph, new_anchors):
                modified.add(name)

        if modified:
            logger.info("Glyphs with propagated anchors: %i" % len(modified))
        return modified


class PropagateAnchorsIFilter(BaseIFilter):
    _pre = True

    def __call__(self, fonts, glyphSets=None, instantiator=None, **kwargs):
        logger.info("Running interpolatable %s", self.name)

        if glyphSets is None:
            glyphSets = [_GlyphSet.from_layer(font) for font in fonts]

        self.set_context(fonts, glyphSets, instantiator, **kwargs)
        ds_categories = kwargs.get("openTypeCategories")
        preliminary = kwargs.get("preliminaryOpenTypeCategories")
        if ds_categories:
            categories = OpenTypeCategories.from_dict(ds_categories)
        else:
            categories = OpenTypeCategories.load(self.getDefaultFont())
        used_preliminary = categories.is_empty and preliminary
        if used_preliminary:
            categories = OpenTypeCategories.from_dict(preliminary)
        interpolated_layers = self.getInterpolatedLayers()

        # Classify using default font's glyphSet
        default_gs = self.getDefaultGlyphSet()
        marks, ligatures = _classify_glyphs(default_gs, categories)

        # Get union of all glyph names across masters
        all_glyph_names = set()
        for gs in glyphSets:
            all_glyph_names.update(gs.keys())

        combined = _combined_glyph_set(glyphSets)
        sorted_glyphs = _depth_sorted_glyphs(combined)

        # Per-master done_anchors and base_glyph_counts
        per_master_done = [{} for _ in glyphSets]
        per_master_counts = [{} for _ in glyphSets]

        for name in sorted_glyphs:
            is_mark = name in marks
            is_ligature = name in ligatures

            for i, (glyphSet, interpolatedLayer) in enumerate(
                zip_strict(glyphSets, interpolated_layers)
            ):
                if name not in glyphSet:
                    continue

                glyph = glyphSet[name]
                existing = _anchors_from_glyph(glyph)

                done = per_master_done[i]
                counts = per_master_counts[i]

                # Ensure component anchors are available: if a component is
                # missing from the real glyphSet, generate from interpolated
                # layer and propagate its anchors into done_anchors.
                for comp in glyph.components:
                    cn = comp.baseGlyph
                    if cn in done:
                        continue
                    if cn in glyphSet:
                        continue
                    if interpolatedLayer is not None and cn in interpolatedLayer:
                        ig = interpolatedLayer[cn]
                        ie = _anchors_from_glyph(ig)
                        ir = anchors_traversing_components(
                            cn,
                            ie,
                            ig.components,
                            cn in marks,
                            cn in ligatures,
                            done,
                            counts,
                            component_anchor_map=_get_component_anchors(ig),
                        )
                        done[cn] = ir

                result = anchors_traversing_components(
                    name,
                    existing,
                    glyph.components,
                    is_mark,
                    is_ligature,
                    done,
                    counts,
                    component_anchor_map=_get_component_anchors(glyph),
                )
                done[name] = result

        # Finalize preliminary categories after propagation: prune anchorless
        # ligatures and infer bases from attaching anchors.  Write the result
        # to every master UFO's lib so GdefFeatureWriter picks it up.
        if used_preliminary:
            if self.context.instantiator is not None:
                default_idx = self.context.instantiator.default_source_idx
            else:
                default_idx = 0
            default_done = per_master_done[default_idx]
            finalized = _finalize_categories(preliminary, default_done)
            for font in fonts:
                font.lib[OPENTYPE_CATEGORIES_KEY] = finalized
            logger.info(
                "Finalized preliminary categories: %d base, %d ligature, %d mark",
                sum(1 for v in finalized.values() if v == "base"),
                sum(1 for v in finalized.values() if v == "ligature"),
                sum(1 for v in finalized.values() if v == "mark"),
            )

        # Determine which glyphs to write
        include = self.include
        included_roots = set()
        for name in all_glyph_names:
            for gs in glyphSets:
                if name in gs and include(gs[name]):
                    included_roots.add(name)
                    break
        write_set = _compute_component_closure(combined, included_roots)

        modified = set()
        for name in sorted_glyphs:
            if name not in write_set:
                continue
            has_components = any(name in gs and gs[name].components for gs in glyphSets)
            if not has_components:
                continue

            for i, glyphSet in enumerate(glyphSets):
                if name not in glyphSet:
                    continue
                glyph = glyphSet[name]
                new_anchors = per_master_done[i].get(name, [])
                if _write_anchors_to_glyph(glyph, new_anchors):
                    modified.add(name)

        if modified:
            logger.info("Glyphs with propagated anchors: %i" % len(modified))
        return modified
