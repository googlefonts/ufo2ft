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


from fontTools.pens.boundsPen import BoundsPen, ControlBoundsPen
from ufoLib import UFOReader, UFOWriter
from ufoLib.pointPen import PointToSegmentPen, SegmentToPointPen
import os
import weakref
try:
    from collections.abc import Mapping  # python >= 3.3
except ImportError:
    from collections import Mapping

DEFAULT_LAYER_NAME = 'public.default'
TRANSFORMATION_INFO = [
    ('xScale', 1),
    ('xyScale', 0),
    ('yxScale', 0),
    ('yScale', 1),
    ('xOffset', 0),
    ('yOffset', 0)
]


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
    def __init__(self, name=None, parent=None, anchorClass=None):
        self.name = name
        self.parent = parent
        self.layer = None

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
        self.cached_controlPointsBounds = None

        if anchorClass is None:
            self.anchorClass = Anchor
        else:
            self.anchorClass = anchorClass

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

    def appendAnchor(self, anchor):
        self.anchors.append(anchor)

    def addComponent(self, base, transform, identifier=None):
        self.components.append(Component(base, transform))
        self.cached_bounds = None
        self.cached_controlPointsBounds = None

    def addPoint(
            self, pt, segmentType=None, smooth=False, name=None,
            identifier=None):
        self.contours[-1].addPoint(pt + (segmentType, smooth))
        self.cached_bounds = None
        self.cached_controlPointsBounds = None

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

    def _get_controlPointBounds(self):
        if self.cached_controlPointsBounds is None:
            pen = ControlBoundsPen(self.parent)
            self.draw(pen)
            self.cached_controlPointsBounds = pen.bounds
        return self.cached_controlPointsBounds

    controlPointBounds = property(_get_controlPointBounds)

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
            'familyName styleName '
            'guidelines note openTypeGaspRangeRecords openTypeHeadFlags '
            'openTypeNameDescription openTypeNameLicense '
            'openTypeNameLicenseURL openTypeNameRecords '
            'openTypeNameSampleText '
            'openTypeNameUniqueID openTypeNameVersion '
            'openTypeNameWWSFamilyName openTypeNameWWSSubfamilyName '
            'openTypeOS2CodePageRanges openTypeOS2FamilyClass '
            'openTypeOS2Panose openTypeOS2Type openTypeOS2UnicodeRanges '
            'openTypeOS2Selection openTypeHheaAscender openTypeHheaDescender '
            'openTypeHheaLineGap openTypeOS2TypoAscender '
            'openTypeOS2TypoDescender openTypeOS2TypoLineGap '
            'openTypeOS2WinAscent openTypeOS2WinDescent '
            'openTypeOS2WidthClass openTypeHeadCreated '
            'openTypeOS2VendorID postscriptDefaultCharacter '
            'postscriptForceBold postscriptIsFixedPitch '
            'postscriptWindowsCharacterSet trademark unitsPerEm '
            'postscriptUnderlineThickness postscriptUnderlinePosition '
            'postscriptFamilyBlues postscriptFamilyOtherBlues'
            'openTypeOS2WidthClass openTypeOS2WeightClass'
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
        self.layers = {}
        self._defaultLayerName = DEFAULT_LAYER_NAME
        self.data = DataSet(font=self)

        if path is not None:
            reader = UFOReader(path)
            reader.readInfo(self.info)
            self.features.text = reader.readFeatures()
            self.groups = reader.readGroups()
            self.kerning = reader.readKerning()
            self.lib = reader.readLib()
            self._defaultLayerName = reader.getDefaultLayerName()
            for layerName in reader.getLayerNames():
                glyphset = reader.getGlyphSet(layerName)
                if layerName not in self.layers:
                    self.newLayer(layerName)
                for name in glyphset.keys():
                    glyph = self.layers[layerName].newGlyph(name)
                    glyphset.readGlyph(
                        glyphName=name, glyphObject=glyph, pointPen=glyph)
            self.data.fileNames = reader.getDataDirectoryListing()
        if self._defaultLayerName not in self.layers:
            self.newLayer(self._defaultLayerName)

        self.kerningGroupConversionRenameMaps = None

    def __contains__(self, name):
        return name in self.layers[self._defaultLayerName]

    def __getitem__(self, name):
        return self.layers[self._defaultLayerName][name]

    def __iter__(self):
        for name in self.keys():
            yield self.layers[self._defaultLayerName][name]

    def __delitem__(self, name):
        del self.layers[self._defaultLayerName][name]

    def keys(self):
        return self.layers[self._defaultLayerName].keys()

    def newGlyph(self, name):
        layer = self.layers[self._defaultLayerName]
        glyph = layer.newGlyph(name)
        return glyph

    def newLayer(self, name):
        layer = Layer(name, self)
        self.layers[name] = layer
        return layer

    @property
    def glyphOrder(self):
        return self.lib.get('public.glyphOrder', [])

    @glyphOrder.setter
    def glyphOrder(self, value):
        if value is None or len(value) == 0:
            if 'public.glyphOrder' in self.lib:
                del self.lib['public.glyphOrder']
            return
        self.lib['public.glyphOrder'] = value

    def save(self, path=None, formatVersion=3):
        if path is not None:
            self.path = path
        writer = UFOWriter(self.path, formatVersion=formatVersion)
        writer.writeFeatures(self.features.text)
        writer.writeGroups(self.groups)
        writer.writeInfo(self.info)
        writer.writeKerning(self.kerning)
        writer.writeLib(self.lib)
        for layerName in self.layers:
            defaultLayer = (layerName == self._defaultLayerName)
            glyphset = writer.getGlyphSet(layerName, defaultLayer)
            for name, glyph in sorted(self.layers[layerName].glyphs.items()):
                glyphset.writeGlyph(name, glyph, glyph.drawPoints)
            glyphset.writeContents()
        writer.writeLayerContents()
        self.data.save(writer, saveAs=False)


class Layer(object):
    def __init__(self, name, parent):
        self.name = name
        self.parent = parent
        self.glyphs = {}

    def __contains__(self, name):
        return name in self.glyphs

    def __getitem__(self, name):
        return self.glyphs[name]

    def __iter__(self):
        for name in self.keys():
            yield self.glyphs[name]

    def __delitem__(self, name):
        del self.glyphs[name]

    def keys(self):
        return self.glyphs.keys()

    def newGlyph(self, name):
        glyph = Glyph(name, self)
        glyph.layer = self
        glyph.font = self.parent
        self.glyphs[name] = glyph
        return glyph


class Anchor(Mapping):
    _attrs = ['x', 'y', 'name', 'color', 'identifier']

    def __init__(self, anchorDict):
        for attr in self._attrs:
            setattr(self, attr, anchorDict.get(attr))

    def __getitem__(self, name):
        return getattr(self, name, None)

    def __iter__(self):
        for key in self._attrs:
            yield key

    def __len__(self):
        return len(a for a in self._attrs if a in self)


class DataSet(object):

    def __init__(self, font=None):
        if font is not None:
            self._font = weakref.ref(font)
        else:
            self._font = None
        self._data = {}

    def getParent(self):
        return self.font

    def _get_font(self):
        if self._font is not None:
            return self._font()

    font = property(_get_font)

    @property
    def fileNames(self):
        return list(self._data.keys())

    @fileNames.setter
    def fileNames(self, fileNames):
        for fileName in fileNames:
            self._data[fileName] = None

    def __getitem__(self, fileName):
        if self._data[fileName] is None:
            path = self.font.path
            reader = UFOReader(path)
            path = os.path.join("data", fileName)
            self._data[fileName] = reader.readBytesFromPath(path)
        return self._data[fileName]

    def __setitem__(self, fileName, data):
        self._data[fileName] = data

    def __delitem__(self, fileName):
        del self._data[fileName]

    def save(self, writer, saveAs=False):
        for fileName in self.fileNames:
            data = self[fileName]
            path = os.path.join("data", fileName)
            writer.writeBytesToPath(path, data)
