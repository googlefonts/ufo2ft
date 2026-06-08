import io
from textwrap import dedent

from fontTools import designspaceLib

from ufo2ft import compileVariableTTF


def _makePartialExceptionDesignSpace(FontClass, *, coverAllMembers=False):
    """Two masters reproducing a partially-populated, conflicting kerning
    exception, the case ufo2ft#988 is about.

        side1 class @c1 = {A, B}   side2 class @c2 = {X, Y}

        (A,  @c2)  = 70   master 'bold' only   glyph-to-class exception
        (@c1, X)   = 30   both masters         class-to-glyph exception
        (@c1, @c2) = 50   both masters         class-to-class (the general value)

    The overlap cell (A, X) is matched by both exceptions. Its source-faithful
    resolution is [regular: 30 from the class-to-glyph (no glyph-to-class yet),
    bold: 70 -- the glyph-to-class wins precedence].

    With coverAllMembers=True, the class-to-glyph exception also covers Y
    ((@c1, Y) = 30), so both overlap cells (A, X) and (A, Y) resolve identically
    -- no cell diverges from another. The glyph-to-class pair is then kept
    compact, but must still carry the agreed cell value [30, 70], not the
    class-to-class value (50) backfilled where the glyph-to-class is absent.
    """

    def makeMaster(kerning):
        font = FontClass()
        font.newGlyph(".notdef").width = 600
        for name, unicode in [("A", 0x41), ("B", 0x42), ("X", 0x58), ("Y", 0x59)]:
            glyph = font.newGlyph(name)
            glyph.width = 600
            glyph.unicodes = [unicode]
            pen = glyph.getPen()
            pen.moveTo((50, 0))
            pen.lineTo((550, 0))
            pen.lineTo((550, 700))
            pen.lineTo((50, 700))
            pen.closePath()
        font.groups["public.kern1.c1"] = ["A", "B"]
        font.groups["public.kern2.c2"] = ["X", "Y"]
        font.kerning.update(kerning)
        font.lib["public.glyphOrder"] = [".notdef", "A", "B", "X", "Y"]
        return font

    regularKerning = {
        ("public.kern1.c1", "public.kern2.c2"): 50,  # class-to-class (general)
        ("public.kern1.c1", "X"): 30,  # class-to-glyph exception
    }
    if coverAllMembers:
        regularKerning[("public.kern1.c1", "Y")] = 30  # class-to-glyph also covers Y
    regular = makeMaster(regularKerning)
    # bold adds the glyph-to-class exception (A, @c2) = 70
    bold = makeMaster({**regularKerning, ("A", "public.kern2.c2"): 70})

    designspace = designspaceLib.DesignSpaceDocument()
    axis = designspace.newAxisDescriptor()
    axis.name, axis.tag = "Weight", "wght"
    axis.minimum, axis.default, axis.maximum = 0, 0, 1000
    designspace.addAxis(axis)
    for font, location, name in [(regular, 0, "regular"), (bold, 1000, "bold")]:
        source = designspace.newSourceDescriptor()
        source.font = font
        source.location = {"Weight": location}
        source.name = source.styleName = name
        source.familyName = "Test"
        designspace.addSource(source)
    return designspace


def test_variable_kern_partial_master_exception(FontClass):
    # A glyph-to-class exception present in only some masters must be resolved
    # per cell and emitted as its own pair ("pos A X ..."), not as a single
    # "enum pos A @kern2.c2 ..." with the class-to-class value backfilled where
    # the exception is absent. That backfill, being glyph-to-class, would shadow
    # the competing class-to-glyph exception and render a phantom value.
    tmp = io.StringIO()
    designspace = _makePartialExceptionDesignSpace(FontClass)
    compileVariableTTF(designspace, debugFeatureFile=tmp)
    assert dedent("\n" + tmp.getvalue()) == dedent("""
        @kern1.Latn.c1 = [A B];
        @kern2.Latn.c2 = [X Y];

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            pos A X (wght=0:30 wght=1000:70);
            pos A Y (wght=0:50 wght=1000:70);
            enum pos @kern1.Latn.c1 X 30;
            pos @kern1.Latn.c1 @kern2.Latn.c2 50;
        } kern_Latn;

        feature kern {
            script DFLT;
            language dflt;
            lookup kern_Latn;

            script latn;
            language dflt;
            lookup kern_Latn;
        } kern;
""")


def test_variable_kern_uniform_override_exception(FontClass):
    # When the class-to-glyph exception covers every member of the second-side
    # class, all overlap cells resolve to the same value, so nothing diverges and
    # the compact "enum pos A @kern2.c2 ..." form is kept. It must still carry the
    # agreed cell value (30 at the default), not the class-to-class value (50)
    # backfilled where the glyph-to-class exception is absent. The backfill would
    # shadow the class-to-glyph exceptions on every cell at the default -- a
    # phantom even though no two cells disagree with each other.
    tmp = io.StringIO()
    designspace = _makePartialExceptionDesignSpace(FontClass, coverAllMembers=True)
    compileVariableTTF(designspace, debugFeatureFile=tmp)
    assert dedent("\n" + tmp.getvalue()) == dedent("""
        @kern1.Latn.c1 = [A B];
        @kern2.Latn.c2 = [X Y];

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            enum pos A @kern2.Latn.c2 (wght=0:30 wght=1000:70);
            enum pos @kern1.Latn.c1 X 30;
            enum pos @kern1.Latn.c1 Y 30;
            pos @kern1.Latn.c1 @kern2.Latn.c2 50;
        } kern_Latn;

        feature kern {
            script DFLT;
            language dflt;
            lookup kern_Latn;

            script latn;
            language dflt;
            lookup kern_Latn;
        } kern;
""")


def test_variable_features(FontClass):
    tmp = io.StringIO()
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        "tests/data/TestVarfea.designspace"
    )
    designspace.loadSourceFonts(FontClass)
    _ = compileVariableTTF(designspace, debugFeatureFile=tmp)

    assert dedent("\n" + tmp.getvalue()) == dedent("""
        markClass dotabove-ar <anchor (wght=100:100 wght=1000:125) (wght=100:320 wght=1000:416)> @mark_top;
        markClass gravecmb <anchor 250 400> @mark_top;

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
                    <anchor (wght=100:211 wght=1000:214) (wght=100:730 wght=1000:797)> mark @mark_top;
                pos base a
                    <anchor 250 400> mark @mark_top;
            } mark2base;

        } mark;

        table GDEF {
            LigatureCaretByPos peh-ar.init 100;
        } GDEF;
""")  # noqa: B950


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

    assert dedent("\n" + tmp.getvalue()) == dedent("""
        markClass dotabove-ar <anchor (wght=100:100 wght=1000:125) (wght=100:320 wght=1000:416)> @mark_top;
        markClass gravecmb <anchor 250 400> @mark_top;

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
                    <anchor (wght=100:211 wght=1000:214) (wght=100:730 wght=1000:797)> mark @mark_top;
                pos base a
                    <anchor 250 400> mark @mark_top;
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
""")  # noqa: B950
