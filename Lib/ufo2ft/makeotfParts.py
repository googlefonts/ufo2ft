from __future__ import print_function, division, absolute_import, unicode_literals
import os
import re
import sys


class FeatureOTFCompiler(object):
    """Generates OpenType feature tables for a UFO."""

    def __init__(self, font, outline, kernWriter, markWriter):
        self.font = font
        self.outline = outline
        self.kernWriter = kernWriter
        self.markWriter = markWriter
        self.setupAnchorPairs()
        self.setupAliases()

    def compile(self):
        """Compile the features.

        Starts by generating feature syntax for the kern, mark, and mkmk
        features. If they already exist, they will not be overwritten unless
        the compiler's `overwriteFeatures` attribute is True.
        """

        self.precompile()
        self.setupFile_features()
        self.setupFile_featureTables()

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

        kernRE = r"feature\s+kern\s+{.*?}\s+kern\s*;"
        markRE = re.compile(kernRE.replace("kern", "mark"), re.DOTALL)
        mkmkRE = re.compile(kernRE.replace("kern", "mkmk"), re.DOTALL)
        kernRE = re.compile(kernRE, re.DOTALL)

        existing = self.font.features.text

        # build the GPOS features as necessary
        autoFeatures = {}
        if self.overwriteFeatures or not kernRE.search(existing):
            autoFeatures["kern"] = self.writeFeatures_kern()
        if self.overwriteFeatures or not markRE.search(existing):
            autoFeatures["mark"] = self.writeFeatures_mark()
        if self.overwriteFeatures or not mkmkRE.search(existing):
            autoFeatures["mkmk"] = self.writeFeatures_mkmk()

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

    def writeFeatures_mark(self):
        """
        Write the mark feature to a string and return it.

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        writer = self.markWriter(self.font, self.anchorPairs,
                                 aliases=self.aliases)
        return writer.write()

    def writeFeatures_mkmk(self):
        """
        Write the mkmk feature to a string and return it.

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        writer = self.markWriter(self.font, self.mkmkAnchorPairs,
                                 aliases=self.aliases, mkmk=True)
        return writer.write()

    def setupAnchorPairs(self):
        """
        Try to determine the base-accent anchor pairs to use in building the
        mark and mkmk features.

        **This should not be called externally.** Subclasses
        may override this method to set up the anchor pairs
        in a different way if desired.
        """

        self.anchorPairs = []
        anchorNames = set()
        for glyph in self.font:
            for anchor in glyph.anchors:
                if anchor.name is None:
                    print("warning: unnamed anchor discarded in", glyph.name)
                    continue
                anchorNames.add(anchor.name)
        for baseName in sorted(anchorNames):
            accentName = "_" + baseName
            if accentName in anchorNames:
                self.anchorPairs.append((baseName, accentName))

        self.mkmkAnchorPairs = []

    def setupAliases(self):
        """
        Initialize an empty list of glyph aliases, which would be used in
        building the mark and mkmk features.

        **This should not be called externally.** Subclasses
        may override this method to set up the glyph aliases
        in a different way if desired.
        """

        self.aliases = ()

    def setupFile_featureTables(self):
        """
        Compile and return OpenType feature tables from the source.
        Raises a FeaLibError if the feature compilation was unsuccessful.

        **This should not be called externally.** Subclasses
        may override this method to handle the table compilation
        in a different way if desired.
        """

        import tempfile
        from fontTools.feaLib.builder import addOpenTypeFeatures
        from fontTools.ttLib import TTFont

        if self.features.strip():
            fd, fea_path = tempfile.mkstemp()
            with open(fea_path, "w") as feafile:
                feafile.write(self.features)
            addOpenTypeFeatures(fea_path, self.outline)
            os.close(fd)
            os.remove(fea_path)
