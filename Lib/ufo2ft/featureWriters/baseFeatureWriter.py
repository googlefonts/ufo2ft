import logging
from collections import OrderedDict
from types import SimpleNamespace

from ufo2ft.featureWriters import ast
from ufo2ft.errors import InvalidFeaturesData

FEATURE_INSERT_MARKER = "# Automatic Code"


class BaseFeatureWriter:
    """Abstract features writer.

    The `tableTag` class attribute (str) states the tag of the OpenType
    Layout table which the generated features are intended for.
    For example: "GPOS", "GSUB", "BASE", etc.

    The `features` class attribute defines the set of all the features
    that this writer supports. If you want to only write some of the
    available features you can provide a smaller sequence to 'features'
    constructor argument. By the default all the features supported by
    this writer will be outputted.

    Two writing modes are defined here:
    1) "skip" (default) will not write features if already present;
    2) "append" will add additional lookups to an existing feature,
       if present, or it will add a new one at the end of all features.
    Subclasses can set a different default mode or define a different
    set of `_SUPPORTED_MODES`.

    The `options` class attribute contains a mapping of option
    names with their default values. These can be overridden on an
    instance by passing keyword arguments to the constructor.
    """

    tableTag = None
    features = frozenset()
    mode = "skip"
    options = {}

    _SUPPORTED_MODES = frozenset(["skip", "append"])

    def __init__(self, features=None, mode=None, **kwargs):
        if features is not None:
            features = frozenset(features)
            assert features, "features cannot be empty"
            unsupported = features.difference(self.__class__.features)
            if unsupported:
                raise ValueError("unsupported: %s" % ", ".join(unsupported))
            self.features = features

        if mode is not None:
            self.mode = mode
        if self.mode not in self._SUPPORTED_MODES:
            raise ValueError(self.mode)

        options = dict(self.__class__.options)
        for k in kwargs:
            if k not in options:
                raise TypeError("unsupported keyword argument: %r" % k)
            options[k] = kwargs[k]
        self.options = SimpleNamespace(**options)

        logger = ".".join([self.__class__.__module__, self.__class__.__name__])
        self.log = logging.getLogger(logger)

    def setContext(self, font, feaFile, compiler=None):
        """Populate a temporary `self.context` namespace, which is reset
        after each new call to `_write` method.
        Subclasses can override this to provide contextual information
        which depends on other data, or set any temporary attributes.

        The default implementation sets:
        - the current font;
        - the current FeatureFile object;
        - the current compiler instance (only present when this writer was
          instantiated from a FeatureCompiler);
        - a set of features (tags) to be generated. If self.mode is "skip",
          these are all the features which are _not_ already present.

        Returns the context namespace instance.
        """
        todo = set(self.features)
        if self.mode == "skip":
            existing = ast.findFeatureTags(feaFile)
            todo.difference_update(existing)

        self.context = SimpleNamespace(
            font=font, feaFile=feaFile, compiler=compiler, todo=todo
        )

        return self.context

    def shouldContinue(self):
        """Decide whether to start generating features or return early.
        Returns a boolean: True to proceed, False to skip.

        Sublcasses may override this to skip generation based on the presence
        or lack of other required pieces of font data.
        """
        if not self.context.todo:
            self.log.debug("No features to be generated; skipped")
            return False
        return True

    def write(self, font, feaFile, compiler=None):
        """Write features and class definitions for this font to a feaLib
        FeatureFile object.
        Returns True if feature file was modified, False if no new features
        were generated.
        """
        self.setContext(font, feaFile, compiler=compiler)
        try:
            if self.shouldContinue():
                return self._write()
            else:
                return False
        finally:
            del self.context

    def _write(self):
        """Subclasses must override this."""
        raise NotImplementedError

    def _insert(self, feaFile, classDefs=None, markClassDefs=None, lookups=None,
                features=None, insertFeatureMarker=FEATURE_INSERT_MARKER):
        """Insert feature at insert marker comment"""

        statements = feaFile.statements

        # Find last class definition and insert classDefs
        if classDefs:
            # currentClassDefs = [
            #     cd for cd in ast.iterClassDefinitions(self.context.feaFile)
            # ]
            statements.extend(classDefs)

        # Insert markClassDefs
        if markClassDefs:
            markClassDefs.append(ast.Comment(""))
            # currentMarkClassDefs = [
            #     cd for cd in ast.iterMarkClassDefinitions(feaFile)
            # ]
            statements.extend(markClassDefs)

        # Collect insert markers in blocks
        insertComments = dict()
        for parent, comment in ast.findCommentPattern(feaFile, insertFeatureMarker):
            if parent is None:
                # TODO: handle insert markers outside of blocks (when parent is None)
                raise InvalidFeaturesData(
                    "Invalid insert marker \"%s\" outside of feature block" % str(comment)
                )
            elif parent.name not in insertComments.keys():
                insertComments[parent.name] = (parent, comment)

        # Add the lookup blocks
        if lookups is None:
            wroteLookups = True
        elif not insertComments:
            if statements:
                statements.append(ast.Comment(""))
            statements.extend(lookups)
            wroteLookups = True
        else:
            wroteLookups = False

        for _, feature in features:
            if feature.name in insertComments:
                block, comment = insertComments[feature.name]
                index = block.statements.index(comment)
                # insertMark comment is at the top of the feature block
                # or only preceded by other comments
                if all(
                    isinstance(s, ast.ast.Comment) for s in
                    block.statements[:index]
                ):
                    index = statements.index(block)
                # insertMark comment is at the bottom of the feature block
                # or only followed by other comments
                elif all(
                    isinstance(s, ast.ast.Comment) for s in
                    block.statements[index:]
                ):

                    index = statements.index(block) + 1
                # insertMark comment is in the middle of the feature block
                # preceded and followed by statements that are not comments
                else:
                    split_block = ast.FeatureBlock(block.name)
                    split_block.statements = block.statements[index:]
                    block.statements = block.statements[:index]
                    index = statements.index(block) + 1
                    statements.insert(index, split_block)
            else:
                index = len(statements)

            statements.insert(index, feature)
            if not wroteLookups:
                statements = feaFile.statements = (
                    statements[:index] + lookups + statements[index:]
                )
                wroteLookups = True

    def makeUnicodeToGlyphNameMapping(self):
        """Return the Unicode to glyph name mapping for the current font."""
        # Try to get the "best" Unicode cmap subtable if this writer is running
        # in the context of a FeatureCompiler, else create a new mapping from
        # the UFO glyphs
        compiler = self.context.compiler
        cmap = None
        if compiler is not None:
            table = compiler.ttFont.get("cmap")
            if table is not None:
                cmap = table.getBestCmap()
        if cmap is None:
            from ufo2ft.util import makeUnicodeToGlyphNameMapping

            if compiler is not None:
                glyphSet = compiler.glyphSet
            else:
                glyphSet = self.context.font
            cmap = makeUnicodeToGlyphNameMapping(glyphSet)
        return cmap

    def getOrderedGlyphSet(self):
        """Return OrderedDict[glyphName, glyph] sorted by glyphOrder."""
        compiler = self.context.compiler
        if compiler is not None:
            return compiler.glyphSet

        from ufo2ft.util import _GlyphSet, makeOfficialGlyphOrder

        font = self.context.font
        # subset glyphSet by skipExportGlyphs if any
        glyphSet = _GlyphSet.from_layer(
            font,
            skipExportGlyphs=set(font.lib.get("public.skipExportGlyphs", [])),
        )
        glyphOrder = makeOfficialGlyphOrder(glyphSet, font.glyphOrder)
        return OrderedDict((gn, glyphSet[gn]) for gn in glyphOrder)

    def compileGSUB(self):
        """Compile a temporary GSUB table from the current feature file."""
        from ufo2ft.util import compileGSUB

        compiler = self.context.compiler
        if compiler is not None:
            # The result is cached in the compiler instance, so if another
            # writer requests one it is not compiled again.
            if hasattr(compiler, "_gsub"):
                return compiler._gsub

            glyphOrder = compiler.ttFont.getGlyphOrder()
        else:
            # the 'real' glyph order doesn't matter because the table is not
            # compiled to binary, only the glyph names are used
            glyphOrder = sorted(self.context.font.keys())

        gsub = compileGSUB(self.context.feaFile, glyphOrder)

        if compiler and not hasattr(compiler, "_gsub"):
            compiler._gsub = gsub
        return gsub
