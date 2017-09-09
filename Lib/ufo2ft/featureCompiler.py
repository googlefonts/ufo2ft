from __future__ import \
    print_function, division, absolute_import, unicode_literals
import logging
import os
from fontTools import feaLib
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools import mtiLib

from ufo2ft.featureWriter.kernFeatureWriter import KernFeatureWriter
from ufo2ft.featureWriter.markFeatureWriter import MarkFeatureWriter
from ufo2ft.maxContextCalc import maxCtxFont

logger = logging.getLogger(__name__)


class FeatureCompiler(object):
    """Generates OpenType feature tables for a UFO.

    If mtiFeatures is passed to the constructor, it should be a dictionary
    mapping feature table tags to MTI feature declarations for that table.
    These are passed to mtiCompilation for compilation.
    """

    def __init__(self, font, outline, featureWriters=None, mtiFeatures=None):
        self.font = font
        self.outline = outline
        if featureWriters is None:
            featureWriters = (KernFeatureWriter(font), MarkFeatureWriter(font))
        self.featureWriters = featureWriters
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

        features = self._findLayoutFeatures()

        existing = self.font.features.text or ""

        # build features as necessary
        autoFeatures = {}
        # the current MarkFeatureWriter writes both mark and mkmk features
        # with shared markClass definitions; to prevent duplicate glyphs in
        # markClass, here we write the features only if none of them is alread
        # present.
        # TODO: Support updating pre-existing markClass definitions to allow
        # writing either mark or mkmk features indipendently from each other
        # https://github.com/googlei18n/fontmake/issues/319
        for featureWriter in self.featureWriters:
            doFeatures = []
            for feature in featureWriter.features:
                if feature not in features:
                    doFeatures.append(feature)
            if set(doFeatures) == set(featureWriter.features):
                autoFeatures[featureWriter.features] = featureWriter.write()

        # write the features
        features = [existing]
        for name, text in sorted(autoFeatures.items()):
            if text is None:
                continue
            features.append(text)
        self.features = "\n\n".join(features)

    def _findLayoutFeatures(self):
        """Returns what OpenType layout feature tags are present in the UFO."""
        if self.font.path is None:
            return set()
        feapath = os.path.join(self.font.path, "features.fea")
        if not os.path.exists(feapath):
            return set()
        glyphMap = self.outline.getReverseGlyphMap()
        parser = feaLib.parser.Parser(feapath, glyphMap=glyphMap)
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
            feapath = os.path.join(self.font.path, "features.fea") if self.font.path is not None else None
            addOpenTypeFeaturesFromString(self.outline, self.features,
                                          filename=feapath)

    def postProcess(self):
        """Make post-compilation calculations.

        **This should not be called externally.** Subclasses
        may override this method if desired.
        """

        # only after compiling features can usMaxContext be calculated
        self.outline['OS/2'].usMaxContext = maxCtxFont(self.outline)
