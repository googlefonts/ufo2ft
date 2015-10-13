import re

from kernFeatureWriter import KernFeatureWriter
from markFeatureWriter import MarkFeatureWriter


class MakeOTFPartsCompiler:
    """Creates an outline binary, and generates missing feature definitions."""

    def __init__(self, font, path, outlineCompilerClass):
        self.font = font
        self.path = path
        self.log = []
        self.outlineCompilerClass = outlineCompilerClass
        self.setupAnchorPairs()

    def compile(self):
        """Compile the outline and features."""

        self.setupFile_outlineSource(self.path)
        self.setupFile_features()

    def setupFile_outlineSource(self, path):
        """
        Make the outline source file.

        **This should not be called externally.** Subclasses
        may override this method to handle the file creation
        in a different way if desired.
        """

        c = self.outlineCompilerClass(self.font, path)
        c.compile()
        self.log += c.log

    def setupFile_features(self, path):
        """
        Make the features source file. If any tables
        or the kern feature are defined in the font's
        features, they will not be overwritten.

        **This should not be called externally.** Subclasses
        may override this method to handle the file creation
        in a different way if desired.
        """

        existing = self.font.features.text

        # build the GPOS features as necessary
        autoFeatures = {}
        if not re.search(r"feature\s+kern\s+{", existing):
            autoFeatures["kern"] = self.writeFeatures_kern()
        if not re.search(r"feature\s+mark\s+{", existing):
            autoFeatures["mark"] = self.writeFeatures_mark()
        if not re.search(r"feature\s+mkmk\s+{", existing):
            autoFeatures["mkmk"] = self.writeFeatures_mkmk()

        # write the features
        features = [existing]
        for name, text in sorted(autoFeatures.items()):
            features.append(text)
        features = "\n\n".join(features)
        self.font.features.text = features

    def writeFeatures_kern(self):
        """
        Write the kern feature to a string and return it.

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        writer = KernFeatureWriter(self.font)
        return writer.write()

    def writeFeatures_mark(self):
        """
        Write the mark feature to a string and return it.

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        writer = MarkFeatureWriter(self.font, self.anchorPairs)
        return writer.write()

    def writeFeatures_mkmk(self):
        """
        Write the mkmk feature to a string and return it.

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        writer = MarkFeatureWriter(self.font, self.anchorPairs, mkmk=True)
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
                anchorNames.add(anchor.name)
        for baseName in sorted(anchorNames):
            accentName = "_" + baseName
            if accentName in anchorNames:
                self.anchorPairs.append((baseName, accentName))
