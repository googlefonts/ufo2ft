import logging
import os
import re
from textwrap import dedent

import pytest

from ufo2ft.errors import InvalidFeaturesData
from ufo2ft.featureCompiler import parseLayoutFeatures
from ufo2ft.featureWriters import ast
from ufo2ft.featureWriters.markFeatureWriter import (
    MarkFeatureWriter,
    NamedAnchor,
    parseAnchorName,
)

from . import FeatureWriterTest


@pytest.fixture
def testufo(FontClass):
    ufo = FontClass()
    ufo.newGlyph("a").appendAnchor({"name": "top", "x": 100, "y": 200})
    liga = ufo.newGlyph("f_i")
    liga.appendAnchor({"name": "top_1", "x": 100, "y": 500})
    liga.appendAnchor({"name": "top_2", "x": 600, "y": 500})
    ufo.newGlyph("acutecomb").appendAnchor({"name": "_top", "x": 100, "y": 200})
    accent = ufo.newGlyph("tildecomb")
    accent.appendAnchor({"name": "_top", "x": 100, "y": 200})
    accent.appendAnchor({"name": "top", "x": 100, "y": 300})
    return ufo


@pytest.mark.parametrize(
    "input_expected",
    [
        ("top", (False, "top", None)),
        ("top_", (False, "top_", None)),
        ("top1", (False, "top1", None)),
        ("_bottom", (True, "bottom", None)),
        ("bottom_2", (False, "bottom", 2)),
        ("top_right_1", (False, "top_right", 1)),
    ],
)
def test_parseAnchorName(input_expected):
    anchorName, (isMark, key, number) = input_expected
    assert parseAnchorName(anchorName) == (isMark, key, number)


def test_parseAnchorName_invalid():
    with pytest.raises(ValueError, match="mark anchor cannot be numbered"):
        parseAnchorName("_top_2")
    with pytest.raises(ValueError, match="mark anchor key is nil"):
        parseAnchorName("_")


def test_NamedAnchor_invalid():
    with pytest.raises(ValueError, match="indexes must start from 1"):
        NamedAnchor("top_0", 1, 2)


def test_NamedAnchor_repr():
    expected = "NamedAnchor(name='top', x=1.0, y=2.0)"
    assert repr(NamedAnchor("top", 1.0, 2.0)) == expected


class MarkFeatureWriterTest(FeatureWriterTest):

    FeatureWriter = MarkFeatureWriter

    def test__makeMarkClassDefinitions_empty(self, FontClass):
        ufo = FontClass()
        ufo.newGlyph("a").appendAnchor({"name": "top", "x": 250, "y": 500})
        ufo.newGlyph("c").appendAnchor({"name": "bottom", "x": 250, "y": -100})
        ufo.newGlyph("grave").appendAnchor({"name": "_top", "x": 100, "y": 200})
        ufo.newGlyph("cedilla").appendAnchor({"name": "_bottom", "x": 100, "y": 0})
        writer = MarkFeatureWriter()
        feaFile = ast.FeatureFile()
        writer.setContext(ufo, feaFile)
        markClassDefs = writer._makeMarkClassDefinitions()

        assert len(feaFile.markClasses) == 2
        assert [str(mcd) for mcd in markClassDefs] == [
            "markClass cedilla <anchor 100 0> @MC_bottom;",
            "markClass grave <anchor 100 200> @MC_top;",
        ]

    def test__makeMarkClassDefinitions_non_empty(self, FontClass):
        ufo = FontClass()
        ufo.newGlyph("a").appendAnchor({"name": "top", "x": 250, "y": 500})
        ufo.newGlyph("c").appendAnchor({"name": "bottom", "x": 250, "y": -100})
        ufo.newGlyph("grave").appendAnchor({"name": "_top", "x": 100, "y": 200})
        ufo.newGlyph("cedilla").appendAnchor({"name": "_bottom", "x": 100, "y": 0})
        ufo.features.text = dedent(
            """\
            markClass cedilla <anchor 200 0> @MC_bottom;
            markClass grave <anchor 100 200> @MC_top;
            """
        )

        writer = MarkFeatureWriter()
        feaFile = parseLayoutFeatures(ufo)
        writer.setContext(ufo, feaFile)
        markClassDefs = writer._makeMarkClassDefinitions()

        assert len(markClassDefs) == 1
        assert len(feaFile.markClasses) == 3
        assert "MC_bottom" in feaFile.markClasses
        assert "MC_top" in feaFile.markClasses
        assert [str(mcd) for mcd in markClassDefs] == [
            "markClass cedilla <anchor 100 0> @MC_bottom_1;"
        ]

    def test_skip_empty_feature(self, FontClass):
        ufo = FontClass()
        assert not self.writeFeatures(ufo)

        ufo.newGlyph("a").appendAnchor({"name": "top", "x": 100, "y": 200})
        ufo.newGlyph("acutecomb").appendAnchor({"name": "_top", "x": 100, "y": 200})

        fea = str(self.writeFeatures(ufo))

        assert "feature mark" in fea
        assert "feature mkmk" not in fea

    def test_skip_unnamed_anchors(self, FontClass, caplog):
        caplog.set_level(logging.ERROR)

        ufo = FontClass()
        ufo.newGlyph("a").appendAnchor({"x": 100, "y": 200})

        writer = MarkFeatureWriter()
        feaFile = ast.FeatureFile()

        logger = "ufo2ft.featureWriters.markFeatureWriter.MarkFeatureWriter"
        with caplog.at_level(logging.WARNING, logger=logger):
            writer.setContext(ufo, feaFile)

        assert len(caplog.records) == 1
        assert "unnamed anchor discarded in glyph 'a'" in caplog.text

    def test_warn_duplicate_anchor_names(self, FontClass, caplog):
        caplog.set_level(logging.ERROR)

        ufo = FontClass()
        ufo.newGlyph("a").anchors = [
            {"name": "top", "x": 100, "y": 200},
            {"name": "top", "x": 200, "y": 300},
        ]

        writer = MarkFeatureWriter()
        feaFile = ast.FeatureFile()

        logger = "ufo2ft.featureWriters.markFeatureWriter.MarkFeatureWriter"
        with caplog.at_level(logging.WARNING, logger=logger):
            writer.setContext(ufo, feaFile)

        assert len(caplog.records) == 1
        assert "duplicate anchor 'top' in glyph 'a'" in caplog.text

    def test_warn_liga_anchor_in_mark_glyph(self, testufo, caplog):
        caplog.set_level(logging.ERROR)

        testufo.newGlyph("ogonekcomb").anchors = [
            {"name": "_top", "x": 200, "y": -40},
            {"name": "top_1", "x": 200, "y": 450},  # should not be there!
        ]

        logger = "ufo2ft.featureWriters.markFeatureWriter.MarkFeatureWriter"
        with caplog.at_level(logging.WARNING, logger=logger):
            _ = self.writeFeatures(testufo)

        assert len(caplog.records) == 1
        assert "invalid ligature anchor 'top_1' in mark glyph" in caplog.text

    def test_ligature_NULL_anchor(self, testufo):
        testufo.newGlyph("f_f_foo").anchors = [
            {"name": "top_1", "x": 250, "y": 600},
            {"name": "top_2", "x": 500, "y": 600},
            {"name": "_3", "x": 0, "y": 0},  # this becomes <anchor NULL>
        ]
        generated = self.writeFeatures(testufo)

        assert re.search(r"ligComponent\s+<anchor NULL>", str(generated))

    def test_skip_existing_feature(self, testufo):
        testufo.features.text = dedent(
            """\
            markClass acutecomb <anchor 100 200> @MC_top;
            feature mark {
                lookup mark1 {
                    pos base a
                        <anchor 100 200> mark @MC_top;
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
                lookup mark2mark_top {
                    @MFS_mark2mark_top = [acutecomb tildecomb];
                    lookupflag UseMarkFilteringSet @MFS_mark2mark_top;
                    pos mark tildecomb
                        <anchor 100 300> mark @MC_top;
                } mark2mark_top;

            } mkmk;
            """
        )

    def test_append_feature(self, testufo):
        testufo.features.text = dedent(
            """\
            markClass acutecomb <anchor 100 200> @MC_top;
            feature mark {
                lookup mark1 {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark1;
            } mark;
            """
        )

        generated = self.writeFeatures(testufo, mode="append")

        assert str(generated) == dedent(
            """\
            markClass tildecomb <anchor 100 200> @MC_top;

            feature mark {
                lookup mark2base {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark2base;

                lookup mark2liga {
                    pos ligature f_i
                            <anchor 100 500> mark @MC_top
                        ligComponent
                            <anchor 600 500> mark @MC_top;
                } mark2liga;

            } mark;

            feature mkmk {
                lookup mark2mark_top {
                    @MFS_mark2mark_top = [acutecomb tildecomb];
                    lookupflag UseMarkFilteringSet @MFS_mark2mark_top;
                    pos mark tildecomb
                        <anchor 100 300> mark @MC_top;
                } mark2mark_top;

            } mkmk;
            """
        )

    def test_insert_comment_before(self, testufo):
        writer = MarkFeatureWriter()
        testufo.features.text = dedent(
            """\
            markClass acutecomb <anchor 100 200> @MC_top;
            feature mark {
                #
                # Automatic Code
                #
                lookup mark1 {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark1;
            } mark;
            """
        )
        feaFile = parseLayoutFeatures(testufo)

        assert writer.write(testufo, feaFile)

        assert str(feaFile) == dedent(
            """\
            markClass acutecomb <anchor 100 200> @MC_top;
            markClass tildecomb <anchor 100 200> @MC_top;

            feature mark {
                lookup mark2base {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark2base;

                lookup mark2liga {
                    pos ligature f_i
                            <anchor 100 500> mark @MC_top
                        ligComponent
                            <anchor 600 500> mark @MC_top;
                } mark2liga;

            } mark;

            feature mark {
                #
                #
                lookup mark1 {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark1;

            } mark;

            feature mkmk {
                lookup mark2mark_top {
                    @MFS_mark2mark_top = [acutecomb tildecomb];
                    lookupflag UseMarkFilteringSet @MFS_mark2mark_top;
                    pos mark tildecomb
                        <anchor 100 300> mark @MC_top;
                } mark2mark_top;

            } mkmk;
            """
        )

        # test append mode ignores insert marker
        generated = self.writeFeatures(testufo, mode="append")
        assert str(generated) == dedent(
            """\
            markClass tildecomb <anchor 100 200> @MC_top;

            feature mark {
                lookup mark2base {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark2base;

                lookup mark2liga {
                    pos ligature f_i
                            <anchor 100 500> mark @MC_top
                        ligComponent
                            <anchor 600 500> mark @MC_top;
                } mark2liga;

            } mark;

            feature mkmk {
                lookup mark2mark_top {
                    @MFS_mark2mark_top = [acutecomb tildecomb];
                    lookupflag UseMarkFilteringSet @MFS_mark2mark_top;
                    pos mark tildecomb
                        <anchor 100 300> mark @MC_top;
                } mark2mark_top;

            } mkmk;
            """
        )

    def test_insert_comment_after(self, testufo):
        writer = MarkFeatureWriter()
        testufo.features.text = dedent(
            """\
            markClass acutecomb <anchor 100 200> @MC_top;
            feature mark {
                lookup mark1 {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark1;
                #
                # Automatic Code
                #
            } mark;
            """
        )
        feaFile = parseLayoutFeatures(testufo)

        assert writer.write(testufo, feaFile)

        assert str(feaFile) == dedent(
            """\
            markClass acutecomb <anchor 100 200> @MC_top;
            feature mark {
                lookup mark1 {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark1;

                #
                #
            } mark;

            markClass tildecomb <anchor 100 200> @MC_top;

            feature mark {
                lookup mark2base {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark2base;

                lookup mark2liga {
                    pos ligature f_i
                            <anchor 100 500> mark @MC_top
                        ligComponent
                            <anchor 600 500> mark @MC_top;
                } mark2liga;

            } mark;

            feature mkmk {
                lookup mark2mark_top {
                    @MFS_mark2mark_top = [acutecomb tildecomb];
                    lookupflag UseMarkFilteringSet @MFS_mark2mark_top;
                    pos mark tildecomb
                        <anchor 100 300> mark @MC_top;
                } mark2mark_top;

            } mkmk;
            """
        )

        # test append mode ignores insert marker
        generated = self.writeFeatures(testufo, mode="append")
        assert str(generated) == dedent(
            """\
            markClass tildecomb <anchor 100 200> @MC_top;

            feature mark {
                lookup mark2base {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark2base;

                lookup mark2liga {
                    pos ligature f_i
                            <anchor 100 500> mark @MC_top
                        ligComponent
                            <anchor 600 500> mark @MC_top;
                } mark2liga;

            } mark;

            feature mkmk {
                lookup mark2mark_top {
                    @MFS_mark2mark_top = [acutecomb tildecomb];
                    lookupflag UseMarkFilteringSet @MFS_mark2mark_top;
                    pos mark tildecomb
                        <anchor 100 300> mark @MC_top;
                } mark2mark_top;

            } mkmk;
            """
        )

    def test_insert_comment_middle(self, testufo):
        writer = MarkFeatureWriter()
        testufo.features.text = dedent(
            """\
            markClass acutecomb <anchor 100 200> @MC_top;
            feature mark {
                lookup mark1 {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark1;
                #
                # Automatic Code
                #
                lookup mark2 {
                    pos base a
                        <anchor 150 250> mark @MC_top;
                } mark2;
            } mark;
            """
        )
        feaFile = parseLayoutFeatures(testufo)

        with pytest.raises(
            InvalidFeaturesData,
            match="Insert marker has rules before and after, feature mark "
            "cannot be inserted.",
        ):
            writer.write(testufo, feaFile)

        # test append mode ignores insert marker
        generated = self.writeFeatures(testufo, mode="append")
        assert str(generated) == dedent(
            """\
            markClass tildecomb <anchor 100 200> @MC_top;

            feature mark {
                lookup mark2base {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark2base;

                lookup mark2liga {
                    pos ligature f_i
                            <anchor 100 500> mark @MC_top
                        ligComponent
                            <anchor 600 500> mark @MC_top;
                } mark2liga;

            } mark;

            feature mkmk {
                lookup mark2mark_top {
                    @MFS_mark2mark_top = [acutecomb tildecomb];
                    lookupflag UseMarkFilteringSet @MFS_mark2mark_top;
                    pos mark tildecomb
                        <anchor 100 300> mark @MC_top;
                } mark2mark_top;

            } mkmk;
            """
        )

    def test_insert_comment_outside_block(self, testufo):
        writer = MarkFeatureWriter()
        testufo.features.text = dedent(
            """\
            #
            # Automatic Code
            #
            """
        )
        feaFile = parseLayoutFeatures(testufo)

        assert writer.write(testufo, feaFile)

        testufo.features.text = dedent(
            """\
            #
            # Automatic Code
            #
            markClass acutecomb <anchor 100 200> @MC_top;
            feature mark {
                lookup mark1 {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark1;

            } mark;
            """
        )
        feaFile = parseLayoutFeatures(testufo)

        assert writer.write(testufo, feaFile)

        # test append mode
        writer = MarkFeatureWriter(mode="append")
        assert writer.write(testufo, feaFile)

    def test_defs_and_lookups_first(self, testufo):
        testufo.newGlyph("circumflexcomb")
        writer = MarkFeatureWriter()
        testufo.features.text = dedent(
            """\
            feature mkmk {
                # Automatic Code
                # Move acutecomb down and right if preceded by circumflexcomb
                lookup move_acutecomb {
                    lookupflag UseMarkFilteringSet [acutecomb circumflexcomb];
                    pos circumflexcomb acutecomb' <0 20 0 20>;
                } move_acutecomb;
            } mkmk;
            """
        )
        feaFile = parseLayoutFeatures(testufo)

        assert writer.write(testufo, feaFile)

        assert str(feaFile) == dedent(
            """\
            markClass acutecomb <anchor 100 200> @MC_top;
            markClass tildecomb <anchor 100 200> @MC_top;

            feature mark {
                lookup mark2base {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark2base;

                lookup mark2liga {
                    pos ligature f_i
                            <anchor 100 500> mark @MC_top
                        ligComponent
                            <anchor 600 500> mark @MC_top;
                } mark2liga;

            } mark;

            feature mkmk {
                lookup mark2mark_top {
                    @MFS_mark2mark_top = [acutecomb tildecomb];
                    lookupflag UseMarkFilteringSet @MFS_mark2mark_top;
                    pos mark tildecomb
                        <anchor 100 300> mark @MC_top;
                } mark2mark_top;

            } mkmk;

            feature mkmk {
                # Move acutecomb down and right if preceded by circumflexcomb
                lookup move_acutecomb {
                    lookupflag UseMarkFilteringSet [acutecomb circumflexcomb];
                    pos circumflexcomb acutecomb' <0 20 0 20>;
                } move_acutecomb;

            } mkmk;
            """
        )

    def test_mark_mkmk_features(self, testufo):
        writer = MarkFeatureWriter()  # by default both mark + mkmk are built
        feaFile = ast.FeatureFile()
        assert writer.write(testufo, feaFile)

        assert str(feaFile) == dedent(
            """\
            markClass acutecomb <anchor 100 200> @MC_top;
            markClass tildecomb <anchor 100 200> @MC_top;

            feature mark {
                lookup mark2base {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark2base;

                lookup mark2liga {
                    pos ligature f_i
                            <anchor 100 500> mark @MC_top
                        ligComponent
                            <anchor 600 500> mark @MC_top;
                } mark2liga;

            } mark;

            feature mkmk {
                lookup mark2mark_top {
                    @MFS_mark2mark_top = [acutecomb tildecomb];
                    lookupflag UseMarkFilteringSet @MFS_mark2mark_top;
                    pos mark tildecomb
                        <anchor 100 300> mark @MC_top;
                } mark2mark_top;

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
        """Roboto uses some weird anchor naming scheme, see:
        https://github.com/google/roboto/blob/
            5700de83856781fa0c097a349e46dbaae5792cb0/
            scripts/lib/fontbuild/markFeature.py#L41-L47
        """

        class RobotoMarkFeatureWriter(MarkFeatureWriter):
            class NamedAnchor(NamedAnchor):
                markPrefix = "_mark"
                ignoreRE = "(^mkmk|_acc$)"

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
        ufo.newGlyph("ogonekcomb").appendAnchor({"name": "_bottom", "x": 180, "y": -10})

        writer = RobotoMarkFeatureWriter()
        feaFile = ast.FeatureFile()
        writer.write(ufo, feaFile)

        assert str(feaFile) == dedent(
            """\
            markClass cedillacomb <anchor 200 0> @MC_markbottom;
            markClass gravecomb <anchor 160 780> @MC_marktop;

            feature mark {
                lookup mark2base {
                    pos base a
                        <anchor 250 -100> mark @MC_markbottom
                        <anchor 250 600> mark @MC_marktop;
                } mark2base;

                lookup mark2liga {
                    pos ligature f_i
                            <anchor 200 700> mark @MC_marktop
                        ligComponent
                            <anchor 500 700> mark @MC_marktop;
                } mark2liga;

            } mark;

            feature mkmk {
                lookup mark2mark_bottom {
                    @MFS_mark2mark_bottom = [cedillacomb gravecomb];
                    lookupflag UseMarkFilteringSet @MFS_mark2mark_bottom;
                    pos mark gravecomb
                        <anchor 150 600> mark @MC_markbottom;
                } mark2mark_bottom;

                lookup mark2mark_top {
                    @MFS_mark2mark_top = [gravecomb];
                    lookupflag UseMarkFilteringSet @MFS_mark2mark_top;
                    pos mark gravecomb
                        <anchor 150 800> mark @MC_marktop;
                } mark2mark_top;

            } mkmk;
            """  # noqa: B950
        )

    def test_abvm_blwm_features(self, FontClass):
        ufo = FontClass()
        ufo.info.unitsPerEm = 1000

        dottedCircle = ufo.newGlyph("dottedCircle")
        dottedCircle.unicode = 0x25CC
        dottedCircle.anchors = [
            {"name": "top", "x": 297, "y": 552},
            {"name": "topright", "x": 491, "y": 458},
            {"name": "bottom", "x": 297, "y": 0},
        ]

        nukta = ufo.newGlyph("nukta-kannada")
        nukta.unicode = 0x0CBC
        nukta.appendAnchor({"name": "_bottom", "x": 0, "y": 0})

        nukta = ufo.newGlyph("candrabindu-kannada")
        nukta.unicode = 0x0C81
        nukta.appendAnchor({"name": "_top", "x": 0, "y": 547})

        halant = ufo.newGlyph("halant-kannada")
        halant.unicode = 0x0CCD
        halant.appendAnchor({"name": "_topright", "x": -456, "y": 460})

        ka = ufo.newGlyph("ka-kannada")
        ka.unicode = 0x0C95
        ka.appendAnchor({"name": "bottom", "x": 290, "y": 0})

        ka_base = ufo.newGlyph("ka-kannada.base")
        ka_base.appendAnchor({"name": "top", "x": 291, "y": 547})
        ka_base.appendAnchor({"name": "topright", "x": 391, "y": 460})
        ka_base.appendAnchor({"name": "bottom", "x": 290, "y": 0})

        ufo.features.text = dedent(
            """\
            languagesystem DFLT dflt;
            languagesystem knda dflt;
            languagesystem knd2 dflt;

            feature psts {
                sub ka-kannada' halant-kannada by ka-kannada.base;
            } psts;
            """
        )
        generated = self.writeFeatures(ufo)

        assert str(generated) == dedent(
            """\
            markClass nukta-kannada <anchor 0 0> @MC_bottom;
            markClass candrabindu-kannada <anchor 0 547> @MC_top;
            markClass halant-kannada <anchor -456 460> @MC_topright;

            feature abvm {
                lookup abvm_mark2base {
                    pos base ka-kannada.base
                        <anchor 291 547> mark @MC_top
                        <anchor 391 460> mark @MC_topright;
                } abvm_mark2base;

            } abvm;

            feature blwm {
                lookup blwm_mark2base {
                    pos base ka-kannada
                        <anchor 290 0> mark @MC_bottom;
                    pos base ka-kannada.base
                        <anchor 290 0> mark @MC_bottom;
                } blwm_mark2base;

            } blwm;

            feature mark {
                lookup mark2base {
                    pos base dottedCircle
                        <anchor 297 0> mark @MC_bottom
                        <anchor 297 552> mark @MC_top
                        <anchor 491 458> mark @MC_topright;
                } mark2base;

            } mark;
            """  # noqa: B950
        )

    def test_all_features(self, testufo):
        ufo = testufo
        ufo.info.unitsPerEm = 1000

        ufo.newGlyph("cedillacomb").anchors = [
            {"name": "_bottom", "x": 10, "y": -5},
            {"name": "bottom", "x": 20, "y": -309},
        ]
        ufo.newGlyph("c").appendAnchor({"name": "bottom", "x": 240, "y": 0})

        dottedCircle = ufo.newGlyph("dottedCircle")
        dottedCircle.unicode = 0x25CC
        dottedCircle.anchors = [
            {"name": "top", "x": 297, "y": 552},
            {"name": "bottom", "x": 297, "y": 0},
            {"name": "bar", "x": 491, "y": 458},
        ]

        # too lazy, couldn't come up with a real-word example :/
        foocomb = ufo.newGlyph("foocomb")
        foocomb.unicode = 0x0B85
        foocomb.anchors = [
            {"name": "_top", "x": 100, "y": 40},
            {"name": "top", "x": 100, "y": 190},
        ]
        barcomb = ufo.newGlyph("barcomb")
        barcomb.unicode = 0x0B86
        barcomb.anchors = [
            {"name": "_bar", "x": 100, "y": 40},
            {"name": "bar", "x": 100, "y": 440.1},
        ]
        bazcomb = ufo.newGlyph("bazcomb")
        bazcomb.unicode = 0x0B87
        bazcomb.anchors = [
            {"name": "_bottom", "x": 90, "y": 320},
            {"name": "bottom", "x": 100, "y": -34},
        ]
        foo_bar_baz = ufo.newGlyph("foo_bar_baz")
        foo_bar_baz.unicode = 0x0B88
        foo_bar_baz.anchors = [
            {"name": "top_1", "x": 100, "y": 500},
            {"name": "bottom_1", "x": 100, "y": 10},
            {"name": "_2", "x": 600, "y": 500},
            {"name": "top_3", "x": 1000, "y": 500},
            {"name": "bar_3", "x": 1100, "y": 499},  # below half UPEM
        ]
        bar_foo = ufo.newGlyph("bar_foo")
        bar_foo.unicode = 0x0B89
        # sequence doesn't start from 1, the first is implied NULL anchor
        bar_foo.anchors = [{"name": "top_2", "x": 600, "y": 501}]

        testufo.glyphOrder = [
            "a",
            "f_i",
            "acutecomb",
            "tildecomb",
            "cedillacomb",
            "c",
            "dottedCircle",
            "foocomb",
            "barcomb",
            "bazcomb",
            "foo_bar_baz",
            "bar_foo",
        ]
        generated = self.writeFeatures(testufo)

        assert str(generated) == dedent(
            """\
            markClass barcomb <anchor 100 40> @MC_bar;
            markClass cedillacomb <anchor 10 -5> @MC_bottom;
            markClass bazcomb <anchor 90 320> @MC_bottom;
            markClass acutecomb <anchor 100 200> @MC_top;
            markClass tildecomb <anchor 100 200> @MC_top;
            markClass foocomb <anchor 100 40> @MC_top;

            feature abvm {
                lookup abvm_mark2liga {
                    pos ligature foo_bar_baz
                            <anchor 100 500> mark @MC_top
                        ligComponent
                            <anchor NULL>
                        ligComponent
                            <anchor 1000 500> mark @MC_top;
                    pos ligature bar_foo
                            <anchor NULL>
                        ligComponent
                            <anchor 600 501> mark @MC_top;
                } abvm_mark2liga;

                lookup abvm_mark2mark_top {
                    @MFS_abvm_mark2mark_top = [foocomb];
                    lookupflag UseMarkFilteringSet @MFS_abvm_mark2mark_top;
                    pos mark foocomb
                        <anchor 100 190> mark @MC_top;
                } abvm_mark2mark_top;

            } abvm;

            feature blwm {
                lookup blwm_mark2liga {
                    pos ligature foo_bar_baz
                            <anchor 100 10> mark @MC_bottom
                        ligComponent
                            <anchor NULL>
                        ligComponent
                            <anchor 1100 499> mark @MC_bar;
                } blwm_mark2liga;

                lookup blwm_mark2mark_bar {
                    @MFS_blwm_mark2mark_bar = [barcomb];
                    lookupflag UseMarkFilteringSet @MFS_blwm_mark2mark_bar;
                    pos mark barcomb
                        <anchor 100 440> mark @MC_bar;
                } blwm_mark2mark_bar;

                lookup blwm_mark2mark_bottom {
                    @MFS_blwm_mark2mark_bottom = [bazcomb];
                    lookupflag UseMarkFilteringSet @MFS_blwm_mark2mark_bottom;
                    pos mark bazcomb
                        <anchor 100 -34> mark @MC_bottom;
                } blwm_mark2mark_bottom;

            } blwm;

            feature mark {
                lookup mark2base {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                    pos base c
                        <anchor 240 0> mark @MC_bottom;
                    pos base dottedCircle
                        <anchor 491 458> mark @MC_bar
                        <anchor 297 0> mark @MC_bottom
                        <anchor 297 552> mark @MC_top;
                } mark2base;

                lookup mark2liga {
                    pos ligature f_i
                            <anchor 100 500> mark @MC_top
                        ligComponent
                            <anchor 600 500> mark @MC_top;
                } mark2liga;

            } mark;

            feature mkmk {
                lookup mark2mark_bottom {
                    @MFS_mark2mark_bottom = [cedillacomb];
                    lookupflag UseMarkFilteringSet @MFS_mark2mark_bottom;
                    pos mark cedillacomb
                        <anchor 20 -309> mark @MC_bottom;
                } mark2mark_bottom;

                lookup mark2mark_top {
                    @MFS_mark2mark_top = [acutecomb tildecomb];
                    lookupflag UseMarkFilteringSet @MFS_mark2mark_top;
                    pos mark tildecomb
                        <anchor 100 300> mark @MC_top;
                } mark2mark_top;

            } mkmk;
            """  # noqa: B950
        )

    def test_mark_mkmk_features_with_GDEF(self, testufo):
        D = testufo.newGlyph("D")
        D.anchors = [
            {"name": "top", "x": 300, "y": 700},
            {"name": "center", "x": 320, "y": 360},
        ]
        # these glyphs have compatible anchors but since they not listed in
        # the GDEF groups, they won't be included in the mark/mkmk feature
        testufo.newGlyph("Alpha").appendAnchor({"name": "topleft", "x": -10, "y": 400})
        testufo.newGlyph("psili").appendAnchor({"name": "_topleft", "x": 0, "y": 50})
        dotaccentcomb = testufo.newGlyph("dotaccentcomb")
        # this mark glyph has more than one mark anchor, and both will be
        # generated. Since the two mark anchors cannot cohabit in the same
        # mark lookup, two lookups will be generated.
        dotaccentcomb.anchors = [
            {"name": "_center", "x": 0, "y": 0},
            {"name": "_top", "x": 0, "y": 0},
            {"name": "top", "x": 0, "y": 300},
        ]
        testufo.features.text = dedent(
            """\
            @Bases = [a D];
            @Marks = [acutecomb tildecomb dotaccentcomb];
            table GDEF {
                GlyphClassDef @Bases, [f_i], @Marks, ;
            } GDEF;
            """
        )
        testufo.glyphOrder = [
            "Alpha",
            "D",
            "a",
            "acutecomb",
            "dotaccentcomb",
            "f_i",
            "psili",
            "tildecomb",
        ]

        generated = self.writeFeatures(testufo)

        assert str(generated) == dedent(
            """\
            markClass dotaccentcomb <anchor 0 0> @MC_center;
            markClass acutecomb <anchor 100 200> @MC_top;
            markClass dotaccentcomb <anchor 0 0> @MC_top;
            markClass tildecomb <anchor 100 200> @MC_top;

            feature mark {
                lookup mark2base {
                    pos base D
                        <anchor 320 360> mark @MC_center;
                } mark2base;

                lookup mark2base_1 {
                    pos base D
                        <anchor 300 700> mark @MC_top;
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark2base_1;

                lookup mark2liga {
                    pos ligature f_i
                            <anchor 100 500> mark @MC_top
                        ligComponent
                            <anchor 600 500> mark @MC_top;
                } mark2liga;

            } mark;

            feature mkmk {
                lookup mark2mark_top {
                    @MFS_mark2mark_top = [acutecomb dotaccentcomb tildecomb];
                    lookupflag UseMarkFilteringSet @MFS_mark2mark_top;
                    pos mark dotaccentcomb
                        <anchor 0 300> mark @MC_top;
                    pos mark tildecomb
                        <anchor 100 300> mark @MC_top;
                } mark2mark_top;

            } mkmk;
            """
        )

    def test_mark_mkmk_features_with_GDEF_and_openTypeCategories(self, testufo):
        # this glyph has compatible anchors and has an openTypeCategories "base"
        # value
        D = testufo.newGlyph("D")
        D.anchors = [
            {"name": "top", "x": 300, "y": 700},
            {"name": "center", "x": 320, "y": 360},
        ]
        # these glyphs have compatible anchors but since they not listed in
        # the GDEF groups, they won't be included in the mark/mkmk feature
        testufo.newGlyph("Alpha").appendAnchor({"name": "topleft", "x": -10, "y": 400})
        testufo.newGlyph("psili").appendAnchor({"name": "_topleft", "x": 0, "y": 50})
        dotaccentcomb = testufo.newGlyph("dotaccentcomb")
        # this mark glyph has more than one mark anchor, and both will be
        # generated. Since the two mark anchors cannot cohabit in the same
        # mark lookup, two lookups will be generated.
        dotaccentcomb.anchors = [
            {"name": "_center", "x": 0, "y": 0},
            {"name": "_top", "x": 0, "y": 0},
            {"name": "top", "x": 0, "y": 300},
        ]
        # will be ignored because in GDEF table below
        testufo.lib["public.openTypeCategories"] = {
            "D": "base",
            "dotaccentcomb": "mark",
            "tildecomb": "base",
        }
        testufo.features.text = dedent(
            """\
            @Bases = [a];
            @Marks = [acutecomb tildecomb];
            table GDEF {
                GlyphClassDef @Bases, [f_i], @Marks, ;
            } GDEF;
            """
        )
        testufo.glyphOrder = [
            "Alpha",
            "D",
            "a",
            "acutecomb",
            "dotaccentcomb",
            "f_i",
            "psili",
            "tildecomb",
        ]

        generated = self.writeFeatures(testufo)

        assert str(generated) == dedent(
            """\
            markClass acutecomb <anchor 100 200> @MC_top;
            markClass tildecomb <anchor 100 200> @MC_top;

            feature mark {
                lookup mark2base {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark2base;

                lookup mark2liga {
                    pos ligature f_i
                            <anchor 100 500> mark @MC_top
                        ligComponent
                            <anchor 600 500> mark @MC_top;
                } mark2liga;

            } mark;

            feature mkmk {
                lookup mark2mark_top {
                    @MFS_mark2mark_top = [acutecomb tildecomb];
                    lookupflag UseMarkFilteringSet @MFS_mark2mark_top;
                    pos mark tildecomb
                        <anchor 100 300> mark @MC_top;
                } mark2mark_top;

            } mkmk;
            """
        )

    def test_multiple_anchor_classes_base(self, FontClass):
        dirname = os.path.dirname(os.path.dirname(__file__))
        fontPath = os.path.join(dirname, "data", "MultipleAnchorClasses.ufo")
        testufo = FontClass(fontPath)
        generated = self.writeFeatures(testufo)

        assert str(generated) == dedent(
            """\
            markClass acutecomb <anchor -175 589> @MC_topA;
            markClass acutecomb <anchor -175 572> @MC_topE;

            feature mark {
                lookup mark2base {
                    pos base a
                        <anchor 515 581> mark @MC_topA;
                } mark2base;

                lookup mark2base_1 {
                    pos base e
                        <anchor -21 396> mark @MC_topE;
                } mark2base_1;

            } mark;
            """
        )

    def test_multiple_anchor_classes_liga(self, FontClass):
        ufo = FontClass()
        liga = ufo.newGlyph("f_i")
        liga.appendAnchor({"name": "top_1", "x": 100, "y": 500})
        liga.appendAnchor({"name": "top_2", "x": 600, "y": 500})
        ligaOther = ufo.newGlyph("f_f")
        ligaOther.appendAnchor({"name": "topOther_1", "x": 101, "y": 501})
        ligaOther.appendAnchor({"name": "topOther_2", "x": 601, "y": 501})
        ligaMix = ufo.newGlyph("f_l")
        ligaMix.appendAnchor({"name": "top_1", "x": 102, "y": 502})
        ligaMix.appendAnchor({"name": "topOther_2", "x": 602, "y": 502})
        acutecomb = ufo.newGlyph("acutecomb")
        acutecomb.appendAnchor({"name": "_top", "x": 100, "y": 200})
        acutecomb.appendAnchor({"name": "_topOther", "x": 150, "y": 250})

        generated = self.writeFeatures(ufo)

        # MC_top should be last thanks to the anchorSortKey
        assert str(generated) == dedent(
            """\
            markClass acutecomb <anchor 100 200> @MC_top;
            markClass acutecomb <anchor 150 250> @MC_topOther;

            feature mark {
                lookup mark2liga {
                    pos ligature f_f
                            <anchor 101 501> mark @MC_topOther
                        ligComponent
                            <anchor 601 501> mark @MC_topOther;
                    pos ligature f_l
                            <anchor NULL>
                        ligComponent
                            <anchor 602 502> mark @MC_topOther;
                } mark2liga;

                lookup mark2liga_1 {
                    pos ligature f_i
                            <anchor 100 500> mark @MC_top
                        ligComponent
                            <anchor 600 500> mark @MC_top;
                    pos ligature f_l
                            <anchor 102 502> mark @MC_top
                        ligComponent
                            <anchor NULL>;
                } mark2liga_1;

            } mark;
            """
        )

    def test_multiple_anchor_classes_conflict_warning(self, FontClass, caplog):
        """Check that when there is an ambiguity in the form of one base glyph
        and one mark glyph being able to be linked through two different
        anchor pairs, the mark feature writer emits a warning about the
        situation but still outputs a valid feature declaraction. The last
        lookup in that feature declaration will "win" and determine the outcome
        of mark positioning. See this comment for more information:
        https://github.com/googlefonts/ufo2ft/pull/416#issuecomment-721693266
        """
        caplog.set_level(logging.INFO)

        ufo = FontClass()
        liga = ufo.newGlyph("a")
        liga.appendAnchor({"name": "top", "x": 100, "y": 500})
        liga.appendAnchor({"name": "topOther", "x": 150, "y": 550})
        acutecomb = ufo.newGlyph("acutecomb")
        acutecomb.appendAnchor({"name": "_top", "x": 100, "y": 200})
        acutecomb.appendAnchor({"name": "_topOther", "x": 150, "y": 250})

        generated = self.writeFeatures(ufo)

        assert (
            "The base glyph a and mark glyph acutecomb are ambiguously "
            "connected by several anchor classes: MC_topOther, MC_top. "
            "The last one will prevail." in caplog.text
        )

        # MC_top should be last thanks to the anchorSortKey
        assert str(generated) == dedent(
            """\
            markClass acutecomb <anchor 100 200> @MC_top;
            markClass acutecomb <anchor 150 250> @MC_topOther;

            feature mark {
                lookup mark2base {
                    pos base a
                        <anchor 150 550> mark @MC_topOther;
                } mark2base;

                lookup mark2base_1 {
                    pos base a
                        <anchor 100 500> mark @MC_top;
                } mark2base_1;

            } mark;
            """
        )

    def test_skipExportGlyphs(self, testufo):
        testufo.lib["public.skipExportGlyphs"] = ["f_i", "tildecomb"]
        testufo.glyphOrder = ["a", "f_i", "acutecomb", "tildcomb"]

        generated = self.writeFeatures(testufo)

        assert str(generated) == dedent(
            """\
            markClass acutecomb <anchor 100 200> @MC_top;

            feature mark {
                lookup mark2base {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark2base;

            } mark;
            """
        )

    def test_quantize(self, testufo):
        testufo.newGlyph("ogonekcomb").anchors = [
            {"name": "_top", "x": 236, "y": 188},
        ]
        testufo.lib["public.skipExportGlyphs"] = ["f_i", "tildecomb"]
        generated = self.writeFeatures(testufo, quantization=50)

        assert str(generated) == dedent(
            """\
            markClass acutecomb <anchor 100 200> @MC_top;
            markClass ogonekcomb <anchor 250 200> @MC_top;

            feature mark {
                lookup mark2base {
                    pos base a
                        <anchor 100 200> mark @MC_top;
                } mark2base;

            } mark;
            """
        )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main(sys.argv))
