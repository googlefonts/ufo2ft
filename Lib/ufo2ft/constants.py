from enum import IntEnum
from types import MappingProxyType


class CFFOptimization(IntEnum):
    NONE = 0
    SPECIALIZE = 1
    SUBROUTINIZE = 2


SPARSE_TTF_MASTER_TABLES = frozenset(
    ["glyf", "head", "hmtx", "loca", "maxp", "post", "vmtx", "cvt ", "fpgm", "prep"]
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
# sequence of [glyphs, clipBox], where 'glyphs' is in turn a sequence of
# glyph names, and 'clipBox' a 5- or 4-item sequence of numbers:
# Sequence[
#   Sequence[
#     Sequence[str, ...],  # glyph names
#     Union[
#       Sequence[float, float, float, float, float],  # variable box
#       Sequence[float, float, float, float],  # non-variable box
#     ]
#   ],
#   ...
# ]
COLR_CLIP_BOXES_KEY = UFO2FT_PREFIX + "colrClipBoxes"

OBJECT_LIBS_KEY = "public.objectLibs"
OPENTYPE_CATEGORIES_KEY = "public.openTypeCategories"
OPENTYPE_META_KEY = "public.openTypeMeta"
OPENTYPE_POST_UNDERLINE_POSITION_KEY = "public.openTypePostUnderlinePosition"
TRUETYPE_INSTRUCTIONS_KEY = "public.truetype.instructions"
TRUETYPE_METRICS_KEY = "public.truetype.useMyMetrics"
TRUETYPE_OVERLAP_KEY = "public.truetype.overlap"
TRUETYPE_ROUND_KEY = "public.truetype.roundOffsetToGrid"
UNICODE_VARIATION_SEQUENCES_KEY = "public.unicodeVariationSequences"

COMMON_SCRIPT = "Zyyy"

UNICODE_SCRIPT_ALIASES = MappingProxyType({"Hira": "Hrkt", "Kana": "Hrkt"})


# HarfBuzz passes Sinhala to the Indic shaper, while OpenType moved it to the USE shaper.

INDIC_SCRIPTS = [
    "Beng",  # Bengali
    "Deva",  # Devanagari
    "Gujr",  # Gujarati
    "Guru",  # Gurmukhi
    "Knda",  # Kannada
    "Mlym",  # Malayalam
    "Orya",  # Oriya
    "Sinh",  # Sinhala
    "Taml",  # Tamil
    "Telu",  # Telugu
]

USE_SCRIPTS = [
    # Correct as at Unicode 15.0
    "Adlm",  # Adlam
    "Ahom",  # Ahom
    "Bali",  # Balinese
    "Batk",  # Batak
    "Brah",  # Brahmi
    "Bugi",  # Buginese
    "Buhd",  # Buhid
    "Cakm",  # Chakma
    "Cham",  # Cham
    "Chrs",  # Chorasmian
    "Cpmn",  # Cypro Minoan
    "Diak",  # Dives Akuru
    "Dogr",  # Dogra
    "Dupl",  # Duployan
    "Egyp",  # Egyptian Hieroglyphs
    "Elym",  # Elymaic
    "Gong",  # Gunjala Gondi
    "Gonm",  # Masaram Gondi
    "Gran",  # Grantha
    "Hano",  # Hanunoo
    "Hmng",  # Pahawh Hmong
    "Hmnp",  # Nyiakeng Puachue Hmong
    "Java",  # Javanese
    "Kali",  # Kayah Li
    "Kawi",  # Kawi
    "Khar",  # Kharosthi
    "Khoj",  # Khojki
    "Kits",  # Khitan Small Script
    "Kthi",  # Kaithi
    "Lana",  # Tai Tham
    "Lepc",  # Lepcha
    "Limb",  # Limbu
    "Mahj",  # Mahajani
    "Maka",  # Makasar
    "Mand",  # Mandaic
    "Mani",  # Manichaean
    "Marc",  # Marchen
    "Medf",  # Medefaidrin
    "Modi",  # Modi
    "Mong",  # Mongolian
    "Mtei",  # Meetei Mayek
    "Mult",  # Multani
    "Nagm",  # Nag Mundari
    "Nand",  # Nandinagari
    "Newa",  # Newa
    "Nhks",  # Bhaiksuki
    "Nko ",  # Nko
    "Ougr",  # Old Uyghur
    "Phag",  # Phags Pa
    "Phlp",  # Psalter Pahlavi
    "Plrd",  # Miao
    "Rjng",  # Rejang
    "Rohg",  # Hanifi Rohingya
    "Saur",  # Saurashtra
    "Shrd",  # Sharada
    "Sidd",  # Siddham
    "Sind",  # Khudawadi
    "Sogd",  # Sogdian
    "Sogo",  # Old Sogdian
    "Soyo",  # Soyombo
    "Sund",  # Sundanese
    "Sylo",  # Syloti Nagri
    "Tagb",  # Tagbanwa
    "Takr",  # Takri
    "Tale",  # Tai Le
    "Tavt",  # Tai Viet
    "Tfng",  # Tifinagh
    "Tglg",  # Tagalog
    "Tibt",  # Tibetan
    "Tirh",  # Tirhuta
    "Tnsa",  # Tangsa
    "Toto",  # Toto
    "Vith",  # Vithkuqi
    "Wcho",  # Wancho
    "Yezi",  # Yezidi
    "Zanb",  # Zanabazar Square
]
