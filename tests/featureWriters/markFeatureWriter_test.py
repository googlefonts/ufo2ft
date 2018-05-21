from __future__ import (
    print_function,
    division,
    absolute_import,
    unicode_literals,
)
from textwrap import dedent

from ufo2ft.featureCompiler import parseLayoutFeatures
from ufo2ft.featureWriters import MarkFeatureWriter, ast

import pytest
from . import FeatureWriterTest


@pytest.fixture
def testufo(FontClass):
    ufo = FontClass()
    ufo.newGlyph("a").appendAnchor({"name": "top", "x": 100, "y": 200})
    liga = ufo.newGlyph("f_i")
    liga.appendAnchor({"name": "top_1", "x": 100, "y": 500})
    liga.appendAnchor({"name": "top_2", "x": 600, "y": 500})
    ufo.newGlyph("acutecomb").appendAnchor(
        {"name": "_top", "x": 100, "y": 200}
    )
    accent = ufo.newGlyph("tildecomb")
    accent.appendAnchor({"name": "_top", "x": 100, "y": 200})
    accent.appendAnchor({"name": "top", "x": 100, "y": 300})
    return ufo


class MarkFeatureWriterTest(FeatureWriterTest):

    FeatureWriter = MarkFeatureWriter

    def test__makeMarkClassDefinitions_empty(self, FontClass):
        ufo = FontClass()
        ufo.newGlyph("a").appendAnchor({"name": "top", "x": 250, "y": 500})
        ufo.newGlyph("c").appendAnchor({"name": "bottom", "x": 250, "y": -100})
        ufo.newGlyph("grave").appendAnchor(
            {"name": "_top", "x": 100, "y": 200}
        )
        ufo.newGlyph("cedilla").appendAnchor(
            {"name": "_bottom", "x": 100, "y": 0}
        )
        writer = MarkFeatureWriter()
        feaFile = ast.FeatureFile()
        writer.setContext(ufo, feaFile)
        markClassDefs = writer._makeMarkClassDefinitions(feaFile.markClasses)

        assert len(feaFile.markClasses) == 2
        assert [str(mcd) for mcd in markClassDefs] == [
            "markClass cedilla <anchor 100 0> @MC_bottom;",
            "markClass grave <anchor 100 200> @MC_top;",
        ]

    def test__makeMarkClassDefinitions_non_empty(self, FontClass):
        ufo = FontClass()
        ufo.newGlyph("a").appendAnchor({"name": "top", "x": 250, "y": 500})
        ufo.newGlyph("c").appendAnchor({"name": "bottom", "x": 250, "y": -100})
        ufo.newGlyph("grave").appendAnchor(
            {"name": "_top", "x": 100, "y": 200}
        )
        ufo.newGlyph("cedilla").appendAnchor(
            {"name": "_bottom", "x": 100, "y": 0}
        )
        ufo.features.text = dedent(
            """\
            markClass cedilla <anchor 200 0> @MC_bottom;
            markClass grave <anchor 100 200> @MC_top;
            """
        )

        writer = MarkFeatureWriter()
        feaFile = parseLayoutFeatures(ufo)
        writer.setContext(ufo, feaFile)
        markClassDefs = writer._makeMarkClassDefinitions(feaFile.markClasses)

        assert len(markClassDefs) == 1
        assert len(feaFile.markClasses) == 3
        assert "MC_bottom" in feaFile.markClasses
        assert "MC_top" in feaFile.markClasses
        assert [str(mcd) for mcd in markClassDefs] == [
            "markClass cedilla <anchor 100 0> @MC_bottom_1;"
        ]

    def test_skip_empty_feature(self, FontClass):
        ufo = FontClass()
        ufo.newGlyph("a").appendAnchor({"name": "top", "x": 100, "y": 200})
        ufo.newGlyph("acutecomb").appendAnchor(
            {"name": "_top", "x": 100, "y": 200}
        )

        fea = str(self.writeFeatures(ufo))

        assert "feature mark" in fea
        assert "feature mkmk" not in fea

    def test_skip_existing_feature(self, testufo):
        testufo.features.text = dedent(
            """\
            markClass acutecomb <anchor 100 200> @MC_top;
            feature mark {
                lookup mark1 {
                    pos base a <anchor 100 200> mark @MC_top;
                } mark1;
            } mark;
            """
        )

        generated = self.writeFeatures(testufo)

        # only mkmk is generated, mark was already present
        assert str(generated) == dedent(
            """\
            markClass tildecomb <anchor 100 200> @MC_top;
            feature mkmk {
                lookup mkmk1 {
                    @mkmk1MkAttach = [acutecomb tildecomb];
                    lookupflag UseMarkFilteringSet @mkmk1MkAttach;
                    pos mark tildecomb <anchor 100 300> mark @MC_top;
                } mkmk1;

            } mkmk;
            """
        )

    def test_all_features(self, testufo):
        writer = MarkFeatureWriter()  # by default both mark + mkmk are built
        feaFile = ast.FeatureFile()
        assert writer.write(testufo, feaFile)

        assert str(feaFile) == dedent(
            """\
            markClass acutecomb <anchor 100 200> @MC_top;
            markClass tildecomb <anchor 100 200> @MC_top;
            feature mark {
                lookup mark1 {
                    pos base a <anchor 100 200> mark @MC_top;
                } mark1;

                lookup mark2liga1 {
                    pos ligature f_i <anchor 100 500> mark @MC_top
                        ligComponent <anchor 600 500> mark @MC_top;
                } mark2liga1;

            } mark;

            feature mkmk {
                lookup mkmk1 {
                    @mkmk1MkAttach = [acutecomb tildecomb];
                    lookupflag UseMarkFilteringSet @mkmk1MkAttach;
                    pos mark tildecomb <anchor 100 300> mark @MC_top;
                } mkmk1;

            } mkmk;
            """
        )

    def test_write_only_one(self, testufo):
        writer = MarkFeatureWriter(features=["mkmk"])  # only builds "mkmk"
        feaFile = ast.FeatureFile()
        assert writer.write(testufo, feaFile)
        fea = str(feaFile)

        assert "feature mark" not in fea
        assert "feature mkmk" in fea

        writer = MarkFeatureWriter(features=["mark"])  # only builds "mark"
        feaFile = ast.FeatureFile()
        assert writer.write(testufo, feaFile)
        fea = str(feaFile)

        assert "feature mark" in fea
        assert "feature mkmk" not in fea

    def test_predefined_anchor_lists(self, FontClass):
        """ Roboto uses some weird anchor naming scheme, see:
        https://github.com/google/roboto/blob/
            5700de83856781fa0c097a349e46dbaae5792cb0/
            scripts/lib/fontbuild/markFeature.py#L41-L47
        """

        class PrebuiltMarkFeatureWriter(MarkFeatureWriter):

            def setupAnchorPairs(self):
                self.context.anchorList = (
                    ("top", "_marktop"),
                    ("bottom", "_markbottom"),
                )
                self.context.mkmkAnchorList = (
                    ("mkmktop", "_marktop"),
                    ("mkmkbottom_acc", "_markbottom"),
                    ("", "_bottom"),
                )
                self.context.ligaAnchorList = (
                    (("top_1", "top_2"), "_marktop"),
                )

        ufo = FontClass()
        a = ufo.newGlyph("a")
        a.anchors = [
            {"name": "top", "x": 250, "y": 600},
            {"name": "bottom", "x": 250, "y": -100},
        ]
        f_i = ufo.newGlyph("f_i")
        f_i.anchors = [
            {"name": "top_1", "x": 200, "y": 700},
            {"name": "top_2", "x": 500, "y": 700},
        ]
        gravecomb = ufo.newGlyph("gravecomb")
        gravecomb.anchors = [
            {"name": "_marktop", "x": 160, "y": 780},
            {"name": "mkmktop", "x": 150, "y": 800},
            {"name": "mkmkbottom_acc", "x": 150, "y": 600},
        ]
        ufo.newGlyph("cedillacomb").appendAnchor(
            {"name": "_markbottom", "x": 200, "y": 0}
        )
        ufo.newGlyph("ogonekcomb").appendAnchor(
            {"name": "_bottom", "x": 180, "y": -10}
        )

        writer = PrebuiltMarkFeatureWriter()
        feaFile = ast.FeatureFile()
        writer.write(ufo, feaFile)

        assert str(feaFile) == dedent(
            """\
            markClass cedillacomb <anchor 200 0> @MC_markbottom;
            markClass gravecomb <anchor 160 780> @MC_marktop;
            feature mark {
                lookup mark1 {
                    pos base a <anchor 250 600> mark @MC_marktop;
                } mark1;

                lookup mark2 {
                    pos base a <anchor 250 -100> mark @MC_markbottom;
                } mark2;

                lookup mark2liga1 {
                    pos ligature f_i <anchor 200 700> mark @MC_marktop
                        ligComponent <anchor 500 700> mark @MC_marktop;
                } mark2liga1;

            } mark;

            feature mkmk {
                lookup mkmk1 {
                    @mkmk1MkAttach = [gravecomb];
                    lookupflag UseMarkFilteringSet @mkmk1MkAttach;
                    pos mark gravecomb <anchor 150 800> mark @MC_marktop;
                } mkmk1;

                lookup mkmk2 {
                    @mkmk2MkAttach = [cedillacomb gravecomb];
                    lookupflag UseMarkFilteringSet @mkmk2MkAttach;
                    pos mark gravecomb <anchor 150 600> mark @MC_markbottom;
                } mkmk2;

            } mkmk;
            """
        )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main(sys.argv))
