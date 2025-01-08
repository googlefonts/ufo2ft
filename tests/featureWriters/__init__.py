from ufo2ft.featureCompiler import parseLayoutFeatures
from ufo2ft.featureWriters import ast


class FeatureWriterTest:
    # subclasses must override this
    FeatureWriter = None

    @classmethod
    def writeFeatures(cls, ufo, compiler=None, **kwargs):
        """Return a new FeatureFile object containing only the newly
        generated statements, or None if no new feature was generated.
        """
        writer = cls.FeatureWriter(**kwargs)
        feaFile = parseLayoutFeatures(ufo)
        old_statements = [st.asFea() for st in feaFile.statements]

        if writer.write(ufo, feaFile, compiler=compiler):
            new = ast.FeatureFile()

            for statement in feaFile.statements:
                if statement.asFea() not in old_statements:
                    new.statements.append(statement)
            return new
