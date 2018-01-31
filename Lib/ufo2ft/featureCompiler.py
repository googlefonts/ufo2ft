from __future__ import \
    print_function, division, absolute_import, unicode_literals
import logging
import os
from inspect import isclass
from tempfile import NamedTemporaryFile
from collections import deque

from fontTools import feaLib
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools import mtiLib
from fontTools.misc.py23 import UnicodeIO, tobytes, tounicode

from ufo2ft.featureWriters import DEFAULT_FEATURE_WRITERS
from ufo2ft.maxContextCalc import maxCtxFont
from ufo2ft.util import parseLayoutFeatures

logger = logging.getLogger(__name__)


class FeatureCompiler(object):
    """Generates OpenType feature tables for a UFO.

    *featureWriters* argument is a list that can contain either subclasses
    of BaseFeatureWriter or pre-initialized instances (or a mix of the two).
    Classes are initialized without arguments so will use default options.

    Features will be written by each feature writer in the given order.
    The default value is [KernFeatureWriter, MarkFeatureWriter].

    If you wish to exclude some features to be automatically generated,
    pass excludeAutoFeatures (set of str) with the tags to be excluded.

    If mtiFeatures is passed to the constructor, it should be a dictionary
    mapping feature table tags to MTI feature declarations for that table.
    These are passed to mtiLib for compilation.
    """

    def __init__(self, font, outline,
                 featureWriters=None,
                 excludeAutoFeatures=frozenset(),
                 mtiFeatures=None):
        self.font = font
        self.outline = outline

        if featureWriters is None:
            featureWriters = DEFAULT_FEATURE_WRITERS
        self.featureWriters = []
        supportedFeatures = set()
        for writer in featureWriters:
            if isclass(writer):
                writer = writer()
            self.featureWriters.append(writer)
            supportedFeatures.update(writer.supportedFeatures)

        self.autoFeatures = {tag for tag in supportedFeatures
                             if tag not in excludeAutoFeatures}

        # TODO: split MTI feature compiler to a separate class
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

        self.featureFile = parseLayoutFeatures(self.font)

        for writer in self.featureWriters:
            writer.write(self.font, self.featureFile,
                         features=self.autoFeatures)

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

        elif self.featureFile.statements:
            # stringify AST so we get correct line numbers in error messages
            featxt = self.featureFile.asFea()
            try:
                addOpenTypeFeaturesFromString(self.outline, featxt)
            except feaLib.error.FeatureLibError:
                # if compilation fails, create temporary file for inspection
                data = tobytes(self.features, encoding="utf-8")
                with NamedTemporaryFile(delete=False) as tmp:
                    tmp.write(data)
                logger.error("Compilation failed! Inspect temporary file: %r",
                             tmp.name)
                raise

    def postProcess(self):
        """Make post-compilation calculations.

        **This should not be called externally.** Subclasses
        may override this method if desired.
        """

        # only after compiling features can usMaxContext be calculated
        self.outline['OS/2'].usMaxContext = maxCtxFont(self.outline)
