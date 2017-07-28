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


from fontTools.pens.boundsPen import BoundsPen
from ufoLib import UFOReader, UFOWriter
from ufoLib.pointPen import PointToSegmentPen, SegmentToPointPen


class Features(object):
    def __init__(self):
        self.text = ''


class Component(object):
    def __init__(self, base, transform):
        self.baseGlyph = base
        self.transformation = transform


class Contour(object):
    def __init__(self):
        self.points = []

    def __len__(self):
        return len(self.points)

    def addPoint(self, pt):
        self.points.append(pt)

    def drawPoints(self, pen):
        pen.beginPath()
        for x, y, segment_type, smooth in self.points:
            pen.addPoint((x, y), segmentType=segment_type, smooth=smooth)
        pen.endPath()


class Glyph(object):
    def __init__(self, name, parent):
        self.name = name
        self.parent = parent

        self.anchors = []
        self.components = []
        self.contours = []

        self.guidelines = []
        self.lib = {}
        self.unicodes = []
        self.width = 0
        self.height = 0

        self.image = None
        self.note = None
        self.cached_bounds = None

    def __getitem__(self, index):
        return self.contours[index]

    def __len__(self):
        return len(self.contours)

    def clear(self):
        self.clearAnchors()
        self.clearComponents()
        self.clearContours()
        self.clearGuidelines()

    def clearAnchors(self):
        self.anchors = []

    def clearComponents(self):
        self.components = []

    def clearContours(self):
        self.contours = []

    def clearGuidelines(self):
        self.guidelines = []

    def addComponent(self, base, transform, identifier=None):
        self.components.append(Component(base, transform))
        self.cached_bounds = None

    def addPoint(
            self, pt, segmentType=None, smooth=False, name=None,
            identifier=None):
        self.contours[-1].addPoint(pt + (segmentType, smooth))
        self.cached_bounds = None

    def beginPath(self, identifier=None):
        self.contours.append(Contour())

    def draw(self, pen):
        self.drawPoints(PointToSegmentPen(pen))

    def drawPoints(self, pen):
        for contour in self.contours:
            contour.drawPoints(pen)
        for component in self.components:
            pen.addComponent(component.baseGlyph, component.transformation)

    def endPath(self):
        pass

    def getPen(self):
        return SegmentToPointPen(self)

    def getPointPen(self):
        return self

    def get_bounds(self):
        if self.cached_bounds is None:
            pen = BoundsPen(self.parent)
            self.draw(pen)
            self.cached_bounds = pen.bounds
        return self.cached_bounds

    bounds = property(get_bounds)

    def get_left_margin(self):
        bounds = self.bounds
        return bounds[0] if bounds is not None else None

    leftMargin = property(get_left_margin)

    def get_right_margin(self):
        bounds = self.bounds
        return bounds[2] if bounds is not None else None

    rightMargin = property(get_right_margin)

    def get_unicode(self):
        return self.unicodes[0] if self.unicodes else None

    def set_unicode(self, val):
        if val in self.unicodes:
            self.unicodes.remove(val)
        self.unicodes.insert(0, val)

    unicode = property(get_unicode, set_unicode)


class Info(object):
    def __init__(self):
        attrs = (
            'guidelines note openTypeGaspRangeRecords openTypeHeadFlags '
            'openTypeNameDescription openTypeNameLicense '
            'openTypeNameLicenseURL openTypeNameRecords openTypeNameSampleText '
            'openTypeNameUniqueID openTypeNameVersion '
            'openTypeNameWWSFamilyName openTypeNameWWSSubfamilyName '
            'openTypeOS2CodePageRanges openTypeOS2FamilyClass '
            'openTypeOS2Panose openTypeOS2Type openTypeOS2UnicodeRanges '
            'openTypeOS2VendorID postscriptDefaultCharacter '
            'postscriptForceBold postscriptIsFixedPitch '
            'postscriptWindowsCharacterSet trademark unitsPerEm'
        ).split()
        for attr in attrs:
            setattr(self, attr, None)


class Font(object):
    def __init__(
            self, path=None, kerningClass=None, infoClass=None,
            groupsClass=None, featuresClass=Features, libClass=None,
            glyphClass=None, glyphContourClass=None, glyphPointClass=None,
            glyphComponentClass=None, glyphAnchorClass=None):

        self.path = path
        self.features = Features()
        self.info = Info()
        self.groups = {}
        self.kerning = {}
        self.lib = {}
        self.glyphset = {}

        if path is not None:
            reader = UFOReader(path)
            reader.readInfo(self.info)
            self.features.text = reader.readFeatures()
            self.groups = reader.readGroups()
            self.kerning = reader.readKerning()
            self.lib = reader.readLib()
            glyphset = reader.getGlyphSet()
            for name in glyphset.keys():
                glyph = Glyph(name, self)
                glyphset.readGlyph(
                    glyphName=name, glyphObject=glyph, pointPen=glyph)
                self.glyphset[name] = glyph

        self.kerningGroupConversionRenameMaps = None

    def __contains__(self, name):
        return name in self.glyphset

    def __getitem__(self, name):
        return self.glyphset[name]

    def __iter__(self):
        for name in self.keys():
            yield self.glyphset[name]

    def keys(self):
        return self.glyphset.keys()

    def newGlyph(self, name):
        glyph = Glyph(name, self)
        self.glyphset[name] = glyph
        return glyph

    def save(self, path=None, formatVersion=3):
        if path is not None:
            self.path = path
        writer = UFOWriter(self.path, formatVersion=formatVersion)
        writer.writeFeatures(self.features.text)
        writer.writeGroups(self.groups)
        writer.writeInfo(self.info)
        writer.writeKerning(self.kerning)
        writer.writeLib(self.lib)
        glyphset = writer.getGlyphSet()
        for name, glyph in sorted(self.glyphset.items()):
            glyphset.writeGlyph(name, glyph, glyph.drawPoints)
        glyphset.writeContents()
        writer.writeLayerContents()
