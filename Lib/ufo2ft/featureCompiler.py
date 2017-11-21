from __future__ import \
    print_function, division, absolute_import, unicode_literals
import logging
import os
from inspect import isclass
from tempfile import NamedTemporaryFile

from fontTools import feaLib
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools import mtiLib
from fontTools.misc.py23 import UnicodeIO, tobytes

from ufo2ft.featureWriters import DEFAULT_FEATURE_WRITERS
from ufo2ft.maxContextCalc import maxCtxFont

logger = logging.getLogger(__name__)


class FeatureCompiler(object):
    """Generates OpenType feature tables for a UFO.

    *featureWriters* argument is a list that can contain either subclasses
    of BaseFeatureWriter or pre-initialized instances (or a mix of the two).
    Classes are initialized without arguments so will use default options.

    Features will be written by each feature writer in the given order.
    The default value is [KernFeatureWriter, MarkFeatureWriter].

    If mtiFeatures is passed to the constructor, it should be a dictionary
    mapping feature table tags to MTI feature declarations for that table.
    These are passed to mtiLib for compilation.
    """

    def __init__(self, font, outline,
                 featureWriters=None,
                 mtiFeatures=None):
        self.font = font
        self.outline = outline
        if featureWriters is None:
            featureWriters = DEFAULT_FEATURE_WRITERS
        self.featureWriters = []
        for writer in featureWriters:
            if isclass(writer):
                writer = writer()
            self.featureWriters.append(writer)
        self.mtiFeatures = mtiFeatures

    def compile(self):
        """Compile the features.

        Starts by generating feature syntax for the kern, mark, and mkmk
        features. If they already exist, they will not be overwritten.
        """

        self.setupFile_features()
        self.setupFile_featureTables()
        self.postProcess()

    def setupFile_features(self):
        """
        Make the features source file. If any tables
        or the kern feature are defined in the font's
        features, they will not be overwritten.

        **This should not be called externally.** Subclasses
        may override this method to handle the file creation
        in a different way if desired.
        """

        if self.mtiFeatures is not None:
            return

        existingFeatures = self._findLayoutFeatures()

        # build features as necessary
        autoFeatures = []
        # the current MarkFeatureWriter writes both mark and mkmk features
        # with shared markClass definitions; to prevent duplicate glyphs in
        # markClass, here we write the features only if none of them is alread
        # present.
        # TODO: Support updating pre-existing markClass definitions to allow
        # writing either mark or mkmk features indipendently from each other
        # https://github.com/googlei18n/fontmake/issues/319
        font = self.font
        for fw in self.featureWriters:
            if (fw.mode == "append" or (
                    fw.mode == "skip" and
                    all(fea not in existingFeatures for fea in fw.features))):
                autoFeatures.append(fw.write(font))

        # write the features
        self.features = "\n\n".join([font.features.text or ""] + autoFeatures)

    def _findLayoutFeatures(self):
        """Returns what OpenType layout feature tags are present in the UFO."""
        featxt = self.font.features.text
        if not featxt:
            return set()
        buf = UnicodeIO(featxt)
        # the path is only used by the lexer to resolve 'include' statements
        if self.font.path is not None:
            buf.name = os.path.join(self.font.path, "features.fea")
        glyphMap = self.outline.getReverseGlyphMap()
        parser = feaLib.parser.Parser(buf, glyphMap)
        doc = parser.parse()
        return {f.name for f in doc.statements
                if isinstance(f, feaLib.ast.FeatureBlock)}

    def setupFile_featureTables(self):
        """
        Compile and return OpenType feature tables from the source.
        Raises a FeaLibError if the feature compilation was unsuccessful.

        **This should not be called externally.** Subclasses
        may override this method to handle the table compilation
        in a different way if desired.
        """

        if self.mtiFeatures is not None:
            for tag, features in self.mtiFeatures.items():
                table = mtiLib.build(features.splitlines(), self.outline)
                assert table.tableTag == tag
                self.outline[tag] = table

        elif self.features.strip():
            # the path to features.fea is only used by the lexer to resolve
            # the relative "include" statements
            if self.font.path is not None:
                feapath = os.path.join(self.font.path, "features.fea")
            else:
                # in-memory UFO has no path, can't do 'include' either
                feapath = None

            # save generated features to a temp file if things go wrong...
            data = tobytes(self.features, encoding="utf-8")
            with NamedTemporaryFile(delete=False) as tmp:
                tmp.write(data)

            # if compilation succedes or fails for unrelated reasons, clean
            # up the temporary file
            try:
                addOpenTypeFeaturesFromString(self.outline, self.features,
                                              filename=feapath)
            except feaLib.error.FeatureLibError:
                logger.error("Compilation failed! Inspect temporary file: %r",
                             tmp.name)
                raise
            except:
                os.remove(tmp.name)
                raise
            else:
                os.remove(tmp.name)

    def postProcess(self):
        """Make post-compilation calculations.

        **This should not be called externally.** Subclasses
        may override this method if desired.
        """

        # only after compiling features can usMaxContext be calculated
        self.outline['OS/2'].usMaxContext = maxCtxFont(self.outline)
