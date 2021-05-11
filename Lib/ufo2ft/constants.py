SPARSE_TTF_MASTER_TABLES = frozenset(
    ["glyf", "head", "hmtx", "loca", "maxp", "post", "vmtx"]
)
SPARSE_OTF_MASTER_TABLES = frozenset(["CFF ", "VORG", "head", "hmtx", "maxp", "vmtx"])

UFO2FT_PREFIX = "com.github.googlei18n.ufo2ft."
GLYPHS_PREFIX = "com.schriftgestaltung."

FILTERS_KEY = UFO2FT_PREFIX + "filters"

MTI_FEATURES_PREFIX = UFO2FT_PREFIX + "mtiFeatures"

FEATURE_WRITERS_KEY = UFO2FT_PREFIX + "featureWriters"

USE_PRODUCTION_NAMES = UFO2FT_PREFIX + "useProductionNames"
GLYPHS_DONT_USE_PRODUCTION_NAMES = GLYPHS_PREFIX + "Don't use Production Names"
KEEP_GLYPH_NAMES = UFO2FT_PREFIX + "keepGlyphNames"

COLOR_LAYERS_KEY = UFO2FT_PREFIX + "colorLayers"
COLOR_PALETTES_KEY = UFO2FT_PREFIX + "colorPalettes"
COLOR_LAYER_MAPPING_KEY = UFO2FT_PREFIX + "colorLayerMapping"

OPENTYPE_CATEGORIES_KEY = "public.openTypeCategories"

UNICODE_VARIATION_SEQUENCES_KEY = "public.unicodeVariationSequences"

TRUETYPE_INSTRUCTIONS_KEY = "public.truetype.instructions"
TRUETYPE_ROUND_KEY = "public.truetype.roundOffsetToGrid"
TRUETYPE_METRICS_KEY = "public.truetype.useMyMetrics"
TRUETYPE_OVERLAP_KEY = "public.truetype.overlap"
OBJECT_LIBS_KEY = "public.objectLibs"
