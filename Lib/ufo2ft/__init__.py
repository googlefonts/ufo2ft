from __future__ import print_function, division, absolute_import

import os

from fontTools.misc.py23 import *

from ufo2ft.preProcessor import (
    OTFPreProcessor, TTFPreProcessor, TTFInterpolatablePreProcessor)
from ufo2ft.featureCompiler import FeatureCompiler
from ufo2ft.outlineCompiler import OutlineOTFCompiler, OutlineTTFCompiler
from ufo2ft.postProcessor import PostProcessor


__version__ = "1.1.0"


def compileOTF(ufo, preProcessorClass=OTFPreProcessor,
               outlineCompilerClass=OutlineOTFCompiler,
               featureCompilerClass=FeatureCompiler,
               kernWriterClass=None,  # deprecated
               markWriterClass=None,  # deprecated
               featureWriters=None,
               glyphOrder=None,
               useProductionNames=None,
               optimizeCFF=True,
               roundTolerance=None,
               removeOverlaps=False,
               inplace=False):
    """Create FontTools CFF font from a UFO.

    *removeOverlaps* performs a union operation on all the glyphs' contours.

    *optimizeCFF* sets whether the CFF table should be subroutinized.

    *roundTolerance* (float) controls the rounding of point coordinates.
      It is defined as the maximum absolute difference between the original
      float and the rounded integer value.
      By default, all floats are rounded to integer (tolerance 0.5); a value
      of 0 completely disables rounding; values in between only round floats
      which are close to their integral part within the tolerated range.

    *featureWriters* argument is a list of BaseFeatureWriter subclasses or
      pre-initialized instances. Features will be written by each feature
      writer in the given order. If featureWriters is None, the default
      feature writers [KernFeatureWriter, MarkFeatureWriter] are used.

    *useProductionNames* renames glyphs in TrueType 'post' or OpenType 'CFF '
      tables based on the 'public.postscriptNames' mapping in the UFO lib,
      if present. Otherwise, uniXXXX names are generated from the glyphs'
      unicode values. The default value (None) will first check if the UFO lib
      has the 'com.github.googlei18n.ufo2ft.useProductionNames' key. If this
      is missing or True (default), the glyphs are renamed. Set to False
      to keep the original names.
    """
    preProcessor = preProcessorClass(
        ufo, inplace=inplace, removeOverlaps=removeOverlaps)
    glyphSet = preProcessor.process()

    outlineCompiler = outlineCompilerClass(
        ufo, glyphSet=glyphSet, glyphOrder=glyphOrder,
        roundTolerance=roundTolerance)
    otf = outlineCompiler.compile()

    featureWriters = _replaceDeprecatedFeatureWriters(
        featureWriters, kernWriterClass, markWriterClass)
    featureCompiler = featureCompilerClass(
        ufo, otf, featureWriters=featureWriters,
        mtiFeatures=_getMtiFeatures(ufo))
    featureCompiler.compile()

    postProcessor = PostProcessor(otf, ufo)
    otf = postProcessor.process(useProductionNames, optimizeCFF)

    return otf


def compileTTF(ufo, preProcessorClass=TTFPreProcessor,
               outlineCompilerClass=OutlineTTFCompiler,
               featureCompilerClass=FeatureCompiler,
               kernWriterClass=None,  # deprecated
               markWriterClass=None,  # deprecated
               featureWriters=None,
               glyphOrder=None,
               useProductionNames=None,
               convertCubics=True,
               cubicConversionError=None,
               reverseDirection=True,
               removeOverlaps=False,
               inplace=False):
    """Create FontTools TrueType font from a UFO.

    *removeOverlaps* performs a union operation on all the glyphs' contours.

    *convertCubics* and *cubicConversionError* specify how the conversion from cubic
    to quadratic curves should be handled.
    """
    preProcessor = preProcessorClass(
        ufo, inplace=inplace,
        removeOverlaps=removeOverlaps,
        convertCubics=convertCubics,
        conversionError=cubicConversionError,
        reverseDirection=reverseDirection)
    glyphSet = preProcessor.process()

    outlineCompiler = outlineCompilerClass(
        ufo, glyphSet=glyphSet, glyphOrder=glyphOrder)
    otf = outlineCompiler.compile()

    featureWriters = _replaceDeprecatedFeatureWriters(
        featureWriters, kernWriterClass, markWriterClass)
    featureCompiler = featureCompilerClass(
        ufo, otf, featureWriters=featureWriters,
        mtiFeatures=_getMtiFeatures(ufo))
    featureCompiler.compile()

    postProcessor = PostProcessor(otf, ufo)
    otf = postProcessor.process(useProductionNames)

    return otf


def compileInterpolatableTTFs(ufos,
                              preProcessorClass=TTFInterpolatablePreProcessor,
                              outlineCompilerClass=OutlineTTFCompiler,
                              featureCompilerClass=FeatureCompiler,
                              featureWriters=None,
                              glyphOrder=None,
                              useProductionNames=None,
                              cubicConversionError=None,
                              reverseDirection=True,
                              inplace=False):
    """Create FontTools TrueType fonts from a list of UFOs with interpolatable
    outlines. Cubic curves are converted compatibly to quadratic curves using
    the Cu2Qu conversion algorithm.

    Return an iterator object that yields a TTFont instance for each UFO.
    """
    preProcessor = preProcessorClass(
        ufos, inplace=inplace,
        conversionError=cubicConversionError,
        reverseDirection=reverseDirection)
    glyphSets = preProcessor.process()

    for ufo, glyphSet in zip(ufos, glyphSets):
        outlineCompiler = outlineCompilerClass(
            ufo, glyphSet=glyphSet, glyphOrder=glyphOrder)
        ttf = outlineCompiler.compile()

        featureCompiler = featureCompilerClass(
            ufo, ttf, featureWriters=featureWriters,
            mtiFeatures=_getMtiFeatures(ufo))
        featureCompiler.compile()

        postProcessor = PostProcessor(ttf, ufo)
        ttf = postProcessor.process(useProductionNames)

        yield ttf


def _getMtiFeatures(ufo):
    features = {}
    prefix = "com.github.googlei18n.ufo2ft.mtiFeatures" + os.path.sep
    for fileName in ufo.data.fileNames:
        if fileName.startswith(prefix) and fileName.endswith(".mti"):
            content = tounicode(ufo.data[fileName], encoding="utf-8")
            features[fileName[len(prefix):-4]] = content
    return features if len(features) > 0 else None


def _deprecateArgument(arg, repl):
    import warnings
    warnings.warn("%r is deprecated; use %r instead" % (arg, repl),
                  category=UserWarning, stacklevel=3)


def _replaceDeprecatedFeatureWriters(featureWriters,
                                     kernWriterClass=None,
                                     markWriterClass=None):
    if not any([kernWriterClass, markWriterClass]):
        return featureWriters

    if featureWriters is not None:
        raise TypeError(
            "the new 'featureWriters' argument, and the old (deprecated) "
            "'kernWriterClass' and 'markWriterClass' arguments are mutually "
            "exclusive.")

    featureWriters = []

    if kernWriterClass is not None:
        _deprecateArgument("kernWriterClass", "featureWriters")
        featureWriters.append(kernWriterClass)
    else:
        from ufo2ft.featureWriters import KernFeatureWriter
        featureWriters.append(KernFeatureWriter)

    if markWriterClass is not None:
        _deprecateArgument("markWriterClass", "featureWriters")
        featureWriters.append(markWriterClass)
    else:
        from ufo2ft.featureWriters import MarkFeatureWriter
        featureWriters.append(MarkFeatureWriter)

    return featureWriters
