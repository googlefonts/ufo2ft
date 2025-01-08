import io
from textwrap import dedent

from fontTools import designspaceLib

from ufo2ft import compileVariableTTF


def test_variable_features(FontClass):
    tmp = io.StringIO()
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        "tests/data/TestVarfea.designspace"
    )
    designspace.loadSourceFonts(FontClass)
    _ = compileVariableTTF(designspace, debugFeatureFile=tmp)

    assert dedent("\n" + tmp.getvalue()) == dedent(
        """
        markClass dotabove-ar <anchor (wght=100:100 wght=1000:125) (wght=100:320 wght=1000:416)> @MC_top;
        markClass gravecmb <anchor 250 400> @MC_top;

        feature curs {
            lookup curs_rtl {
                lookupflag RightToLeft IgnoreMarks;
                pos cursive alef-ar.fina <anchor (wght=100:299 wght=1000:330) (wght=100:97 wght=1000:115)> <anchor NULL>;
                pos cursive peh-ar.init <anchor NULL> <anchor (wght=100:161 wght=1000:73) (wght=100:54 wght=1000:89)>;
                pos cursive peh-ar.init.BRACKET.varAlt01 <anchor NULL> <anchor (wght=100:89 wght=1000:73) (wght=100:53 wght=1000:85)>;
            } curs_rtl;

        } curs;

        lookup kern_Arab {
            lookupflag IgnoreMarks;
            pos alef-ar.fina alef-ar.fina <(wght=100:15 wght=1000:35) 0 (wght=100:15 wght=1000:35) 0>;
        } kern_Arab;

        feature kern {
            script DFLT;
            language dflt;
            lookup kern_Arab;

            script arab;
            language dflt;
            lookup kern_Arab;
        } kern;

        feature mark {
            lookup mark2base {
                pos base alef-ar.fina
                    <anchor (wght=100:211 wght=1000:214) (wght=100:730 wght=1000:797)> mark @MC_top;
                pos base a
                    <anchor 250 400> mark @MC_top;
            } mark2base;

        } mark;

        table GDEF {
            LigatureCaretByPos peh-ar.init 100;
        } GDEF;
"""  # noqa: B950
    )


def test_variable_features_old_kern_writer(FontClass):
    tmp = io.StringIO()
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        "tests/data/TestVarfea.designspace"
    )
    designspace.loadSourceFonts(FontClass)

    default_source = designspace.findDefault()
    assert default_source is not None
    default_ufo = default_source.font
    assert default_ufo is not None
    default_ufo.lib["com.github.googlei18n.ufo2ft.featureWriters"] = [
        {
            "module": "ufo2ft.featureWriters.kernFeatureWriter2",
            "class": "KernFeatureWriter",
        },
        {
            "module": "ufo2ft.featureWriters.markFeatureWriter",
            "class": "MarkFeatureWriter",
        },
        {
            "module": "ufo2ft.featureWriters.gdefFeatureWriter",
            "class": "GdefFeatureWriter",
        },
        {
            "module": "ufo2ft.featureWriters.cursFeatureWriter",
            "class": "CursFeatureWriter",
        },
    ]
    for index, source in enumerate(designspace.sources):
        font = source.font
        font.groups["public.kern1.alef"] = ["alef-ar.fina"]
        font.groups["public.kern2.alef"] = ["alef-ar.fina"]
        font.kerning[("public.kern1.alef", "public.kern2.alef")] = index

    _ = compileVariableTTF(designspace, debugFeatureFile=tmp)

    assert dedent("\n" + tmp.getvalue()) == dedent(
        """
        markClass dotabove-ar <anchor (wght=100:100 wght=1000:125) (wght=100:320 wght=1000:416)> @MC_top;
        markClass gravecmb <anchor 250 400> @MC_top;

        @kern1.rtl.alef = [alef-ar.fina];
        @kern2.rtl.alef = [alef-ar.fina];

        lookup kern_rtl {
            lookupflag IgnoreMarks;
            pos alef-ar.fina alef-ar.fina <(wght=100:15 wght=1000:35) 0 (wght=100:15 wght=1000:35) 0>;
            pos @kern1.rtl.alef @kern2.rtl.alef <(wght=100:0 wght=1000:1) 0 (wght=100:0 wght=1000:1) 0>;
        } kern_rtl;

        feature kern {
            script DFLT;
            language dflt;
            lookup kern_rtl;

            script arab;
            language dflt;
            lookup kern_rtl;
        } kern;

        feature mark {
            lookup mark2base {
                pos base alef-ar.fina
                    <anchor (wght=100:211 wght=1000:214) (wght=100:730 wght=1000:797)> mark @MC_top;
                pos base a
                    <anchor 250 400> mark @MC_top;
            } mark2base;

        } mark;

        table GDEF {
            LigatureCaretByPos peh-ar.init 100;
        } GDEF;

        feature curs {
            lookup curs_rtl {
                lookupflag RightToLeft IgnoreMarks;
                pos cursive alef-ar.fina <anchor (wght=100:299 wght=1000:330) (wght=100:97 wght=1000:115)> <anchor NULL>;
                pos cursive peh-ar.init <anchor NULL> <anchor (wght=100:161 wght=1000:73) (wght=100:54 wght=1000:89)>;
                pos cursive peh-ar.init.BRACKET.varAlt01 <anchor NULL> <anchor (wght=100:89 wght=1000:73) (wght=100:53 wght=1000:85)>;
            } curs_rtl;

        } curs;
"""  # noqa: B950
    )
