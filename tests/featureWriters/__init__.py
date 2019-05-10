from __future__ import print_function, division, absolute_import, unicode_literals
from ufo2ft.featureCompiler import parseLayoutFeatures
from ufo2ft.featureWriters import ast


class FeatureWriterTest(object):

    # subclasses must override this
    FeatureWriter = None

    @classmethod
    def writeFeatures(cls, ufo, **kwargs):
        """ Return a new FeatureFile object containing only the newly
        generated statements, or None if no new feature was generated.
        """
        writer = cls.FeatureWriter(**kwargs)
        feaFile = parseLayoutFeatures(ufo)
        n = len(feaFile.statements)
        if writer.write(ufo, feaFile):
            new = ast.FeatureFile()
            new.statements = feaFile.statements[n:]
            return new
