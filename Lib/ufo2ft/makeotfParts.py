import re

from kernFeatureWriter import KernFeatureWriter
from markFeatureWriter import MarkFeatureWriter


class FeatureOTFCompiler:
    """Generates OpenType feature tables for a UFO."""

    def __init__(self, font, outline):
        self.font = font
        self.outline = outline
        self.setupAnchorPairs()

    def compile(self):
        """Compile the features."""

        self.setupFile_features()
        self.setupFile_featureTables()
        return self.feasrc

    def setupFile_features(self):
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
        self.features = "\n\n".join(features)

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

    def setupFile_featureTables(self):
        """
        Compile and return OpenType feature tables from the source.
        Raises a ValueError if the feature compilation was unsuccessful.

        **This should not be called externally.** Subclasses
        may override this method to handle the table compilation
        in a different way if desired.
        """

        import os
        import subprocess
        from fontTools.ttLib import TTFont

        fea_path = "tmp.fea"
        outline_path = "tmp1." + ("otf" if "CFF " in self.outline else "ttf")
        feasrc_path = outline_path.replace("1", "2")

        with open(fea_path, "w") as feafile:
            feafile.write(self.features)
        self.outline.save(outline_path)

        report = subprocess.check_output([
            "makeotf", "-o", feasrc_path, "-f", outline_path, "-ff", fea_path])
        os.remove(fea_path)
        os.remove(outline_path)

        print report
        if 'Done.' not in report:
            raise ValueError("Feature syntax compilation failed.")

        feasrc = TTFont(feasrc_path)
        self.feasrc = {table: feasrc[table] for table in ["GPOS", "GSUB"]}
        feasrc.close()
        os.remove(feasrc_path)
