from __future__ import (
    print_function, division, absolute_import, unicode_literals)
from fontTools.misc.py23 import SimpleNamespace
from fontTools.feaLib import ast
import collections
import re

from ufo2ft.util import compileGSUB


class BaseFeatureWriter(object):
    """Abstract features writer.

    The `features` class attribute defines the set of all the features
    that this writer supports. If you want to only write some of the
    available features you can provide a smaller sequence to 'features'
    constructor argument. By the default all the features supported by
    this writer will be outputted.

    Two writing modes are defined here:
    1) "skip" (default) will not write anything if any of the features
       listed is already present;
    2) "append" will add additional lookups to an existing feature,
       if present, or it will add a new one at the end of all features.
    Subclasses can set a different default mode or define a different
    set of `_SUPPORTED_MODES`.

    The `options` class attribute contains a mapping of option
    names with their default values. These can be overridden on an
    instance by passing keyword arguments to the constructor.
    """

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

    def set_context(self, font, compiler=None):
        """ Populate a temporary `self.context` namespace, which is reset
        before each new call to `_write` method.
        Subclasses can override this to provide contextual information
        which depends on other data in the font, or set any other
        temporary attributes.
        The default implementation simply sets the current font, a compiler
        instance (optional, when called from FeatureCompiler), and returns
        the namepace instance.
        """
        self.context = SimpleNamespace(font=font, compiler=compiler)
        return self.context

    def write(self, font, feaFile, compiler=None):
        """Write features and class definitions for this font to a feaLib
        FeatureFile object.
        Returns True if feature file was modified, False if no new features
        were generated.
        """
        if self.mode == "skip":
            existingFeatures = self.findFeatureTags(feaFile)
            if existingFeatures.intersection(self.features):
                return False

        self.set_context(font, compiler=compiler)
        try:
            return self._write(feaFile)
        finally:
            del self.context

    def _write(self, feaFile):
        """Subclasses must override this."""
        raise NotImplementedError

    def makeUnicodeToGlyphNameMapping(self):
        """Return the Unicode to glyph name mapping for the current font.
        """
        # Try to get the "best" Unicode cmap subtable if this writer is running
        # in the context of a FeatureCompiler, else create a new mapping from
        # the UFO glyphs
        compiler = self.context.compiler
        cmap = None
        if compiler is not None:
            cmap = compiler.ttFont["cmap"].getBestCmap()
        if cmap is None:
            from ufo2ft.util import makeUnicodeToGlyphNameMapping
            cmap = makeUnicodeToGlyphNameMapping(self.context.font)
        return cmap

    def compileGSUB(self, feaFile):
        """Compile a temporary GSUB table from feature file, to be used
        with the FontTools subsetter to find all the glyphs that are
        "reachable" via substitutions from an initial set of glyphs
        with specific unicode properties.
        """
        compiler = self.context.compiler
        if compiler is not None:
            glyphOrder = compiler.ttFont.getGlyphOrder()
        else:
            # the 'real' order doesn't matter because the table is meant to
            # be thrown away
            glyphOrder = sorted(self.context.font.keys())
        return compileGSUB(feaFile, glyphOrder)

    # ast helpers

    LOOKUP_FLAGS = {
        "RightToLeft": 1,
        "IgnoreBaseGlyphs": 2,
        "IgnoreLigatures": 4,
        "IgnoreMarks": 8,
    }

    @staticmethod
    def findFeatureTags(feaFile):
        return {f.name for f in feaFile.statements
                if isinstance(f, ast.FeatureBlock)}

    @classmethod
    def makeLookupFlag(cls, name=None, markAttachment=None,
                       markFilteringSet=None):
        value = 0 if name is None else cls.LOOKUP_FLAGS[name]

        if markAttachment is not None:
            assert isinstance(markAttachment, ast.GlyphClassDefinition)
            markAttachment = ast.GlyphClassName(markAttachment)

        if markFilteringSet is not None:
            assert isinstance(markFilteringSet, ast.GlyphClassDefinition)
            markFilteringSet = ast.GlyphClassName(markFilteringSet)

        return ast.LookupFlagStatement(value,
                                       markAttachment=markAttachment,
                                       markFilteringSet=markFilteringSet)

    @classmethod
    def makeGlyphClassDefinitions(cls, groups, stripPrefix=""):
        """ Given a groups dictionary ({str: list[str]}), create feaLib
        GlyphClassDefinition objects for each group.
        Return an OrderedDict (sorted alphabetically) keyed by the original
        group name.

        If `stripPrefix` (str) is provided and a group name starts with it,
        the string will be stripped from the beginning of the class name.
        """
        classDefs = collections.OrderedDict()
        classNames = set()
        lengthPrefix = len(stripPrefix)
        for groupName, members in sorted(groups.items()):
            originalGroupName = groupName
            if stripPrefix and groupName.startswith(stripPrefix):
                groupName = groupName[lengthPrefix:]
            className = cls.makeFeaClassName(groupName, classNames)
            classNames.add(className)
            classDef = cls.makeGlyphClassDefinition(className, members)
            classDefs[originalGroupName] = classDef
        return classDefs

    @staticmethod
    def makeGlyphClassDefinition(className, members):
        glyphNames = [ast.GlyphName(g) for g in members]
        glyphClass = ast.GlyphClass(glyphNames)
        classDef = ast.GlyphClassDefinition(className, glyphClass)
        return classDef

    @staticmethod
    def makeFeaClassName(name, existingClassNames=None):
        """Make a glyph class name which is legal to use in feature text.

        Ensures the name only includes characters in "A-Za-z0-9._", and
        isn't already defined.
        """
        name = re.sub(r"[^A-Za-z0-9._]", r"", name)
        if existingClassNames is None:
            return name
        i = 1
        origName = name
        while name in existingClassNames:
            name = "%s_%d" % (origName, i)
            i += 1
        return name

    @staticmethod
    def addLookupReference(feature, lookup, languageSystems=None):
        """Add reference to a named lookup to the feature's statements.
        If 'languageSystems' is provided, only register the named lookup for
        the given scripts and languages; otherwise add a global reference
        which will be registered for all the scripts and languages in the
        feature file's `languagesystems` statements.

        Language systems are passed in as an ordered dictionary mapping
        scripts to lists of languages.
        """
        if not languageSystems:
            feature.statements.append(
                ast.LookupReferenceStatement(lookup))
            return

        for script, languages in languageSystems.items():
            feature.statements.append(ast.ScriptStatement(script))
            for language in languages:
                feature.statements.append(
                    ast.LanguageStatement(language, include_default=False))
                feature.statements.append(
                    ast.LookupReferenceStatement(lookup))
