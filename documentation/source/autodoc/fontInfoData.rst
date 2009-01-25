.. highlight:: python
.. module:: ufo2fdk

============
fontInfoData
============

.. automodule:: ufo2fdk.fontInfoData

Main Functions
^^^^^^^^^^^^^^

.. autofunction:: ufo2fdk.fontInfoData.getAttrWithFallback
.. autofunction:: ufo2fdk.fontInfoData.preflightInfo

Static Fallbacks
^^^^^^^^^^^^^^^^

Most of the fallbacks have static values. To see what is set for these, look at the source code's *staticFallbackData* definition.

Special Fallbacks
^^^^^^^^^^^^^^^^^

In some cases, the fallback values are dynamically generated from other data in the info object. These are handled internally with functions.

.. autofunction:: ufo2fdk.fontInfoData.styleMapFamilyNameFallback
.. autofunction:: ufo2fdk.fontInfoData.openTypeHeadCreatedFallback
.. autofunction:: ufo2fdk.fontInfoData.openTypeHheaAscenderFallback
.. autofunction:: ufo2fdk.fontInfoData.openTypeHheaDescenderFallback
.. autofunction:: ufo2fdk.fontInfoData.openTypeNameVersionFallback
.. autofunction:: ufo2fdk.fontInfoData.openTypeNameUniqueIDFallback
.. autofunction:: ufo2fdk.fontInfoData.openTypeNamePreferredFamilyNameFallback
.. autofunction:: ufo2fdk.fontInfoData.openTypeNamePreferredSubfamilyNameFallback
.. autofunction:: ufo2fdk.fontInfoData.openTypeNameCompatibleFullNameFallback
.. autofunction:: ufo2fdk.fontInfoData.openTypeOS2TypoAscenderFallback
.. autofunction:: ufo2fdk.fontInfoData.openTypeOS2TypoDescenderFallback
.. autofunction:: ufo2fdk.fontInfoData.openTypeOS2WinAscentFallback
.. autofunction:: ufo2fdk.fontInfoData.openTypeOS2WinDescentFallback
.. autofunction:: ufo2fdk.fontInfoData.postscriptFontNameFallback
.. autofunction:: ufo2fdk.fontInfoData.postscriptFullNameFallback
.. autofunction:: ufo2fdk.fontInfoData.postscriptSlantAngleFallback
.. autofunction:: ufo2fdk.fontInfoData.postscriptWeightNameFallback