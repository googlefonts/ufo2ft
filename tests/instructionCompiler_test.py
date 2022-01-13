import pytest
from cu2qu.ufo import font_to_quadratic
from fontTools.pens.hashPointPen import HashPointPen
from fontTools.ttLib.ttFont import TTFont

from ufo2ft.instructionCompiler import InstructionCompiler
from .outlineCompiler_test import getpath


def get_hash_ufo(glyph, ufo):
    hash_pen = HashPointPen(glyph.width, ufo)
    glyph.drawPoints(hash_pen)
    return hash_pen.hash


def get_hash_ttf(glyph_name, ttf):
    aw, _lsb = ttf["hmtx"][glyph_name]
    gs = ttf.getGlyphSet()
    hash_pen = HashPointPen(aw, gs)
    ttf["glyf"][glyph_name].drawPoints(hash_pen, ttf["glyf"])
    return hash_pen.hash


@pytest.fixture
def quadfont():
    font = TTFont()
    font.importXML(getpath("Testfont.ttx"))
    return font


@pytest.fixture
def quaduforeversed(FontClass):
    font = FontClass(getpath("TestFont.ufo"))
    font_to_quadratic(font=font, reverse_direction=True)
    return font


@pytest.fixture
def testufo(FontClass):
    font = FontClass(getpath("TestFont.ufo"))
    del font.lib["public.postscriptNames"]
    return font


class InstructionCompilerTest:
    def test_check_glyph_hash_match(self, quaduforeversed, quadfont):
        glyph = quaduforeversed["a"]
        ufo_hash = get_hash_ufo(glyph, quaduforeversed)
        ttglyph = quadfont["glyf"]["uni0061"]

        result = InstructionCompiler()._check_glyph_hash(
            glyph=glyph,
            ttglyph=ttglyph,
            glyph_hash=ufo_hash,
            otf=quadfont,
            otf_glyph_name="uni0061",
        )
        assert result

    def test_check_glyph_hash_mismatch(self, testufo, quadfont):
        glyph = testufo["a"]
        ufo_hash = get_hash_ufo(glyph, testufo)
        ttglyph = quadfont["glyf"]["uni0061"]

        # The contour direction is reversed in testufo vs. quadfont, so the
        # hash should not match

        result = InstructionCompiler()._check_glyph_hash(
            glyph=glyph,
            ttglyph=ttglyph,
            glyph_hash=ufo_hash,
            otf=quadfont,
            otf_glyph_name="uni0061",
        )
        assert not result

    def test_check_glyph_hash_mismatch_width(self, quaduforeversed, quadfont):
        glyph = quaduforeversed["a"]

        # Modify the glyph width in the UFO to trigger the mismatch
        glyph.width += 10

        ufo_hash = get_hash_ufo(glyph, quaduforeversed)
        ttglyph = quadfont["glyf"]["uni0061"]

        result = InstructionCompiler()._check_glyph_hash(
            glyph=glyph,
            ttglyph=ttglyph,
            glyph_hash=ufo_hash,
            otf=quadfont,
            otf_glyph_name="uni0061",
        )
        assert not result

    def test_check_tt_data_format_match_str(self):
        result = InstructionCompiler()._check_tt_data_format(
            ttdata={"formatVersion": "1"},
            name="",
        )
        assert result is None

    def test_check_tt_data_format_type_error(self):
        with pytest.raises(
            TypeError,
            match="Illegal type 'int' instead of 'str' for formatVersion for instructions in location.",
        ):
            InstructionCompiler()._check_tt_data_format(
                ttdata={"formatVersion": 1},  # Spec requires a str
                name="location",
            )

    def test_check_tt_data_format_mismatch_str(self):
        with pytest.raises(
            NotImplementedError,
            match="Unknown formatVersion 1.5 for instructions in location.",
        ):
            InstructionCompiler()._check_tt_data_format(
                ttdata={"formatVersion": "1.5"},  # Maps to the correct int
                name="location",
            )
