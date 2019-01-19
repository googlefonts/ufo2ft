from __future__ import print_function, division, absolute_import

import os
from enum import IntEnum

from fontTools.misc.py23 import *

from ufo2ft.preProcessor import (
    OTFPreProcessor,
    TTFPreProcessor,
    TTFInterpolatablePreProcessor,
)
from ufo2ft.featureCompiler import (
    FeatureCompiler,
    MtiFeatureCompiler,
    MTI_FEATURES_PREFIX,
)
from ufo2ft.outlineCompiler import OutlineOTFCompiler, OutlineTTFCompiler
from ufo2ft.postProcessor import PostProcessor
from ufo2ft.constants import SPARSE_TTF_MASTER_TABLES, SPARSE_OTF_MASTER_TABLES
import logging

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "0.0.0+unknown"


logger = logging.getLogger(__name__)


class CFFOptimization(IntEnum):
    NONE = 0
    SPECIALIZE = 1
    SUBROUTINIZE = 2


def compileOTF(
    ufo,
    preProcessorClass=OTFPreProcessor,
    outlineCompilerClass=OutlineOTFCompiler,
    featureCompilerClass=None,
    featureWriters=None,
    glyphOrder=None,
    useProductionNames=None,
    optimizeCFF=CFFOptimization.SUBROUTINIZE,
    roundTolerance=None,
    removeOverlaps=False,
    overlapsBackend=None,
    inplace=False,
    layerName=None,
    _tables=None,
):
    """Create FontTools CFF font from a UFO.

    *removeOverlaps* performs a union operation on all the glyphs' contours.

    *optimizeCFF* (int) defines whether the CFF charstrings should be
      specialized and subroutinized. By default both optimization are enabled.
      A value of 0 disables both; 1 only enables the specialization; 2 (default)
      does both specialization and subroutinization.

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

    **inplace** (bool) specifies whether the filters should modify the input
      UFO's glyphs, a copy should be made first.

    *layerName* specifies which layer should be compiled. When compiling something
    other than the default layer, feature compilation is skipped.
    """
    logger.info("Pre-processing glyphs")
    preProcessor = preProcessorClass(
        ufo,
        inplace=inplace,
        removeOverlaps=removeOverlaps,
        overlapsBackend=overlapsBackend,
        layerName=layerName,
    )
    glyphSet = preProcessor.process()

    logger.info("Building OpenType tables")
    optimizeCFF = CFFOptimization(optimizeCFF)
    outlineCompiler = outlineCompilerClass(
        ufo,
        glyphSet=glyphSet,
        glyphOrder=glyphOrder,
        roundTolerance=roundTolerance,
        optimizeCFF=optimizeCFF >= CFFOptimization.SPECIALIZE,
        tables=_tables,
    )
    otf = outlineCompiler.compile()

    # Only the default layer is likely to have all glyphs used in feature code.
    if layerName is None:
        compileFeatures(
            ufo,
            otf,
            glyphSet=glyphSet,
            featureWriters=featureWriters,
            featureCompilerClass=featureCompilerClass,
        )

    postProcessor = PostProcessor(otf, ufo, glyphSet=glyphSet)
    otf = postProcessor.process(
        useProductionNames,
        optimizeCFF=optimizeCFF >= CFFOptimization.SUBROUTINIZE,
    )

    return otf


def compileTTF(
    ufo,
    preProcessorClass=TTFPreProcessor,
    outlineCompilerClass=OutlineTTFCompiler,
    featureCompilerClass=None,
    featureWriters=None,
    glyphOrder=None,
    useProductionNames=None,
    convertCubics=True,
    cubicConversionError=None,
    reverseDirection=True,
    rememberCurveType=True,
    removeOverlaps=False,
    overlapsBackend=None,
    inplace=False,
    layerName=None,
):
    """Create FontTools TrueType font from a UFO.

    *removeOverlaps* performs a union operation on all the glyphs' contours.

    *convertCubics* and *cubicConversionError* specify how the conversion from cubic
    to quadratic curves should be handled.

    *layerName* specifies which layer should be compiled. When compiling something
    other than the default layer, feature compilation is skipped.
    """
    logger.info("Pre-processing glyphs")
    preProcessor = preProcessorClass(
        ufo,
        inplace=inplace,
        removeOverlaps=removeOverlaps,
        overlapsBackend=overlapsBackend,
        convertCubics=convertCubics,
        conversionError=cubicConversionError,
        reverseDirection=reverseDirection,
        rememberCurveType=rememberCurveType,
        layerName=layerName,
    )
    glyphSet = preProcessor.process()

    logger.info("Building OpenType tables")
    outlineCompiler = outlineCompilerClass(
        ufo, glyphSet=glyphSet, glyphOrder=glyphOrder
    )
    otf = outlineCompiler.compile()

    # Only the default layer is likely to have all glyphs used in feature code.
    if layerName is None:
        compileFeatures(
            ufo,
            otf,
            glyphSet=glyphSet,
            featureWriters=featureWriters,
            featureCompilerClass=featureCompilerClass,
        )

    postProcessor = PostProcessor(otf, ufo, glyphSet=glyphSet)
    otf = postProcessor.process(useProductionNames)

    return otf


def compileInterpolatableTTFs(
    ufos,
    preProcessorClass=TTFInterpolatablePreProcessor,
    outlineCompilerClass=OutlineTTFCompiler,
    featureCompilerClass=None,
    featureWriters=None,
    glyphOrder=None,
    useProductionNames=None,
    cubicConversionError=None,
    reverseDirection=True,
    inplace=False,
    layerNames=None,
):
    """Create FontTools TrueType fonts from a list of UFOs with interpolatable
    outlines. Cubic curves are converted compatibly to quadratic curves using
    the Cu2Qu conversion algorithm.

    Return an iterator object that yields a TTFont instance for each UFO.

    *layerNames* refers to the layer names to use glyphs from in the order of
    the UFOs in *ufos*. By default, this is a list of `[None]` times the number
    of UFOs, i.e. using the default layer from all the UFOs.

    When the layerName is not None for a given UFO, the corresponding TTFont object
    will contain only a minimum set of tables ("head", "hmtx", "glyf", "loca", "maxp",
    "post" and "vmtx"), and no OpenType layout tables.
    """
    from ufo2ft.util import _LazyFontName

    if layerNames is None:
        layerNames = [None] * len(ufos)
    assert len(ufos) == len(layerNames)

    logger.info("Pre-processing glyphs")
    preProcessor = preProcessorClass(
        ufos,
        inplace=inplace,
        conversionError=cubicConversionError,
        reverseDirection=reverseDirection,
        layerNames=layerNames,
    )
    glyphSets = preProcessor.process()

    for ufo, glyphSet, layerName in zip(ufos, glyphSets, layerNames):
        fontName = _LazyFontName(ufo)
        if layerName is not None:
            logger.info("Building OpenType tables for %s-%s", fontName, layerName)
        else:
            logger.info("Building OpenType tables for %s", fontName)

        outlineCompiler = outlineCompilerClass(
            ufo,
            glyphSet=glyphSet,
            glyphOrder=glyphOrder,
            tables=SPARSE_TTF_MASTER_TABLES if layerName else None,
        )
        ttf = outlineCompiler.compile()

        # Only the default layer is likely to have all glyphs used in feature
        # code.
        if layerName is None:
            compileFeatures(
                ufo,
                ttf,
                glyphSet=glyphSet,
                featureWriters=featureWriters,
                featureCompilerClass=featureCompilerClass,
            )

        postProcessor = PostProcessor(ttf, ufo, glyphSet=glyphSet)
        ttf = postProcessor.process(useProductionNames)

        if layerName is not None:
            # for sparse masters (i.e. containing only a subset of the glyphs), we
            # need to include the post table in order to store glyph names, so that
            # fontTools.varLib can interpolate glyphs with same name across masters.
            # However we want to prevent the underlinePosition/underlineThickness
            # fields in such sparse masters to be included when computing the deltas
            # for the MVAR table. Thus, we set them to this unlikely, limit value
            # (-36768) which is a signal varLib should ignore them when building MVAR.
            ttf["post"].underlinePosition = -0x8000
            ttf["post"].underlineThickness = -0x8000

        yield ttf


def compileInterpolatableTTFsFromDS(
    designSpaceDoc,
    preProcessorClass=TTFInterpolatablePreProcessor,
    outlineCompilerClass=OutlineTTFCompiler,
    featureCompilerClass=None,
    featureWriters=None,
    glyphOrder=None,
    useProductionNames=None,
    cubicConversionError=None,
    reverseDirection=True,
    inplace=False,
):
    """Create FontTools TrueType fonts from the DesignSpaceDocument UFO sources
    with interpolatable outlines. Cubic curves are converted compatibly to
    quadratic curves using the Cu2Qu conversion algorithm.

    The DesignSpaceDocument should contain SourceDescriptor objects with 'font'
    attribute set to an already loaded defcon.Font object (or compatible UFO
    Font class). If 'font' attribute is unset or None, an AttributeError exception
    is thrown.

    Return a copy of the DesignSpaceDocument object (or the same one if
    inplace=True) with the source's 'font' attribute set to the corresponding
    TTFont instance.

    For sources that have the 'layerName' attribute defined, the corresponding TTFont
    object will contain only a minimum set of tables ("head", "hmtx", "glyf", "loca",
    "maxp", "post" and "vmtx"), and no OpenType layout tables.
    """
    ufos, layerNames = [], []
    for source in designSpaceDoc.sources:
        if source.font is None:
            raise AttributeError(
                "designspace source '%s' is missing required 'font' attribute"
                % getattr(source, "name", "<Unknown>")
            )
        ufos.append(source.font)
        # 'layerName' is None for the default layer
        layerNames.append(source.layerName)

    ttfs = compileInterpolatableTTFs(
        ufos,
        preProcessorClass=preProcessorClass,
        outlineCompilerClass=outlineCompilerClass,
        featureCompilerClass=featureCompilerClass,
        featureWriters=featureWriters,
        glyphOrder=glyphOrder,
        useProductionNames=useProductionNames,
        cubicConversionError=cubicConversionError,
        reverseDirection=reverseDirection,
        inplace=inplace,
        layerNames=layerNames,
    )

    if inplace:
        result = designSpaceDoc
    else:
        # TODO try a more efficient copy method that doesn't involve (de)serializing
        result = designSpaceDoc.__class__.fromstring(designSpaceDoc.tostring())
    for source, ttf in zip(result.sources, ttfs):
        source.font = ttf
    return result


def compileInterpolatableOTFsFromDS(
    designSpaceDoc,
    preProcessorClass=OTFPreProcessor,
    outlineCompilerClass=OutlineOTFCompiler,
    featureCompilerClass=None,
    featureWriters=None,
    glyphOrder=None,
    useProductionNames=None,
    roundTolerance=None,
    inplace=False,
):
    """Create FontTools CFF fonts from the DesignSpaceDocument UFO sources
    with interpolatable outlines.

    Interpolatable means without subroutinization and specializer optimizations
    and no removal of overlaps.

    The DesignSpaceDocument should contain SourceDescriptor objects with 'font'
    attribute set to an already loaded defcon.Font object (or compatible UFO
    Font class). If 'font' attribute is unset or None, an AttributeError exception
    is thrown.

    Return a copy of the DesignSpaceDocument object (or the same one if
    inplace=True) with the source's 'font' attribute set to the corresponding
    TTFont instance.

    For sources that have the 'layerName' attribute defined, the corresponding TTFont
    object will contain only a minimum set of tables ("head", "hmtx", "CFF ", "maxp",
    "vmtx" and "VORG"), and no OpenType layout tables.
    """
    for source in designSpaceDoc.sources:
        if source.font is None:
            raise AttributeError(
                "designspace source '%s' is missing required 'font' attribute"
                % getattr(source, "name", "<Unknown>")
            )

    otfs = []
    for source in designSpaceDoc.sources:
        otfs.append(
            compileOTF(
                ufo=source.font,
                layerName=source.layerName,
                preProcessorClass=preProcessorClass,
                outlineCompilerClass=outlineCompilerClass,
                featureCompilerClass=featureCompilerClass,
                featureWriters=featureWriters,
                glyphOrder=glyphOrder,
                useProductionNames=useProductionNames,
                optimizeCFF=CFFOptimization.NONE,
                roundTolerance=roundTolerance,
                removeOverlaps=False,
                overlapsBackend=None,
                inplace=inplace,
                _tables=SPARSE_OTF_MASTER_TABLES if source.layerName else None,
            )
        )

    if inplace:
        result = designSpaceDoc
    else:
        # TODO try a more efficient copy method that doesn't involve (de)serializing
        result = designSpaceDoc.__class__.fromstring(designSpaceDoc.tostring())

    for source, otf in zip(result.sources, otfs):
        source.font = otf

    return result


def compileFeatures(
    ufo,
    ttFont=None,
    glyphSet=None,
    featureWriters=None,
    featureCompilerClass=None,
):
    """ Compile OpenType Layout features from `ufo` into FontTools OTL tables.
    If `ttFont` is None, a new TTFont object is created containing the new
    tables, else the provided `ttFont` is updated with the new tables.

    If no explicit `featureCompilerClass` is provided, the one used will
    depend on whether the ufo contains any MTI feature files in its 'data'
    directory (thus the `MTIFeatureCompiler` is used) or not (then the
    default FeatureCompiler for Adobe FDK features is used).
    """
    if featureCompilerClass is None:
        if any(
            fn.startswith(MTI_FEATURES_PREFIX) and fn.endswith(".mti")
            for fn in ufo.data.fileNames
        ):
            featureCompilerClass = MtiFeatureCompiler
        else:
            featureCompilerClass = FeatureCompiler
    featureCompiler = featureCompilerClass(
        ufo, ttFont, glyphSet=glyphSet, featureWriters=featureWriters
    )
    return featureCompiler.compile()
