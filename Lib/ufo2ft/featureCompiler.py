from __future__ import \
    print_function, division, absolute_import, unicode_literals
import logging
import os
from inspect import isclass
from tempfile import NamedTemporaryFile

from fontTools.misc.py23 import tobytes, tounicode
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.feaLib.error import FeatureLibError
from fontTools import mtiLib

from ufo2ft.featureWriters import (
    KernFeatureWriter, MarkFeatureWriter, loadFeatureWriters)
from ufo2ft.maxContextCalc import maxCtxFont
from ufo2ft.util import parseLayoutFeatures


logger = logging.getLogger(__name__)


class BaseFeatureCompiler(object):
    """Base class for generating OpenType features and compiling OpenType
    layout tables from these.
    """

    def __init__(self, ufo, ttFont, glyphSet=None, **kwargs):
        """
        Args:
          ufo: an object representing a UFO (defcon.Font or equivalent)
            containing the features source data.
          ttFont: a fontTools TTFont object where the generated OpenType
            tables are added.
          glyphSet: a (optional) dict containing pre-processed copies of
            the UFO glyphs.
        """
        self.ufo = ufo
        self.ttFont = ttFont
        if glyphSet is not None:
            assert set(ttFont.getGlyphOrder()) == glyphSet.keys()
            self.glyphSet = glyphSet
        else:
            self.glyphSet = ufo

    def setupFile_features(self):
        """
        Make the features source file.

        **This should not be called externally.** Subclasses
        may override this method.
        """
        raise NotImplementedError

    def setupFile_featureTables(self):
        """ Compile OpenType feature tables from the source.

        **This should not be called externally.** Subclasses
        must override this method.
        """
        raise NotImplementedError

    def postProcess(self):
        """Make post-compilation calculations.

        **This should not be called externally.** Subclasses
        can override this method.
        """
        # only after compiling features can usMaxContext be calculated
        self.ttFont['OS/2'].usMaxContext = maxCtxFont(self.ttFont)

    def compile(self):
        self.setupFile_features()
        self.setupFile_featureTables()
        self.postProcess()


class FeatureCompiler(BaseFeatureCompiler):
    """Generate automatic features and compile OpenType tables from Adobe
    Feature File stored in the UFO, using fontTools.feaLib as compiler.
    """

    defaultFeatureWriters = [
        KernFeatureWriter,
        MarkFeatureWriter,
    ]

    def __init__(self, ufo, ttFont,
                 glyphSet=None,
                 featureWriters=None,
                 **kwargs):
        """
        Args:
          featureWriters: a list of BaseFeatureWriter subclasses or
            pre-initialized instances. The default value (None) means that:
            - first, the UFO lib will be searched for a list of featureWriters
              under the key "com.github.googlei18n.ufo2ft.featureWriters"
              (see loadFeatureWriters).
            - if that is not found, the default list of writers will be used:
              [KernFeatureWriter, MarkFeatureWriter]. This generates "kern"
              (or "dist" for Indic scripts), "mark" and "mkmk" features.
            If the featureWriters list is empty, no automatic feature is
            generated and only pre-existing features are compiled.
        """
        BaseFeatureCompiler.__init__(self, ufo, ttFont, glyphSet)

        self.initFeatureWriters(featureWriters)

        if kwargs.get("mtiFeatures") is not None:
            import warnings
            warnings.warn("mtiFeatures argument is deprecated; "
                          "use MtiLibFeatureCompiler",
                          category=UserWarning, stacklevel=2)

    def initFeatureWriters(self, featureWriters=None):
        if featureWriters is None:
            featureWriters = loadFeatureWriters(self.ufo)
            if featureWriters is None:
                featureWriters = self.defaultFeatureWriters

        self.featureWriters = []
        for writer in featureWriters:
            if isclass(writer):
                writer = writer()
            self.featureWriters.append(writer)

    def setupFile_features(self):
        """
        Make the features source file.

        **This should not be called externally.** Subclasses
        may override this method to handle the file creation
        in a different way if desired.
        """
        if self.featureWriters:
            featureFile = parseLayoutFeatures(self.ufo)

            for writer in self.featureWriters:
                writer.write(self.ufo, featureFile, compiler=self)

            # stringify AST to get correct line numbers in error messages
            self.features = featureFile.asFea()
        else:
            # no featureWriters, simply read existing features' text
            self.features = tounicode(
                self.ufo.features.text or "", "utf-8")

    def setupFile_featureTables(self):
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
        try:
            addOpenTypeFeaturesFromString(self.ttFont, self.features,
                                          filename=path)
        except FeatureLibError:
            if path is None:
                # if compilation fails, create temporary file for inspection
                data = tobytes(self.features, encoding="utf-8")
                with NamedTemporaryFile(delete=False) as tmp:
                    tmp.write(data)
                logger.error("Compilation failed! Inspect temporary file: %r",
                             tmp.name)
            raise


# defcon lists UFO data filenames using platform-specific path separators.
# TODO change it to always return UNIX forward slashes
MTI_FEATURES_PREFIX = "com.github.googlei18n.ufo2ft.mtiFeatures" + os.path.sep


class MtiFeatureCompiler(BaseFeatureCompiler):
    """ Compile OpenType layout tables from MTI feature files using
    fontTools.mtiLib.
    """

    def setupFile_features(self):
        ufo = self.ufo
        features = {}
        prefixLength = len(MTI_FEATURES_PREFIX)
        for fn in ufo.data.fileNames:
            if fn.startswith(MTI_FEATURES_PREFIX) and fn.endswith(".mti"):
                content = tounicode(ufo.data[fn], encoding="utf-8")
                features[fn[prefixLength:-4]] = content
        self.mtiFeatures = features

    def setupFile_featureTables(self):
        for tag, features in self.mtiFeatures.items():
            table = mtiLib.build(features.splitlines(), self.ttFont)
            assert table.tableTag == tag
            self.ttFont[tag] = table


def getDefaultFeatureCompiler(ufo):
    """ If font has any MTI feature file return MtiFeatureCompiler,
    else return the default (FEA) FeatureCompiler.
    """
    if any(fn.startswith(MTI_FEATURES_PREFIX) and fn.endswith(".mti")
           for fn in ufo.data.fileNames):
        return MtiFeatureCompiler
    return FeatureCompiler
