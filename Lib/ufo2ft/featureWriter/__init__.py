from ufo2ft.featureWriter.kernFeatureWriter import KernFeatureWriter
from ufo2ft.featureWriter.markFeatureWriter import MarkFeatureWriter


def defaultFeatureWriters(font):
    return [KernFeatureWriter(font), MarkFeatureWriter(font)]
