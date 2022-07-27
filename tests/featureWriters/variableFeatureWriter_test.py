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
            } mark2base;

        } mark;

        feature curs {
            lookup curs {
                lookupflag RightToLeft IgnoreMarks;
                pos cursive alef-ar.fina <anchor (wght=100:299 wght=1000:330) (wght=100:97 wght=1000:115)> <anchor NULL>;
                pos cursive peh-ar.init <anchor NULL> <anchor (wght=100:161 wght=1000:73) (wght=100:54 wght=1000:89)>;
                pos cursive peh-ar.init.BRACKET.varAlt01 <anchor NULL> <anchor (wght=100:89 wght=1000:73) (wght=100:53 wght=1000:85)>;
            } curs;

        } curs;
"""  # noqa: B950
    )
