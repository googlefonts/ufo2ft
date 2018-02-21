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

from fontTools.misc.transform import Transform
from ufo2ft.filters import BaseFilter

import logging


logger = logging.getLogger(__name__)


class PropagateAnchorsFilter(BaseFilter):

    def set_context(self, font, glyphSet):
        ctx = super(PropagateAnchorsFilter, self).set_context(font, glyphSet)
        ctx.processed = set()
        return ctx

    def __call__(self, font, glyphSet=None):
        if super(PropagateAnchorsFilter, self).__call__(font, glyphSet):
            modified = self.context.modified
            if modified:
                logger.info('Glyphs with propagated anchors: %i' %
                            len(modified))
            return modified

    def filter(self, glyph):
        if not glyph.components:
            return False
        _propagate_glyph_anchors(self.context.font, glyph, self.context.processed)
        return True


def _propagate_glyph_anchors(ufo, parent, processed):
    """Propagate anchors for a single parent glyph."""

    if parent.name in processed:
        return
    processed.add(parent.name)

    base_components = []
    mark_components = []
    anchor_names = set()
    to_add = {}
    for component in parent.components:
        glyph = ufo[component.baseGlyph]
        _propagate_glyph_anchors(ufo, glyph, processed)
        if any(a.name.startswith('_') for a in glyph.anchors):
            mark_components.append(component)
        else:
            base_components.append(component)
            anchor_names |= {a.name for a in glyph.anchors}

    for anchor_name in anchor_names:
        # don't add if parent already contains this anchor OR any associated
        # ligature anchors (e.g. "top_1, top_2" for "top")
        if not any(a.name.startswith(anchor_name) for a in parent.anchors):
            _get_anchor_data(to_add, ufo, base_components, anchor_name)

    for component in mark_components:
        _adjust_anchors(to_add, ufo, component)

    # we sort propagated anchors to append in a deterministic order
    for name, (x, y) in sorted(to_add.items()):
        anchor_dict = {'name': name, 'x': x, 'y': y}
        parent.appendAnchor(glyph.anchorClass(anchorDict=anchor_dict))


def _get_anchor_data(anchor_data, ufo, components, anchor_name):
    """Get data for an anchor from a list of components."""

    anchors = []
    for component in components:
        for anchor in ufo[component.baseGlyph].anchors:
            if anchor.name == anchor_name:
                anchors.append((anchor, component))
                break
    if len(anchors) > 1:
        for i, (anchor, component) in enumerate(anchors):
            t = Transform(*component.transformation)
            name = '%s_%d' % (anchor.name, i + 1)
            anchor_data[name] = t.transformPoint((anchor.x, anchor.y))
    elif anchors:
        anchor, component = anchors[0]
        t = Transform(*component.transformation)
        anchor_data[anchor.name] = t.transformPoint((anchor.x, anchor.y))


def _adjust_anchors(anchor_data, ufo, component):
    """Adjust anchors to which a mark component may have been attached."""

    glyph = ufo[component.baseGlyph]
    t = Transform(*component.transformation)
    for anchor in glyph.anchors:
        # only adjust if this anchor has data and the component also contains
        # the associated mark anchor (e.g. "_top" for "top")
        if (anchor.name in anchor_data and
                any(a.name == '_' + anchor.name for a in glyph.anchors)):
            anchor_data[anchor.name] = t.transformPoint((anchor.x, anchor.y))
