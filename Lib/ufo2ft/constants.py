from __future__ import absolute_import, unicode_literals

SPARSE_TTF_MASTER_TABLES = frozenset(
    ["glyf", "head", "hmtx", "loca", "maxp", "post", "vmtx"]
)
SPARSE_OTF_MASTER_TABLES = frozenset(["CFF ", "VORG", "head", "hmtx", "maxp", "vmtx"])

UFO2FT_PREFIX = "com.github.googlei18n.ufo2ft."
GLYPHS_PREFIX = "com.schriftgestaltung."

USE_PRODUCTION_NAMES = UFO2FT_PREFIX + "useProductionNames"
GLYPHS_DONT_USE_PRODUCTION_NAMES = GLYPHS_PREFIX + "Don't use Production Names"
