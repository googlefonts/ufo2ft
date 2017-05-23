import logging

from fontTools.pens.basePen import AbstractPen
from fontTools.misc.transform import Transform


logger = logging.getLogger(__name__)


class BaseFilterPen(AbstractPen):
    """Base class for segment pens that transform coordinates and pass
    them to another pen.
    """
    def __init__(self, outPen, *args, **kwargs):
        self._outPen = outPen


class PassThroughFilterPen(BaseFilterPen):
    """Does nothing but pass commands to other pen with no modifications."""
    def moveTo(self, pt):
        self._outPen.moveTo(*self._apply(pt))

    def lineTo(self, pt):
        self._outPen.lineTo(*self._apply(pt))

    def curveTo(self, *points):
        self._outPen.curveTo(*self._apply(*points))

    def qCurveTo(self, *points):
        self._outPen.qCurveTo(*self._apply(*points))

    def closePath(self):
        self._outPen.closePath()

    def endPath(self):
        self._outPen.endPath()

    def addComponent(self, glyphName, transformation):
        self._outPen.addComponent(glyphName, transformation)

    def _apply(self, *points):
        """Apply filter operation to points. Subclass may need to override it."""
        return points


class TransformationsFilterPen(PassThroughFilterPen):
    """Does transformation based on the filter in UFO.
    """
    def __init__(self, outPen, *args, **kwargs):
        super(TransformationsFilterPen, self).__init__(outPen)
        self.kwargs = kwargs
        self.args = args
        self.transform = Transform() 
        self.transform = self.transform.translate(self.kwargs.get('OffsetX', 0), self.kwargs.get('OffsetY', 0))
        self.transform = self.transform.scale(self.kwargs.get('ScaleX', 1), self.kwargs.get('ScaleY', 1))

        for argument in [x for x in ['LSB', 'RSB', 'Width', 'Slant', 'SlantCorrection', 'Origin'] if x in self.kwargs.keys()]:
            logger.warn('argument {} is not implemented yet. {} is skipped.'.format(argument, argument))

    def _apply(self, *points):
        return tuple(self.transform.transformPoints(list(points)))

class BaseFilter(object):
    """Basefilter does nothing but implements the basic operations for filters.
       it is a transparent filter. """
    def __init__(self, name=None, args=[], kwargs={}):
        # subclasses need to override it
        self.filterPenClass = PassThroughFilterPen
        self.nextFilter = None
        self.name = name
        self.exclude = kwargs.get('exclude', frozenset())
        self.include = kwargs.get('include', None)
        if self.include:
            self.include = fronzenset(map(str.strip, self.include))

        if kwargs.get('exclude') and kwargs.get('include'):
            logger.error('exclude and include can not coexist in a filter. Skipping current filter. name: {}, args: {}, kwargs: {}'.format(name, args, kwargs))
            self.include = frozenset()

        self.args = args
        self.kwargs = kwargs

    def __call__(self, glyph):
        """Apply current filter and then its nextFilter (if exist) to glyph."""
        if self.nextFilter:
            return self.nextFilter(glyph)
        return glyph

    def setFilterPenClass(self, filterPenClass):
        self.filterPenClass = filterPenClass

    def add(self, nextFilter):
        """Chain a filter to current filter."""
        f = self
        assert self != nextFilter, 'Can not add a filter to itself.'
        while f.nextFilter:
             f = f.nextFilter
             assert f != nextFilter, 'Can not create loop in the filter chain.'
        f.nextFilter = nextFilter
        return self

class TransformationsFilter(BaseFilter):
    """TransformationFilter implements transformation parameter in glyphs filter
        Reference: Glyphs Handbook, page 184
    """
    def __init__(self, args, kwargs):
        super(TransformationsFilter, self).__init__('Transformations', args, kwargs)
        self.setFilterPenClass(TransformationsFilterPen)

    def __call__(self, glyph):
        """Apply current filter and then its nextFilter (if exist) to glyph."""
        if glyph.name in self.exclude or (self.include and glyph.name not in self.include):
            if self.nextFilter:
                return self.nextFilter(glyph)
            return glyph

        newGlyph = glyph.__class__()
        newGlyph.name = glyph.name
        newGlyph.unicodes = glyph.unicodes
        newGlyph.unicode = glyph.unicode
        newGlyph.leftMargin = glyph.leftMargin
        newGlyph.rightMargin = glyph.rightMargin
        newGlyph.width = glyph.width
        newGlyph.height = glyph.height

        filterPen = self.filterPenClass(newGlyph.getPen(), *self.args, **self.kwargs)
        for anchor in glyph.anchors:
            newAnchor = defcon.Anchor()
            newAnchor.x = filterPen.transform.transformPoint(anchor.x)
            newAnchor.y = filterPen.transform.transformPoint(anchor.y)
            newGlyph.appendAnchor(newAnchor)

        glyph.draw(filterPen)

        if self.nextFilter:
            newGlyph = self.nextFilter(newGlyph)

        return newGlyph

