from __future__ import annotations

import logging
import os
import re
from collections import OrderedDict
from inspect import isclass
from io import StringIO
from tempfile import NamedTemporaryFile

from fontTools import mtiLib
from fontTools.designspaceLib import DesignSpaceDocument, SourceDescriptor
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.feaLib.error import FeatureLibError, IncludedFeaNotFound
from fontTools.feaLib.parser import Parser
from fontTools.misc.loggingTools import Timer

from ufo2ft.constants import MTI_FEATURES_PREFIX
from ufo2ft.featureWriters import (
    CursFeatureWriter,
    GdefFeatureWriter,
    KernFeatureWriter,
    MarkFeatureWriter,
    ast,
    isValidFeatureWriter,
    loadFeatureWriters,
)
from ufo2ft.util import describe_ufo

logger = logging.getLogger(__name__)
timer = Timer(logging.getLogger("ufo2ft.timer"), level=logging.DEBUG)


def parseLayoutFeatures(font, includeDir=None):
    """Parse OpenType layout features in the UFO and return a
    feaLib.ast.FeatureFile instance.

    includeDir is an optional directory path to search for included
    feature files, if omitted the font.path is used. If the latter
    is also not set, the feaLib Lexer uses the current working directory.
    """
    featxt = font.features.text or ""
    if not featxt:
        return ast.FeatureFile()
    buf = StringIO(featxt)
    ufoPath = font.path
    if includeDir is None and ufoPath is not None:
        # The UFO v3 specification says "Any include() statements must be relative to
        # the UFO path, not to the features.fea file itself". We set the `name`
        # attribute on the buffer to the actual feature file path, which feaLib will
        # pick up and use to attribute errors to the correct file, and explicitly set
        # the include directory to the parent of the UFO.
        ufoPath = os.path.normpath(ufoPath)
        buf.name = os.path.join(ufoPath, "features.fea")
        includeDir = os.path.dirname(ufoPath) or "."
    glyphNames = set(font.keys())
    includeDir = os.path.normpath(includeDir) if includeDir else None
    try:
        parser = Parser(buf, glyphNames, includeDir=includeDir)
        doc = parser.parse()
    except IncludedFeaNotFound as e:
        if ufoPath and os.path.exists(os.path.join(ufoPath, e.args[0])):
            logger.warning(
                "Please change the file name in the include(...); "
                "statement to be relative to the UFO itself, "
                "instead of relative to the 'features.fea' file "
                "contained in it."
            )
        raise
    return doc


class BaseFeatureCompiler:
    """Base class for generating OpenType features and compiling OpenType
    layout tables from these.
    """

    def __init__(self, ufo, ttFont=None, glyphSet=None, extraSubstitutions=None):
        """
        Args:
          ufo: an object representing a UFO (defcon.Font or equivalent)
            containing the features source data.
          ttFont: a fontTools TTFont object where the generated OpenType
            tables are added. If None, an empty TTFont is used, with
            the same glyph order as the ufo object.
          glyphSet: a (optional) dict containing pre-processed copies of
            the UFO glyphs.
          extraSubstitutions: an optional dictionary mapping glyph names
            to a set of other glyphs which should be considered reachable
            from them (for example when using designspace rules to effect
            substitutions).
        """
        self.ufo = ufo

        if ttFont is None:
            from fontTools.ttLib import TTFont

            from ufo2ft.util import makeOfficialGlyphOrder

            ttFont = TTFont()
            ttFont.setGlyphOrder(makeOfficialGlyphOrder(ufo))
        self.ttFont = ttFont

        glyphOrder = ttFont.getGlyphOrder()
        if glyphSet is not None:
            if set(glyphOrder) != set(glyphSet.keys()):
                print("Glyph order incompatible")
                print("In UFO but not in font:", set(glyphSet.keys()) - set(glyphOrder))
                print("In font but not in UFO:", set(glyphOrder) - set(glyphSet.keys()))
            assert set(glyphOrder) == set(glyphSet.keys())
        else:
            glyphSet = ufo
        self.glyphSet = OrderedDict((gn, glyphSet[gn]) for gn in glyphOrder)

        self.extraSubstitutions = extraSubstitutions

    def setupFeatures(self):
        """Make the features source.

        **This should not be called externally.** Subclasses
        must override this method.
        """
        raise NotImplementedError

    def buildTables(self):
        """Compile OpenType feature tables from the source.

        **This should not be called externally.** Subclasses
        must override this method.
        """
        raise NotImplementedError

    def setupFile_features(self):
        """DEPRECATED. Use 'setupFeatures' instead."""
        _deprecateMethod("setupFile_features", "setupFeatures")
        self.setupFeatures()

    def setupFile_featureTables(self):
        """DEPRECATED. Use 'setupFeatures' instead."""
        _deprecateMethod("setupFile_featureTables", "buildTables")
        self.buildTables()

    def compile(self):
        if "setupFile_features" in self.__class__.__dict__:
            _deprecateMethod("setupFile_features", "setupFeatures")
            self.setupFile_features()
        else:
            self.setupFeatures()

        if "setupFile_featureTables" in self.__class__.__dict__:
            _deprecateMethod("setupFile_featureTables", "buildTables")
            self.setupFile_featureTables()
        else:
            self.buildTables()

        return self.ttFont


def _deprecateMethod(arg, repl):
    import warnings

    warnings.warn(
        f"{arg!r} method is deprecated; use {repl!r} instead",
        category=UserWarning,
        stacklevel=3,
    )


class FeatureCompiler(BaseFeatureCompiler):
    """Generate automatic features and compile OpenType tables from Adobe
    Feature File stored in the UFO, using fontTools.feaLib as compiler.
    """

    defaultFeatureWriters = [
        KernFeatureWriter,
        MarkFeatureWriter,
        GdefFeatureWriter,
        CursFeatureWriter,
    ]

    def __init__(
        self,
        ufo,
        ttFont=None,
        glyphSet=None,
        featureWriters=None,
        feaIncludeDir=None,
        extraSubstitutions=None,
        **kwargs,
    ):
        """
        Args:
          featureWriters: a list of BaseFeatureWriter subclasses or
            pre-initialized instances. The default value (None) means that:
            - first, the UFO lib will be searched for a list of featureWriters
              under the key "com.github.googlei18n.ufo2ft.featureWriters"
              (see loadFeatureWriters).
            - if that is not found, the default list of writers will be used:
              (see FeatureCompiler.defaultFeatureWriters, and the individual
              feature writer classes for the list of features generated).
            If the featureWriters list is empty, no automatic feature is
            generated and only pre-existing features are compiled.
            The ``featureWriters`` parameter overrides both the writers from
            the UFO lib and the default writers list. To extend instead of
            replace the latter, the list can contain a special value ``...``
            (i.e. the ``ellipsis`` singleton, not the str literal '...')
            which gets replaced by either the UFO.lib writers or the default
            ones; thus one can insert additional writers either before or after
            these.
          feaIncludeDir: a directory to be used as the include directory for
            the feature file. If None, the include directory is set to the
            parent directory of the UFO, provided the UFO has a path.
        """
        BaseFeatureCompiler.__init__(
            self, ufo, ttFont, glyphSet, extraSubstitutions=extraSubstitutions
        )
        self.feaIncludeDir = feaIncludeDir

        self.initFeatureWriters(featureWriters)

        if kwargs.get("mtiFeatures") is not None:
            import warnings

            warnings.warn(
                "mtiFeatures argument is ignored; "
                "you should use MtiLibFeatureCompiler",
                category=UserWarning,
                stacklevel=2,
            )

    def _load_custom_feature_writers(self, featureWriters=None):
        # Args:
        #   ufo: Font
        #   featureWriters: Optional[List[Union[FeatureWriter, EllipsisType]]])
        # Returns: List[FeatureWriter]

        # by default, load the feature writers from the lib or the default ones;
        # ellipsis is used as a placeholder so one can optionally insert additional
        # featureWriters=[w1, ..., w2] either before or after these, or override
        # them by omitting the ellipsis.
        if featureWriters is None:
            featureWriters = [...]
        result = []
        seen_ellipsis = False
        for writer in featureWriters:
            if writer is ...:
                if seen_ellipsis:
                    raise ValueError("ellipsis not allowed more than once")
                writers = loadFeatureWriters(self.ufo)
                if writers is not None:
                    result.extend(writers)
                else:
                    result.extend(self.defaultFeatureWriters)
                seen_ellipsis = True
            else:
                klass = writer if isclass(writer) else type(writer)
                if not isValidFeatureWriter(klass):
                    raise TypeError(f"Invalid feature writer: {writer!r}")
                result.append(writer)
        return result

    def initFeatureWriters(self, featureWriters=None):
        """Initialize feature writer classes as specified in the UFO lib.
        If none are defined in the UFO, the default feature writers are used
        (see FeatureCompiler.defaultFeatureWriters).
        The 'featureWriters' argument can be used to override these.
        The method sets the `self.featureWriters` attribute with the list of
        writers.

        Note that the writers that generate GSUB features are placed first in
        this list, before all others. This is because the GSUB table may be
        used in the subsequent feature writers to resolve substitutions from
        glyphs with unicodes to their alternates.
        """
        featureWriters = self._load_custom_feature_writers(featureWriters)

        gsubWriters = []
        others = []
        for writer in featureWriters:
            if isclass(writer):
                writer = writer()
            if writer.tableTag == "GSUB":
                gsubWriters.append(writer)
            else:
                others.append(writer)

        self.featureWriters = gsubWriters + others

    def setupFeatures(self):
        """
        Make the features source.

        **This should not be called externally.** Subclasses
        may override this method to handle the file creation
        in a different way if desired.
        """
        with timer("run feature writers"):
            if self.featureWriters:
                featureFile = parseLayoutFeatures(self.ufo, self.feaIncludeDir)

                # Insertion markers are only considered in "skip" mode.
                if any(writer.mode == "skip" for writer in self.featureWriters):
                    markers = {
                        writer.insertFeatureMarker
                        for writer in self.featureWriters
                        if writer.insertFeatureMarker is not None
                    }
                    warn_about_miscased_insertion_markers(
                        describe_ufo(self.ufo), featureFile, markers
                    )

                path = self.ufo.path
                for writer in self.featureWriters:
                    try:
                        writer.write(self.ufo, featureFile, compiler=self)
                    except FeatureLibError:
                        if path is None:
                            self._write_temporary_feature_file(featureFile.asFea())
                        raise

                # stringify AST to get correct line numbers in error messages
                self.features = featureFile.asFea()
            else:
                # no featureWriters, simply read existing features' text
                self.features = self.ufo.features.text or ""

    def writeFeatures(self, outfile):
        if hasattr(self, "features"):
            outfile.write(self.features)

    def buildTables(self):
        """
        Compile OpenType feature tables from the source.
        Raises a FeaLibError if the feature compilation was unsuccessful.

        **This should not be called externally.** Subclasses
        may override this method to handle the table compilation
        in a different way if desired.
        """

        if not self.features:
            return

        # the path is used by the lexer to follow 'include' statements;
        # if we generated some automatic features, includes have already been
        # resolved, and we work from a string which does't exist on disk
        path = self.ufo.path if not self.featureWriters else None
        with timer("build OpenType features"):
            try:
                addOpenTypeFeaturesFromString(self.ttFont, self.features, filename=path)
            except FeatureLibError:
                if path is None:
                    self._write_temporary_feature_file(self.features)
                raise

    def _write_temporary_feature_file(self, features: str) -> None:
        # if compilation fails, create temporary file for inspection
        data = features.encode("utf-8")
        with NamedTemporaryFile(delete=False) as tmp:
            tmp.write(data)
        logger.error("Compilation failed! Inspect temporary file: %r", tmp.name)


class MtiFeatureCompiler(BaseFeatureCompiler):
    """Compile OpenType layout tables from MTI feature files using
    fontTools.mtiLib.
    """

    def setupFeatures(self):
        ufo = self.ufo
        features = {}
        # includes the length of the "/" separator
        prefixLength = len(MTI_FEATURES_PREFIX) + 1
        for fn in ufo.data.fileNames:
            if fn.startswith(MTI_FEATURES_PREFIX) and fn.endswith(".mti"):
                content = ufo.data[fn].decode("utf-8")
                features[fn[prefixLength:-4]] = content
        self.mtiFeatures = features

    def buildTables(self):
        for tag, features in self.mtiFeatures.items():
            table = mtiLib.build(features.splitlines(), self.ttFont)
            assert table.tableTag == tag
            self.ttFont[tag] = table


def warn_about_miscased_insertion_markers(
    ufo_description: str, feaFile: ast.FeatureFile, patterns: set[str]
) -> None:
    """Warn the user about potentially mistyped feature insertion markers."""

    patterns_compiled = tuple(
        (re.compile(pattern), re.compile(pattern, re.IGNORECASE))
        for pattern in patterns
    )

    # NOTE: Insertion markers can only meaningfully occur in top-level feature
    # blocks.
    for block in ast.iterFeatureBlocks(feaFile):
        for statement in block.statements:
            if not isinstance(statement, ast.Comment):
                continue
            for pattern_case, pattern_ignore_case in patterns_compiled:
                text = str(statement)
                match_case = re.match(pattern_case, text)
                match_ignore_case = re.match(pattern_ignore_case, text)
                if match_ignore_case and not match_case:
                    logger.warning(
                        "%s: The insertion comment '%s' in the feature file is "
                        "miscased (search pattern: %s), ignoring it.",
                        ufo_description,
                        text,
                        pattern_case.pattern,
                    )


class VariableFeatureCompiler(FeatureCompiler):
    """Generate a variable feature file and compile OpenType tables from a
    designspace file.
    """

    def __init__(
        self,
        ufo,
        designspace,
        ttFont=None,
        glyphSet=None,
        featureWriters=None,
        **kwargs,
    ):
        self.designspace = designspace
        super().__init__(ufo, ttFont, glyphSet, featureWriters, **kwargs)

    def setupFeatures(self):
        if self.featureWriters:
            featureFile = parseLayoutFeatures(self.ufo)

            for writer in self.featureWriters:
                writer.write(self.designspace, featureFile, compiler=self)

            # stringify AST to get correct line numbers in error messages
            self.features = featureFile.asFea()
        else:
            # no featureWriters, simply read existing features' text
            self.features = self.ufo.features.text or ""


def _featuresCompatible(designSpaceDoc: DesignSpaceDocument) -> bool:
    """Returns whether the features of the individual source UFOs are the same.

    NOTE: Only compares the feature file text inside the source UFO and does not
    follow imports. This will suffice as long as no external feature file is
    using variable syntax and all sources are stored n the same parent folder
    (so the same includes point to the same files).
    """

    assert all(hasattr(source.font, "features") for source in designSpaceDoc.sources)

    def transform(f: SourceDescriptor) -> str:
        # Strip comments
        text = re.sub("(?m)#.*$", "", f.font.features.text or "")
        # Strip extraneous whitespace
        text = re.sub(r"\s+", " ", text)
        return text

    first = transform(designSpaceDoc.sources[0])
    return all(transform(s) == first for s in designSpaceDoc.sources[1:])
