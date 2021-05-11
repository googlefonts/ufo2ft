import logging
from textwrap import dedent

import pytest

from ufo2ft.featureCompiler import parseLayoutFeatures
from ufo2ft.featureWriters import GdefFeatureWriter

from . import FeatureWriterTest


@pytest.fixture
def testufo(FontClass):
    ufo = FontClass()
    ufo.newGlyph("a")
    ufo.newGlyph("f")
    ufo.newGlyph("f.component")
    ufo.newGlyph("i")
    liga = ufo.newGlyph("f_f_i")
    liga.appendAnchor({"name": "caret_2", "x": 400, "y": 0})
    liga.appendAnchor({"name": "caret_1", "x": 200, "y": 0})
    liga = ufo.newGlyph("f_i")
    liga.appendAnchor({"name": "caret_", "x": 200, "y": 0})
    ufo.newGlyph("acutecomb")
    ufo.newGlyph("tildecomb")

    ufo.lib["public.glyphOrder"] = [
        "a",
        "f",
        "f.component",
        "i",
        "f_f_i",
        "f_i",
        "acutecomb",
        "tildecomb",
    ]
    return ufo


class GdefFeatureWriterTest(FeatureWriterTest):

    FeatureWriter = GdefFeatureWriter

    @classmethod
    def writeGDEF(cls, ufo, **kwargs):
        writer = cls.FeatureWriter(**kwargs)
        feaFile = parseLayoutFeatures(ufo)
        if writer.write(ufo, feaFile):
            return feaFile

    def test_no_GDEF_no_openTypeCategories_in_font(self, testufo):
        newFea = self.writeGDEF(testufo)
        assert str(newFea) == dedent(
            """\
            table GDEF {
                LigatureCaretByPos f_f_i 200 400;
                LigatureCaretByPos f_i 200;
            } GDEF;
            """
        )

    def test_GDEF_in_font(self, testufo):
        testufo.features.text = dedent(
            """\
            table GDEF {
                GlyphClassDef [a], [], [acutecomb], [];
                LigatureCaretByPos f_i 300;
            } GDEF;
            """
        )
        assert self.writeGDEF(testufo) is None

    def test_openTypeCategories_in_font(self, testufo):
        testufo.lib["public.openTypeCategories"] = {
            "a": "base",
            "f.component": "component",
            "f_i": "ligature",
            "acutecomb": "mark",
        }
        newFea = self.writeGDEF(testufo)
        assert str(newFea) == dedent(
            """\
            table GDEF {
                GlyphClassDef [a], [f_i], [acutecomb], [f.component];
                LigatureCaretByPos f_f_i 200 400;
                LigatureCaretByPos f_i 200;
            } GDEF;
            """
        )

    def test_GDEF_and_openTypeCategories_in_font(self, testufo):
        testufo.lib["public.openTypeCategories"] = {
            "a": "base",
            "f.component": "component",
            "f_i": "ligature",
            "acutecomb": "mark",
        }
        testufo.features.text = dedent(
            """\
            table GDEF {
                 GlyphClassDef [i], [], [tildecomb], [];
                 LigatureCaretByPos f_i 100;
             } GDEF;
             """
        )
        assert self.writeGDEF(testufo) is None

    def test_GDEF_LigatureCarets_and_openTypeCategories_in_font(self, testufo):
        testufo.lib["public.openTypeCategories"] = {
            "a": "base",
            "f.component": "component",
            "f_i": "ligature",
            "acutecomb": "mark",
        }
        testufo.features.text = dedent(
            """\
            table GDEF {
                LigatureCaretByPos f_i 100;
            } GDEF;
             """
        )
        newFea = self.writeGDEF(testufo)
        assert str(newFea) == dedent(
            """\
            table GDEF {
                LigatureCaretByPos f_i 100;
                GlyphClassDef [a], [f_i], [acutecomb], [f.component];
            } GDEF;
            """
        )

    def test_GDEF_GlyphClassDef_and_carets_in_font(self, testufo):
        testufo.lib["public.openTypeCategories"] = {
            "a": "base",
            "f.component": "component",
            "f_i": "ligature",
            "acutecomb": "mark",
        }
        testufo.features.text = dedent(
            """\
            table GDEF {
                GlyphClassDef [], [], [acutecomb tildecomb], [];
            } GDEF;
             """
        )
        newFea = self.writeGDEF(testufo)
        assert str(newFea) == dedent(
            """\
            table GDEF {
                GlyphClassDef [], [], [acutecomb tildecomb], [];
                LigatureCaretByPos f_f_i 200 400;
                LigatureCaretByPos f_i 200;
            } GDEF;
            """
        )

    def test_mark_and_openTypeCategories_in_font(self, testufo):
        testufo.lib["public.openTypeCategories"] = {
            "a": "base",
            "f.component": "component",
            "f_f_i": "base",
            "f_i": "ligature",
            "acutecomb": "mark",
            "tildecomb": "component",
        }
        testufo.features.text = old = dedent(
            """\
            feature mark {
                markClass tildecomb <anchor 0 500> @TOP_MARKS;
                pos base a
                    <anchor 250 500> mark @TOP_MARKS;
                pos base f
                    <anchor 250 500> mark @TOP_MARKS;
                pos ligature f_f_i
                        <anchor 150 700> mark @TOP_MARKS
                    ligComponent
                        <anchor 450 700> mark @TOP_MARKS
                    ligComponent
                        <anchor 600 700> mark @TOP_MARKS;
            } mark;
            """
        )
        newFea = self.writeGDEF(testufo)
        assert str(newFea) == old + "\n" + dedent(
            """\
            table GDEF {
                GlyphClassDef [a f_f_i], [f_i], [acutecomb], [f.component tildecomb];
                LigatureCaretByPos f_f_i 200 400;
                LigatureCaretByPos f_i 200;
            } GDEF;
            """
        )

    def test_vertical_carets(self, testufo):
        vliga = testufo.newGlyph("vi_li_ga")
        vliga.appendAnchor({"name": "vcaret_1", "x": 0, "y": 100})
        vliga.appendAnchor({"name": "vcaret_2", "x": 0, "y": 200})
        vliga = testufo.newGlyph("vli_ga")
        vliga.appendAnchor({"name": "vcaret_", "x": 0, "y": 100})

        newFea = self.writeGDEF(testufo)
        assert str(newFea) == dedent(
            """\
            table GDEF {
                LigatureCaretByPos f_f_i 200 400;
                LigatureCaretByPos f_i 200;
                LigatureCaretByPos vi_li_ga 100 200;
                LigatureCaretByPos vli_ga 100;
            } GDEF;
            """
        )

    def test_getOpenTypeCategories_invalid(self, testufo, caplog):
        caplog.set_level(logging.WARNING)
        testufo.lib["public.openTypeCategories"] = {
            "a": "base",
            "f.component": "component",
            "f_f_i": "base",
            "f_i": "ligature",
            "acutecomb": "mark",
            "tildecomb": "components",
        }
        logger = "ufo2ft.featureWriters.gdefFeatureWriter.GdefFeatureWriter"
        with caplog.at_level(logging.WARNING, logger=logger):
            self.writeGDEF(testufo)

        assert len(caplog.records) == 1
        assert "The 'public.openTypeCategories' value of tildecomb in" in caplog.text
        assert "is 'components' when it should be" in caplog.text
