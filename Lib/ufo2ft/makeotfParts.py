from __future__ import print_function, division, absolute_import, unicode_literals

import logging
import os
import re

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools import mtiLib

from ufo2ft.maxContextCalc import maxCtxFont

logger = logging.getLogger(__name__)


class FeatureOTFCompiler(object):
    """Generates OpenType feature tables for a UFO.

    If mtiFeaFiles is passed to the constructor, it should be a dictionary
    mapping feature table tags to source files which should be compiled by
    mtiLib into that respective table.
    """

    def __init__(self, font, outline, kernWriter, markWriter, mtiFeaFiles=None):
        self.font = font
        self.outline = outline
        self.kernWriter = kernWriter
        self.markWriter = markWriter
        self.mtiFeaFiles = mtiFeaFiles
        self.setupAnchorPairs()

    def compile(self):
        """Compile the features.

        Starts by generating feature syntax for the kern, mark, and mkmk
        features. If they already exist, they will not be overwritten unless
        the compiler's `overwriteFeatures` attribute is True.
        """

        self.precompile()
        self.setupFile_features()
        self.setupFile_featureTables()

        # only after compiling features can usMaxContext be calculated
        self.outline['OS/2'].usMaxContext = maxCtxFont(self.outline)

    def precompile(self):
        """Set any attributes needed before compilation.

        **This should not be called externally.** Subclasses
        may override this method if desired.
        """

        self.overwriteFeatures = False

    def setupFile_features(self):
        """
        Make the features source file. If any tables
        or the kern feature are defined in the font's
        features, they will not be overwritten.

        **This should not be called externally.** Subclasses
        may override this method to handle the file creation
        in a different way if desired.
        """

        if self.mtiFeaFiles is not None:
            return

        kernRE = r"feature\s+kern\s+{.*?}\s+kern\s*;"
        markRE = re.compile(kernRE.replace("kern", "mark"), re.DOTALL)
        mkmkRE = re.compile(kernRE.replace("kern", "mkmk"), re.DOTALL)
        kernRE = re.compile(kernRE, re.DOTALL)

        existing = self.font.features.text or ""

        # build the GPOS features as necessary
        autoFeatures = {}
        if self.overwriteFeatures or not kernRE.search(existing):
            autoFeatures["kern"] = self.writeFeatures_kern()
        writeMark = self.overwriteFeatures or not markRE.search(existing)
        writeMkmk = self.overwriteFeatures or not mkmkRE.search(existing)
        if writeMark or writeMkmk:
            autoFeatures["mark"] = self.writeFeatures_mark(
                doMark=writeMark, doMkmk=writeMkmk)

        if self.overwriteFeatures:
            existing = kernRE.sub("", markRE.sub("", mkmkRE.sub("", existing)))

        # write the features
        features = [existing]
        for name, text in sorted(autoFeatures.items()):
            features.append(text)
        self.features = "\n\n".join(features)

    def writeFeatures_kern(self):
        """
        Write the kern feature to a string and return it.

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        writer = self.kernWriter(self.font)
        return writer.write()

    def writeFeatures_mark(self, doMark=True, doMkmk=True):
        """
        Write the mark and mkmk features to a string and return it.

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """

        writer = self.markWriter(
            self.font, self.anchorPairs, self.mkmkAnchorPairs,
            self.ligaAnchorPairs)
        return writer.write(doMark, doMkmk)

    def setupAnchorPairs(self):
        """
        Try to determine the base-accent anchor pairs to use in building the
        mark and mkmk features.

        **This should not be called externally.** Subclasses
        may override this method to set up the anchor pairs
        in a different way if desired.
        """

        self.anchorPairs = []
        self.ligaAnchorPairs = []

        anchorNames = set()
        for glyph in self.font:
            for anchor in glyph.anchors:
                if anchor.name is None:
                    logger.warning("Unnamed anchor discarded in %s", glyph.name)
                    continue
                anchorNames.add(anchor.name)

        for baseName in sorted(anchorNames):
            accentName = "_" + baseName
            if accentName in anchorNames:
                self.anchorPairs.append((baseName, accentName))

                ligaNames = []
                i = 1
                while True:
                    ligaName = "%s_%d" % (baseName, i)
                    if ligaName not in anchorNames:
                        break
                    ligaNames.append(ligaName)
                    i += 1
                if ligaNames:
                    self.ligaAnchorPairs.append((tuple(ligaNames), accentName))

        self.mkmkAnchorPairs = self.anchorPairs

    def setupFile_featureTables(self):
        """
        Compile and return OpenType feature tables from the source.
        Raises a FeaLibError if the feature compilation was unsuccessful.

        **This should not be called externally.** Subclasses
        may override this method to handle the table compilation
        in a different way if desired.
        """

        if self.mtiFeaFiles is not None:
            for tag, feapath in self.mtiFeaFiles.items():
                with open(feapath) as feafile:
                    table = mtiLib.build(feafile, self.outline)
                    assert table.tableTag == tag
                    self.outline[tag] = table

        elif self.features.strip():
            feapath = os.path.join(self.font.path, "features.fea") if self.font.path is not None else None
            addOpenTypeFeaturesFromString(self.outline, self.features,
                                          filename=feapath)
