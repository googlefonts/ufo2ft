from textwrap import dedent

import pytest

from ufo2ft.featureWriters.cursFeatureWriter import CursFeatureWriter

from . import FeatureWriterTest


@pytest.fixture
def testufo(FontClass):
    ufo = FontClass()
    ufo.newGlyph("a").appendAnchor({"name": "exit", "x": 100, "y": 200})
    glyph = ufo.newGlyph("b")
    glyph.appendAnchor({"name": "entry", "x": 0, "y": 200})
    glyph.appendAnchor({"name": "exit", "x": 111, "y": 200})
    ufo.newGlyph("c").appendAnchor({"name": "entry", "x": 100, "y": 200})
    return ufo


class CursFeatureWriterTest(FeatureWriterTest):
    FeatureWriter = CursFeatureWriter

    def test_curs_feature(self, testufo):
        generated = self.writeFeatures(testufo)

        assert str(generated) == dedent(
            """\
            feature curs {
                lookup curs {
                    lookupflag RightToLeft IgnoreMarks;
                    pos cursive a <anchor NULL> <anchor 100 200>;
                    pos cursive b <anchor 0 200> <anchor 111 200>;
                    pos cursive c <anchor 100 200> <anchor NULL>;
                } curs;

            } curs;
            """
        )

    def test_curs_feature_LTR(self, testufo):
        testufo["a"].unicode = ord("a")
        testufo["b"].unicode = ord("b")
        testufo["c"].unicode = ord("c")
        generated = self.writeFeatures(testufo)

        assert str(generated) == dedent(
            """\
            feature curs {
                lookup curs_ltr {
                    lookupflag IgnoreMarks;
                    pos cursive a <anchor NULL> <anchor 100 200>;
                    pos cursive b <anchor 0 200> <anchor 111 200>;
                    pos cursive c <anchor 100 200> <anchor NULL>;
                } curs_ltr;

            } curs;
            """
        )

    def test_curs_feature_mixed(self, testufo):
        testufo["a"].unicode = ord("a")
        testufo["b"].unicode = ord("b")
        testufo["c"].unicode = ord("c")
        glyph = testufo.newGlyph("a.swsh")
        glyph.appendAnchor({"name": "entry", "x": 100, "y": 200})
        glyph = testufo.newGlyph("alef")
        glyph.unicode = 0x0627
        glyph = testufo.newGlyph("alef.fina")
        glyph.appendAnchor({"name": "entry", "x": 300, "y": 10})
        glyph = testufo.newGlyph("meem")
        glyph.unicode = 0x0645
        glyph = testufo.newGlyph("meem.init")
        glyph.appendAnchor({"name": "exit", "x": 0, "y": 10})
        glyph = testufo.newGlyph("meem.medi")
        glyph.appendAnchor({"name": "entry", "x": 500, "y": 10})
        glyph.appendAnchor({"name": "exit", "x": 0, "y": 10})
        glyph = testufo.newGlyph("meem.fina")
        glyph.appendAnchor({"name": "entry", "x": 500, "y": 10})
        testufo.features.text = dedent(
            """\
            feature swsh {
                sub a by a.swsh;
            } swsh;
            feature init {
                sub meem by meem.init;
            } init;
            feature medi {
                sub meem by meem.medi;
            } medi;
            feature fina {
                sub alef by alef.fina;
                sub meem by meem.fina;
            } fina;
            """
        )
        testufo.lib["public.glyphOrder"] = [
            "a",
            "b",
            "c",
            "a.swsh",
            "alef",
            "alef.fina",
            "meem",
            "meem.init",
            "meem.medi",
            "meem.fina",
        ]
        generated = self.writeFeatures(testufo)

        assert str(generated) == dedent(
            """\
            feature curs {
                lookup curs_ltr {
                    lookupflag IgnoreMarks;
                    pos cursive a <anchor NULL> <anchor 100 200>;
                    pos cursive b <anchor 0 200> <anchor 111 200>;
                    pos cursive c <anchor 100 200> <anchor NULL>;
                    pos cursive a.swsh <anchor 100 200> <anchor NULL>;
                } curs_ltr;

                lookup curs_rtl {
                    lookupflag RightToLeft IgnoreMarks;
                    pos cursive alef.fina <anchor 300 10> <anchor NULL>;
                    pos cursive meem.init <anchor NULL> <anchor 0 10>;
                    pos cursive meem.medi <anchor 500 10> <anchor 0 10>;
                    pos cursive meem.fina <anchor 500 10> <anchor NULL>;
                } curs_rtl;

            } curs;
            """
        )

    def test_curs_feature_multiple_anchors(self, testufo):
        glyph = testufo.newGlyph("d")
        glyph.appendAnchor({"name": "entry.1", "x": 100, "y": 200})
        glyph.appendAnchor({"name": "exit.1", "x": 0, "y": 300})
        glyph = testufo.newGlyph("e")
        glyph.appendAnchor({"name": "entry.1", "x": 100, "y": 200})
        glyph = testufo.newGlyph("f")
        glyph.appendAnchor({"name": "exit.1", "x": 0, "y": 300})
        glyph.appendAnchor({"name": "exit.2", "x": 0, "y": 400})
        glyph = testufo.newGlyph("g")
        glyph.appendAnchor({"name": "entry.2", "x": 100, "y": 200})
        generated = self.writeFeatures(testufo)

        assert str(generated) == dedent(
            """\
            feature curs {
                lookup curs {
                    lookupflag RightToLeft IgnoreMarks;
                    pos cursive a <anchor NULL> <anchor 100 200>;
                    pos cursive b <anchor 0 200> <anchor 111 200>;
                    pos cursive c <anchor 100 200> <anchor NULL>;
                } curs;

                lookup curs_1 {
                    lookupflag RightToLeft IgnoreMarks;
                    pos cursive d <anchor 100 200> <anchor 0 300>;
                    pos cursive e <anchor 100 200> <anchor NULL>;
                    pos cursive f <anchor NULL> <anchor 0 300>;
                } curs_1;

                lookup curs_2 {
                    lookupflag RightToLeft IgnoreMarks;
                    pos cursive f <anchor NULL> <anchor 0 400>;
                    pos cursive g <anchor 100 200> <anchor NULL>;
                } curs_2;

            } curs;
            """
        )

    def test_curs_feature_multiple_anchors_LTR(self, testufo):
        testufo["a"].unicode = ord("a")
        testufo["b"].unicode = ord("b")
        testufo["c"].unicode = ord("c")
        glyph = testufo.newGlyph("d")
        glyph.unicode = ord("d")
        glyph.appendAnchor({"name": "entry.1", "x": 100, "y": 200})
        glyph.appendAnchor({"name": "exit.1", "x": 0, "y": 300})
        glyph = testufo.newGlyph("e")
        glyph.unicode = ord("e")
        glyph.appendAnchor({"name": "entry.1", "x": 100, "y": 200})
        glyph = testufo.newGlyph("f")
        glyph.unicode = ord("f")
        glyph.appendAnchor({"name": "exit.1", "x": 0, "y": 300})
        glyph.appendAnchor({"name": "exit.2", "x": 0, "y": 400})
        glyph = testufo.newGlyph("g")
        glyph.unicode = ord("g")
        glyph.appendAnchor({"name": "entry.2", "x": 100, "y": 200})
        generated = self.writeFeatures(testufo)

        assert str(generated) == dedent(
            """\
            feature curs {
                lookup curs_ltr {
                    lookupflag IgnoreMarks;
                    pos cursive a <anchor NULL> <anchor 100 200>;
                    pos cursive b <anchor 0 200> <anchor 111 200>;
                    pos cursive c <anchor 100 200> <anchor NULL>;
                } curs_ltr;

                lookup curs_1_ltr {
                    lookupflag IgnoreMarks;
                    pos cursive d <anchor 100 200> <anchor 0 300>;
                    pos cursive e <anchor 100 200> <anchor NULL>;
                    pos cursive f <anchor NULL> <anchor 0 300>;
                } curs_1_ltr;

                lookup curs_2_ltr {
                    lookupflag IgnoreMarks;
                    pos cursive f <anchor NULL> <anchor 0 400>;
                    pos cursive g <anchor 100 200> <anchor NULL>;
                } curs_2_ltr;

            } curs;
            """
        )

    def test_curs_feature_multiple_anchors_mixed(self, testufo):
        testufo["a"].unicode = ord("a")
        testufo["b"].unicode = ord("b")
        testufo["c"].unicode = ord("c")
        glyph = testufo.newGlyph("d")
        glyph.unicode = ord("d")
        glyph.appendAnchor({"name": "entry.1", "x": 100, "y": 200})
        glyph.appendAnchor({"name": "exit.1", "x": 0, "y": 300})
        glyph = testufo.newGlyph("e")
        glyph.unicode = ord("e")
        glyph.appendAnchor({"name": "entry.1", "x": 100, "y": 200})
        glyph = testufo.newGlyph("f")
        glyph.unicode = ord("f")
        glyph.appendAnchor({"name": "exit.1", "x": 0, "y": 300})
        glyph.appendAnchor({"name": "exit.2", "x": 0, "y": 400})
        glyph = testufo.newGlyph("g")
        glyph.unicode = ord("g")
        glyph.appendAnchor({"name": "entry.2", "x": 100, "y": 200})
        glyph = testufo.newGlyph("alef-ar")
        glyph.appendAnchor({"name": "entry", "x": 100, "y": 200})
        glyph.appendAnchor({"name": "exit", "x": 0, "y": 200})
        glyph.appendAnchor({"name": "exit.1", "x": 0, "y": 300})
        glyph = testufo.newGlyph("beh-ar")
        glyph.unicode = 0x0628
        glyph.appendAnchor({"name": "entry.1", "x": 100, "y": 200})
        glyph.appendAnchor({"name": "exit.1", "x": 0, "y": 200})
        glyph.appendAnchor({"name": "exit.2", "x": 0, "y": 100})
        glyph = testufo.newGlyph("hah-ar")
        glyph.unicode = 0x0647
        glyph.appendAnchor({"name": "entry", "x": 100, "y": 100})
        glyph.appendAnchor({"name": "entry.2", "x": 100, "y": 200})
        generated = self.writeFeatures(testufo)

        assert str(generated) == dedent(
            """\
            feature curs {
                lookup curs_ltr {
                    lookupflag IgnoreMarks;
                    pos cursive a <anchor NULL> <anchor 100 200>;
                    pos cursive b <anchor 0 200> <anchor 111 200>;
                    pos cursive c <anchor 100 200> <anchor NULL>;
                } curs_ltr;

                lookup curs_rtl {
                    lookupflag RightToLeft IgnoreMarks;
                    pos cursive alef-ar <anchor 100 200> <anchor 0 200>;
                    pos cursive hah-ar <anchor 100 100> <anchor NULL>;
                } curs_rtl;

                lookup curs_1_ltr {
                    lookupflag IgnoreMarks;
                    pos cursive d <anchor 100 200> <anchor 0 300>;
                    pos cursive e <anchor 100 200> <anchor NULL>;
                    pos cursive f <anchor NULL> <anchor 0 300>;
                } curs_1_ltr;

                lookup curs_1_rtl {
                    lookupflag RightToLeft IgnoreMarks;
                    pos cursive alef-ar <anchor NULL> <anchor 0 300>;
                    pos cursive beh-ar <anchor 100 200> <anchor 0 200>;
                } curs_1_rtl;

                lookup curs_2_ltr {
                    lookupflag IgnoreMarks;
                    pos cursive f <anchor NULL> <anchor 0 400>;
                    pos cursive g <anchor 100 200> <anchor NULL>;
                } curs_2_ltr;

                lookup curs_2_rtl {
                    lookupflag RightToLeft IgnoreMarks;
                    pos cursive beh-ar <anchor NULL> <anchor 0 100>;
                    pos cursive hah-ar <anchor 100 200> <anchor NULL>;
                } curs_2_rtl;

            } curs;
            """
        )

    def test_curs_feature_forced_RTL(self, testufo):
        for c in ("a", "b", "c"):
            g = testufo[c]
            g.unicode = ord(c)
            anchors = list(g.anchors)
            g.anchors = []
            for a in anchors:
                g.appendAnchor({"name": a.name + ".RTL", "x": a.x, "y": a.y})

        generated = self.writeFeatures(testufo)

        assert str(generated) == dedent(
            """\
                feature curs {
                    lookup curs_RTL {
                        lookupflag RightToLeft IgnoreMarks;
                        pos cursive a <anchor NULL> <anchor 100 200>;
                        pos cursive b <anchor 0 200> <anchor 111 200>;
                        pos cursive c <anchor 100 200> <anchor NULL>;
                    } curs_RTL;

                } curs;
                """
        )

    def test_curs_feature_forced_LTR(self, testufo):
        for n, u in (("a", 0x0627), ("b", 0x0628), ("c", 0x062C)):
            g = testufo[n]
            g.unicode = u
            anchors = list(g.anchors)
            g.anchors = []
            for a in anchors:
                g.appendAnchor({"name": a.name + ".LTR", "x": a.x, "y": a.y})

        generated = self.writeFeatures(testufo)

        assert str(generated) == dedent(
            """\
                feature curs {
                    lookup curs_LTR {
                        lookupflag IgnoreMarks;
                        pos cursive a <anchor NULL> <anchor 100 200>;
                        pos cursive b <anchor 0 200> <anchor 111 200>;
                        pos cursive c <anchor 100 200> <anchor NULL>;
                    } curs_LTR;

                } curs;
                """
        )

    def test_curs_feature_mixed_forced_direction(self, testufo):
        testufo["a"].unicode = ord("a")
        testufo["b"].unicode = ord("b")
        testufo["c"].unicode = ord("c")

        glyph = testufo.newGlyph("d")
        glyph.unicode = ord("d")
        glyph.appendAnchor({"name": "exit.RTL", "x": 110, "y": 210})

        glyph = testufo.newGlyph("e")
        glyph.unicode = ord("e")
        glyph.appendAnchor({"name": "entry.RTL", "x": 10, "y": 210})
        glyph.appendAnchor({"name": "exit.RTL", "x": 121, "y": 210})

        glyph = testufo.newGlyph("f")
        glyph.unicode = ord("f")
        glyph.appendAnchor({"name": "entry.RTL", "x": 110, "y": 210})

        glyph = testufo.newGlyph("alef")
        glyph.unicode = 0x0627
        glyph.appendAnchor({"name": "entry", "x": 100, "y": 200})

        glyph = testufo.newGlyph("beh")
        glyph.unicode = 0x0628
        glyph.appendAnchor({"name": "entry", "x": 0, "y": 200})
        glyph.appendAnchor({"name": "exit", "x": 111, "y": 200})

        glyph = testufo.newGlyph("jeem")
        glyph.unicode = 0x062C
        glyph.appendAnchor({"name": "entry", "x": 100, "y": 200})

        glyph = testufo.newGlyph("heh")
        glyph.unicode = 0x0647
        glyph.appendAnchor({"name": "entry.LTR", "x": 110, "y": 210})

        glyph = testufo.newGlyph("waw")
        glyph.unicode = 0x0648
        glyph.appendAnchor({"name": "exit.LTR", "x": 10, "y": 210})
        glyph.appendAnchor({"name": "exit.LTR", "x": 121, "y": 210})

        glyph = testufo.newGlyph("zain")
        glyph.unicode = 0x0632
        glyph.appendAnchor({"name": "entry.LTR", "x": 110, "y": 210})

        generated = self.writeFeatures(testufo)

        assert str(generated) == dedent(
            """\
                feature curs {
                    lookup curs_ltr {
                        lookupflag IgnoreMarks;
                        pos cursive a <anchor NULL> <anchor 100 200>;
                        pos cursive b <anchor 0 200> <anchor 111 200>;
                        pos cursive c <anchor 100 200> <anchor NULL>;
                    } curs_ltr;

                    lookup curs_rtl {
                        lookupflag RightToLeft IgnoreMarks;
                        pos cursive alef <anchor 100 200> <anchor NULL>;
                        pos cursive beh <anchor 0 200> <anchor 111 200>;
                        pos cursive jeem <anchor 100 200> <anchor NULL>;
                    } curs_rtl;

                    lookup curs_LTR {
                        lookupflag IgnoreMarks;
                        pos cursive heh <anchor 110 210> <anchor NULL>;
                        pos cursive waw <anchor NULL> <anchor 10 210>;
                        pos cursive zain <anchor 110 210> <anchor NULL>;
                    } curs_LTR;

                    lookup curs_RTL {
                        lookupflag RightToLeft IgnoreMarks;
                        pos cursive d <anchor NULL> <anchor 110 210>;
                        pos cursive e <anchor 10 210> <anchor 121 210>;
                        pos cursive f <anchor 110 210> <anchor NULL>;
                    } curs_RTL;

                } curs;
                """
        )
