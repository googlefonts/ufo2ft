from .baseFeatureWriter import BaseFeatureWriter
from .kernFeatureWriter import KernFeatureWriter
from .markFeatureWriter import MarkFeatureWriter


def defaultFeatureWriters(font):
    return [KernFeatureWriter(font), MarkFeatureWriter(font)]
