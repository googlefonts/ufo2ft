import io
import itertools
from dataclasses import dataclass
from textwrap import dedent
from typing import NamedTuple

import pytest
from fontTools import designspaceLib
from fontTools.ufoLib.kerning import lookupKerningValue
from fontTools.varLib.errors import VarLibMergeError

from ufo2ft import compileVariableTTF
from ufo2ft.featureWriters.kernFeatureWriter import (
    _refineMembers,
    collectKerningGroups,
)
from ufo2ft.featureWriters.kernFeatureWriter2 import (
    KernFeatureWriter as KernFeatureWriter2,
)
from ufo2ft.featureWriters.markFeatureWriter import MarkFeatureWriter


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
    # class, all overlap cells resolve to the same value. Each member is emitted
    # as its own pair carrying that agreed cell value (30 at the default), not the
    # class-to-class value (50) backfilled where the glyph-to-class exception is
    # absent. The backfill would shadow the class-to-glyph exceptions on every
    # cell at the default -- a phantom even though no two cells disagree.
    tmp = io.StringIO()
    designspace = _makePartialExceptionDesignSpace(FontClass, coverAllMembers=True)
    compileVariableTTF(designspace, debugFeatureFile=tmp)
    assert dedent("\n" + tmp.getvalue()) == dedent("""
        @kern1.Latn.c1 = [A B];
        @kern2.Latn.c2 = [X Y];

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            pos A X (wght=0:30 wght=1000:70);
            pos A Y (wght=0:30 wght=1000:70);
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


def _assertVariableKernMatchesSources(
    designspace, firsts, seconds, featureWriters=None
):
    # At a master location the variation model reconstructs that source exactly,
    # so the kern the font applies to a pair there must equal the value the
    # master's own DS+UFO cascade resolves.
    hb = pytest.importorskip("uharfbuzz")

    kwargs = {} if featureWriters is None else {"featureWriters": featureWriters}
    vf = compileVariableTTF(designspace, **kwargs)
    buf = io.BytesIO()
    vf.save(buf)
    face = hb.Face(buf.getvalue())

    for source in designspace.sources:
        kerning = source.font.kerning
        groups = source.font.groups
        hbFont = hb.Font(face)
        hbFont.set_variations({"wght": source.location["Weight"]})
        for first, second in itertools.product(firsts, seconds):
            expected = lookupKerningValue((first, second), kerning, groups)
            hbBuf = hb.Buffer()
            hbBuf.add_str(first + second)
            hbBuf.guess_segment_properties()
            hb.shape(hbFont, hbBuf, {"kern": True})
            info, pos = hbBuf.glyph_infos, hbBuf.glyph_positions
            actual = pos[0].x_advance - hbFont.get_glyph_h_advance(info[0].codepoint)
            assert actual == expected, (
                f"{source.name} {first}{second}: "
                f"font kerns {actual}, source resolves {expected}"
            )


@pytest.mark.parametrize("coverAllMembers", [False, True])
def test_variable_kern_matches_source_at_masters(coverAllMembers, FontClass):
    designspace = _makePartialExceptionDesignSpace(
        FontClass, coverAllMembers=coverAllMembers
    )
    _assertVariableKernMatchesSources(designspace, ("A", "B"), ("X", "Y"))


class _MasterCase(NamedTuple):
    groups: dict
    kerning: dict


@dataclass
class _DivergentCase:
    regular: _MasterCase
    bold: _MasterCase
    fea: str


_DIVERGENT_CASES = {
    "glyph_to_class": _DivergentCase(
        regular=_MasterCase(
            {"public.kern2.right": ["X", "Y"]},
            {("A", "public.kern2.right"): 100},
        ),
        bold=_MasterCase(
            {"public.kern2.right": ["X"], "public.kern2.other": ["Y"]},
            {("A", "public.kern2.right"): 100, ("A", "public.kern2.other"): -50},
        ),
        fea="""
        lookup kern_Latn {
            lookupflag IgnoreMarks;
            pos A X 100;
            pos A Y (wght=0:100 wght=1000:-50);
        } kern_Latn;
    """,
    ),
    "class_to_class": _DivergentCase(
        regular=_MasterCase(
            {"public.kern1.left": ["A", "B"], "public.kern2.right": ["X", "Y"]},
            {("public.kern1.left", "public.kern2.right"): 100},
        ),
        bold=_MasterCase(
            {
                "public.kern1.left": ["A", "B"],
                "public.kern2.right": ["X"],
                "public.kern2.other": ["Y"],
            },
            {
                ("public.kern1.left", "public.kern2.right"): 100,
                ("public.kern1.left", "public.kern2.other"): -50,
            },
        ),
        fea="""
        @kern1.Latn.left = [A B];
        @kern2.Latn.right = [X];
        @kern2.Latn.right_1 = [Y];

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            pos @kern1.Latn.left @kern2.Latn.right 100;
            pos @kern1.Latn.left @kern2.Latn.right_1 (wght=0:100 wght=1000:-50);
        } kern_Latn;
    """,
    ),
    "class_to_glyph": _DivergentCase(
        regular=_MasterCase(
            {"public.kern1.left": ["A", "B"]},
            {("public.kern1.left", "X"): 100},
        ),
        bold=_MasterCase(
            {"public.kern1.left": ["A"], "public.kern1.other": ["B"]},
            {("public.kern1.left", "X"): 100, ("public.kern1.other", "X"): -50},
        ),
        fea="""
        @kern1.Latn.left = [A];
        @kern1.Latn.left_1 = [B];

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            enum pos @kern1.Latn.left X 100;
            enum pos @kern1.Latn.left_1 X (wght=0:100 wght=1000:-50);
        } kern_Latn;
    """,
    ),
    "both_diverge": _DivergentCase(
        regular=_MasterCase(
            {"public.kern1.left": ["A", "B"], "public.kern2.right": ["X", "Y"]},
            {("public.kern1.left", "public.kern2.right"): 100},
        ),
        bold=_MasterCase(
            {
                "public.kern1.left": ["A"],
                "public.kern1.other": ["B"],
                "public.kern2.right": ["X"],
                "public.kern2.other": ["Y"],
            },
            {
                ("public.kern1.left", "public.kern2.right"): 100,
                ("public.kern1.left", "public.kern2.other"): -50,
                ("public.kern1.other", "public.kern2.right"): 70,
                ("public.kern1.other", "public.kern2.other"): 20,
            },
        ),
        fea="""
        @kern1.Latn.left = [A];
        @kern1.Latn.left_1 = [B];
        @kern2.Latn.right = [X];
        @kern2.Latn.right_1 = [Y];

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            pos @kern1.Latn.left @kern2.Latn.right 100;
            pos @kern1.Latn.left @kern2.Latn.right_1 (wght=0:100 wght=1000:-50);
            pos @kern1.Latn.left_1 @kern2.Latn.right (wght=0:100 wght=1000:70);
            pos @kern1.Latn.left_1 @kern2.Latn.right_1 (wght=0:100 wght=1000:20);
        } kern_Latn;
    """,
    ),
    # Z and W are stranded by first-wins merging but still need bold's value.
    "orphan": _DivergentCase(
        regular=_MasterCase(
            {"public.kern2.right": ["X", "Y"]},
            {("A", "public.kern2.right"): 100},
        ),
        bold=_MasterCase(
            {"public.kern2.right": ["X"], "public.kern2.other": ["Y", "Z", "W"]},
            {("A", "public.kern2.right"): 100, ("A", "public.kern2.other"): -50},
        ),
        fea="""
        lookup kern_Latn {
            lookupflag IgnoreMarks;
            pos A W (wght=0:0 wght=1000:-50);
            pos A X 100;
            pos A Y (wght=0:100 wght=1000:-50);
            pos A Z (wght=0:0 wght=1000:-50);
        } kern_Latn;
    """,
    ),
    # Y is only in bold's dropped group; class naming must still find a name.
    "late_added": _DivergentCase(
        regular=_MasterCase(
            {"public.kern1.left": ["A", "B"], "public.kern2.right": ["X"]},
            {("public.kern1.left", "public.kern2.right"): 100},
        ),
        bold=_MasterCase(
            {"public.kern1.left": ["A", "B"], "public.kern2.right": ["X", "Y"]},
            {("public.kern1.left", "public.kern2.right"): 100},
        ),
        fea="""
        @kern1.Latn.left = [A B];
        @kern2.Latn.right = [X];
        @kern2.Latn.right_1 = [Y];

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            pos @kern1.Latn.left @kern2.Latn.right 100;
            pos @kern1.Latn.left @kern2.Latn.right_1 (wght=0:0 wght=1000:100);
        } kern_Latn;
    """,
    ),
    # Y and Z co-move into one refined class.
    "regrouped": _DivergentCase(
        regular=_MasterCase(
            {"public.kern1.left": ["A", "B"], "public.kern2.right": ["X", "Y", "Z"]},
            {("public.kern1.left", "public.kern2.right"): 100},
        ),
        bold=_MasterCase(
            {
                "public.kern1.left": ["A", "B"],
                "public.kern2.right": ["X"],
                "public.kern2.other": ["Y", "Z"],
            },
            {
                ("public.kern1.left", "public.kern2.right"): 100,
                ("public.kern1.left", "public.kern2.other"): -50,
            },
        ),
        fea="""
        @kern1.Latn.left = [A B];
        @kern2.Latn.right = [X];
        @kern2.Latn.right_1 = [Y Z];

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            pos @kern1.Latn.left @kern2.Latn.right 100;
            pos @kern1.Latn.left @kern2.Latn.right_1 (wght=0:100 wght=1000:-50);
        } kern_Latn;
    """,
    ),
    # A Y exception must not smear onto the [Y Z] refined class.
    "regrouped_exception": _DivergentCase(
        regular=_MasterCase(
            {"public.kern1.left": ["A", "B"], "public.kern2.right": ["X", "Y", "Z"]},
            {
                ("public.kern1.left", "public.kern2.right"): 100,
                ("public.kern1.left", "Y"): 30,
            },
        ),
        bold=_MasterCase(
            {
                "public.kern1.left": ["A", "B"],
                "public.kern2.right": ["X"],
                "public.kern2.other": ["Y", "Z"],
            },
            {
                ("public.kern1.left", "public.kern2.right"): 100,
                ("public.kern1.left", "public.kern2.other"): -50,
            },
        ),
        fea="""
        @kern1.Latn.left = [A B];
        @kern2.Latn.right = [X];
        @kern2.Latn.right_1 = [Y Z];

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            enum pos @kern1.Latn.left Y (wght=0:30 wght=1000:-50);
            pos @kern1.Latn.left @kern2.Latn.right 100;
            pos @kern1.Latn.left @kern2.Latn.right_1 (wght=0:100 wght=1000:-50);
        } kern_Latn;
    """,
    ),
    # The exact B-Y exception must not smear onto B against the refined [Y Z].
    "both_diverge_exception": _DivergentCase(
        regular=_MasterCase(
            {"public.kern1.left": ["A", "B"], "public.kern2.right": ["X", "Y", "Z"]},
            {
                ("public.kern1.left", "public.kern2.right"): 100,
                ("B", "Y"): 30,
            },
        ),
        bold=_MasterCase(
            {
                "public.kern1.left": ["A"],
                "public.kern1.other": ["B"],
                "public.kern2.right": ["X"],
                "public.kern2.other": ["Y", "Z"],
            },
            {
                ("public.kern1.left", "public.kern2.right"): 100,
                ("public.kern1.left", "public.kern2.other"): -50,
                ("public.kern1.other", "public.kern2.right"): 70,
                ("public.kern1.other", "public.kern2.other"): 20,
            },
        ),
        fea="""
        @kern1.Latn.left = [A];
        @kern1.Latn.left_1 = [B];
        @kern2.Latn.right = [X];
        @kern2.Latn.right_1 = [Y Z];

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            pos B Y (wght=0:30 wght=1000:20);
            pos @kern1.Latn.left @kern2.Latn.right 100;
            pos @kern1.Latn.left @kern2.Latn.right_1 (wght=0:100 wght=1000:-50);
            pos @kern1.Latn.left_1 @kern2.Latn.right (wght=0:100 wght=1000:70);
            pos @kern1.Latn.left_1 @kern2.Latn.right_1 (wght=0:100 wght=1000:20);
        } kern_Latn;
    """,
    ),
    # Unkerned destination groups are invisible to varLib.merger, so Y/Z stay
    # together.
    "regrouped_unkerned": _DivergentCase(
        regular=_MasterCase(
            {"public.kern1.left": ["A", "B"], "public.kern2.right": ["X", "Y", "Z"]},
            {("public.kern1.left", "public.kern2.right"): 100},
        ),
        bold=_MasterCase(
            {
                "public.kern1.left": ["A", "B"],
                "public.kern2.right": ["X"],
                "public.kern2.foo": ["Y"],
                "public.kern2.bar": ["Z"],
            },
            {("public.kern1.left", "public.kern2.right"): 100},
        ),
        fea="""
        @kern1.Latn.left = [A B];
        @kern2.Latn.right = [X];
        @kern2.Latn.right_1 = [Y Z];

        lookup kern_Latn {
            lookupflag IgnoreMarks;
            pos @kern1.Latn.left @kern2.Latn.right 100;
            pos @kern1.Latn.left @kern2.Latn.right_1 (wght=0:100 wght=1000:0);
        } kern_Latn;
    """,
    ),
}


def _makeDivergentGroupsDesignSpace(FontClass, mode):
    U = {"A": 0x41, "B": 0x42, "X": 0x58, "Y": 0x59, "Z": 0x5A, "W": 0x57}

    def makeMaster(groups, kerning):
        font = FontClass()
        font.newGlyph(".notdef").width = 600
        order = [".notdef"]
        for name in ("A", "B", "X", "Y", "Z", "W"):
            glyph = font.newGlyph(name)
            glyph.width = 600
            glyph.unicodes = [U[name]]
            pen = glyph.getPen()
            pen.moveTo((50, 0))
            pen.lineTo((550, 0))
            pen.lineTo((550, 700))
            pen.lineTo((50, 700))
            pen.closePath()
            order.append(name)
        # Do not let font objects mutate shared parametrized case data.
        font.groups.update({name: list(members) for name, members in groups.items()})
        font.kerning.update(kerning)
        font.lib["public.glyphOrder"] = order
        return font

    case = _DIVERGENT_CASES[mode]
    designspace = designspaceLib.DesignSpaceDocument()
    axis = designspace.newAxisDescriptor()
    axis.name, axis.tag = "Weight", "wght"
    axis.minimum, axis.default, axis.maximum = 0, 0, 1000
    designspace.addAxis(axis)
    for (groups, kerning), location, name in [
        (case.regular, 0, "regular"),
        (case.bold, 1000, "bold"),
    ]:
        source = designspace.newSourceDescriptor()
        source.font = makeMaster(groups, kerning)
        source.location = {"Weight": location}
        source.name = source.styleName = name
        source.familyName = "Test"
        designspace.addSource(source)
    return designspace


@pytest.mark.parametrize(
    "members, kernedMaps, expected",
    [
        pytest.param(
            ("X", "Y"),
            [{"X": "right", "Y": "right"}, {"X": "right", "Y": "right"}],
            [(("right", "right"), ("X", "Y"))],
            id="consistent-membership-one-class",
        ),
        pytest.param(
            ("X", "Y"),
            [{"X": "right", "Y": "right"}, {"X": "right", "Y": "other"}],
            [(("right", "right"), ("X",)), (("right", "other"), ("Y",))],
            id="regrouped-alone-splits-off",
        ),
        pytest.param(
            ("X", "Y", "Z"),
            [
                {"X": "right", "Y": "right", "Z": "right"},
                {"X": "right", "Y": "other", "Z": "other"},
            ],
            [(("right", "right"), ("X",)), (("right", "other"), ("Y", "Z"))],
            id="regrouped-together-stays-one-class",
        ),
        pytest.param(
            ("W", "X"),
            [{"X": "right"}, {"X": "right"}],
            [((None, None), ("W",)), (("right", "right"), ("X",))],
            id="ungrouped-everywhere-shares-fallback-class",
        ),
        pytest.param(
            ("X", "Y", "Z"),
            [{"X": "right", "Y": "right", "Z": "right"}, {"X": "right"}],
            [(("right", "right"), ("X",)), (("right", None), ("Y", "Z"))],
            id="unkerned-groups-omitted-matching-varlib",
        ),
    ],
)
def test_refineMembers_partitions_by_cross_source_signature(
    members, kernedMaps, expected
):
    # Pin the partition primitive independently of full font compilation.
    assert _refineMembers(members, kernedMaps) == expected


def test_collectKerningGroups_backfills_merge_dropped_glyphs(FontClass):
    # late_added strands Y outside merged classes; backfill preserves its name.
    designspace = _makeDivergentGroupsDesignSpace(FontClass, "late_added")
    glyphSet = {g: None for g in ("A", "B", "X", "Y", "Z", "W")}
    _, side2Groups, _, side2Membership = collectKerningGroups(
        designspace, glyphSet, isVariable=True
    )
    assert side2Groups["public.kern2.right"] == ("X",)
    assert "Y" not in {g for members in side2Groups.values() for g in members}
    assert side2Membership["Y"] == "right"


@pytest.mark.parametrize(
    "writerClass", [None, KernFeatureWriter2], ids=["writer1", "writer2"]
)
@pytest.mark.parametrize("mode", list(_DIVERGENT_CASES))
def test_variable_kern_divergent_groups_match_sources(mode, writerClass, FontClass):
    designspace = _makeDivergentGroupsDesignSpace(FontClass, mode)
    featureWriters = None if writerClass is None else [writerClass()]
    _assertVariableKernMatchesSources(
        designspace, ("A", "B"), ("X", "Y", "Z", "W"), featureWriters=featureWriters
    )


def _makeKernlessMasterDesignSpace(
    FontClass, *, kerned="glyph", midGroups=False, midKern=None, withMarks=False
):
    # Three full (non-layer) masters: two flanking masters that kern 100 at both
    # ends of the axis, and a middle master under test whose kerning is midKern
    # (default empty -- the #995 kernless shape). The default source is kept
    # non-kernless (its own kernless corner is out of scope for #995).
    #
    # kerned selects how the flanking masters kern: a bare glyph pair ("glyph"),
    # a glyph-to-class pair ("glyph_class", second side @right = [X, Y]), or a
    # class-to-class pair ("class_class", @left = [A, B] against @right = [X, Y]
    # -- the Roboto Flex parametric shape). midGroups additionally gives the
    # middle master those same kern groups, so its empty kerning must not make
    # the grouped glyphs look divergent.
    U = {"A": 0x41, "B": 0x42, "X": 0x58, "Y": 0x59}
    if kerned == "glyph":
        names = ("A", "X")
        groups = {}
        endKern = {("A", "X"): 100}
    elif kerned == "glyph_class":
        names = ("A", "X", "Y")
        groups = {"public.kern2.right": ["X", "Y"]}
        endKern = {("A", "public.kern2.right"): 100}
    elif kerned == "class_class":
        names = ("A", "B", "X", "Y")
        groups = {"public.kern1.left": ["A", "B"], "public.kern2.right": ["X", "Y"]}
        endKern = {("public.kern1.left", "public.kern2.right"): 100}
    else:
        raise ValueError(f"unknown kerned mode: {kerned!r}")

    def makeMaster(kerning, withGroups):
        font = FontClass()
        font.newGlyph(".notdef").width = 600
        order = [".notdef"]
        for name in names:
            glyph = font.newGlyph(name)
            glyph.width = 600
            glyph.unicodes = [U[name]]
            pen = glyph.getPen()
            pen.moveTo((50, 0))
            pen.lineTo((550, 0))
            pen.lineTo((550, 700))
            pen.lineTo((50, 700))
            pen.closePath()
            order.append(name)
        if withMarks:
            # A "top" base anchor plus a combining mark glyph makes ufo2ft emit
            # a mark feature, i.e. GPOS content beyond kerning.
            font["A"].appendAnchor({"name": "top", "x": 300, "y": 700})
            mark = font.newGlyph("gravecomb")
            mark.width = 0
            mark.unicodes = [0x0300]
            mark.appendAnchor({"name": "_top", "x": 0, "y": 0})
            order.append("gravecomb")
        if withGroups and groups:
            font.groups.update({n: list(m) for n, m in groups.items()})
        font.kerning.update(kerning)
        font.lib["public.glyphOrder"] = order
        return font

    masters = [
        (makeMaster(endKern, True), 0, "regular"),
        (makeMaster(midKern or {}, midGroups), 500, "mid"),
        (makeMaster(endKern, True), 1000, "bold"),
    ]

    designspace = designspaceLib.DesignSpaceDocument()
    axis = designspace.newAxisDescriptor()
    axis.name, axis.tag = "Weight", "wght"
    axis.minimum, axis.default, axis.maximum = 0, 0, 1000
    designspace.addAxis(axis)
    for font, location, name in masters:
        source = designspace.newSourceDescriptor()
        source.font = font
        source.location = {"Weight": location}
        source.name = source.styleName = name
        source.familyName = "Test"
        designspace.addSource(source)
    return designspace


def _shapeKern(face, hb, text, wght):
    font = hb.Font(face)
    font.set_variations({"wght": wght})
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"kern": True})
    info, pos = buf.glyph_infos, buf.glyph_positions
    return pos[0].x_advance - font.get_glyph_h_advance(info[0].codepoint)


def _assertKernlessMasterMatchesVarLib(FontClass, texts, *, featureWriters, **dsKwargs):
    # The varLib merge path (variableFeatures=False) is the oracle: it excludes
    # the kernless master's absent GPOS and keeps the kern constant. The
    # variable-features path (variableFeatures=True) must reproduce it.
    hb = pytest.importorskip("uharfbuzz")
    locations = (0, 250, 500, 750, 1000)
    kwargs = {} if featureWriters is None else {"featureWriters": featureWriters}
    varlib = compileVariableTTF(
        _makeKernlessMasterDesignSpace(FontClass, **dsKwargs),
        variableFeatures=False,
    )
    varfea = compileVariableTTF(
        _makeKernlessMasterDesignSpace(FontClass, **dsKwargs),
        variableFeatures=True,
        **kwargs,
    )
    varlibBuf, varfeaBuf = io.BytesIO(), io.BytesIO()
    varlib.save(varlibBuf)
    varfea.save(varfeaBuf)
    varlibFace = hb.Face(varlibBuf.getvalue())
    varfeaFace = hb.Face(varfeaBuf.getvalue())
    for text in texts:
        for wght in locations:
            expected = _shapeKern(varlibFace, hb, text, wght)
            actual = _shapeKern(varfeaFace, hb, text, wght)
            assert actual == expected, (
                f"{text} wght={wght}: " f"varfea kerns {actual}, varlib {expected}"
            )


@pytest.mark.parametrize(
    "writerClass", [None, KernFeatureWriter2], ids=["writer1", "writer2"]
)
def test_variable_kern_kernless_master_matches_varlib(writerClass, FontClass):
    # https://github.com/googlefonts/ufo2ft/issues/995: a full master with no
    # kerning must not pin the kern to 0 at its location.
    featureWriters = None if writerClass is None else [writerClass()]
    _assertKernlessMasterMatchesVarLib(
        FontClass, ["AX"], featureWriters=featureWriters, kerned="glyph"
    )


@pytest.mark.parametrize(
    "writerClass", [None, KernFeatureWriter2], ids=["writer1", "writer2"]
)
def test_variable_kern_kernless_master_with_groups_matches_varlib(
    writerClass, FontClass
):
    # The kernless master still carries the kern groups: its empty kerning must
    # neither zero the class kern nor make the grouped glyphs look divergent.
    featureWriters = None if writerClass is None else [writerClass()]
    _assertKernlessMasterMatchesVarLib(
        FontClass,
        ["AX", "AY"],
        featureWriters=featureWriters,
        kerned="glyph_class",
        midGroups=True,
    )


@pytest.mark.parametrize(
    "writerClass", [None, KernFeatureWriter2], ids=["writer1", "writer2"]
)
def test_variable_kern_kernless_master_no_groups_matches_varlib(writerClass, FontClass):
    # The Roboto Flex parametric shape: flanking masters kern one class-to-class
    # pair; the middle master has neither groups nor kerning. Skipping it keeps
    # that pair intact -- letting it participate would make its glyphs look
    # ungrouped, splintering the class pair into per-cell glyph pairs. Shaping
    # stays correct either way, so the FEA assertion below guards GPOS structure.
    featureWriters = None if writerClass is None else [writerClass()]
    _assertKernlessMasterMatchesVarLib(
        FontClass,
        ["AX", "AY", "BX", "BY"],
        featureWriters=featureWriters,
        kerned="class_class",
    )
    if writerClass is None:
        # The class kern stays a single, non-varying class-to-class pair.
        tmp = io.StringIO()
        compileVariableTTF(
            _makeKernlessMasterDesignSpace(FontClass, kerned="class_class"),
            debugFeatureFile=tmp,
        )
        fea = tmp.getvalue()
        assert "pos @kern1.Latn.left @kern2.Latn.right 100;" in fea, fea
        assert "pos A X" not in fea, fea


@pytest.mark.parametrize(
    "writerClass", [None, KernFeatureWriter2], ids=["writer1", "writer2"]
)
def test_variable_kern_explicit_zero_master_participates(writerClass, FontClass):
    # A master with an explicit zero-valued pair has non-empty kerning, so it is
    # NOT treated as kernless: it participates and pins the kern to 0 at its
    # location, identically to the varLib merge path. This is the escape hatch
    # #995 leaves for an author who genuinely wants the kern to collapse to 0 at
    # a master (contrast test_variable_kern_kernless_master_matches_varlib, where
    # an absent kerning interpolates across instead).
    hb = pytest.importorskip("uharfbuzz")
    featureWriters = None if writerClass is None else [writerClass()]
    # Both paths honor the explicit zero identically.
    _assertKernlessMasterMatchesVarLib(
        FontClass, ["AX"], featureWriters=featureWriters, midKern={("A", "X"): 0}
    )
    # And it must actually pull the kern to 0 at the mid master, proving that
    # master participated rather than being skipped as kernless.
    kwargs = {} if featureWriters is None else {"featureWriters": featureWriters}
    varfea = compileVariableTTF(
        _makeKernlessMasterDesignSpace(FontClass, midKern={("A", "X"): 0}),
        variableFeatures=True,
        **kwargs,
    )
    buf = io.BytesIO()
    varfea.save(buf)
    face = hb.Face(buf.getvalue())
    assert _shapeKern(face, hb, "AX", 500) == 0
    assert _shapeKern(face, hb, "AX", 0) == 100


@pytest.mark.parametrize(
    "writerClass", [None, KernFeatureWriter2], ids=["writer1", "writer2"]
)
def test_variable_kern_kernless_master_with_marks_compiles(writerClass, FontClass):
    # The case raised in #997 review: a kernless master can still carry other
    # GPOS. Here the middle master has a mark feature (from anchors) but no
    # kerning. The varLib merge path cannot handle it -- that master's GPOS has
    # the mark feature but no kern feature, so the per-master feature lists
    # diverge and the merge raises (#350). The variable-fea path builds features
    # once over the whole designspace, so it compiles: the empty kerning is
    # simply non-participating (#995) while the marks build independently.
    hb = pytest.importorskip("uharfbuzz")
    # Default writers include the kern and mark writers; for writer2 the mark
    # writer must be added explicitly so the mark GPOS is still generated.
    if writerClass is None:
        featureWriters = None
    else:
        featureWriters = [writerClass(), MarkFeatureWriter()]
    kwargs = {} if featureWriters is None else {"featureWriters": featureWriters}

    with pytest.raises(VarLibMergeError):
        compileVariableTTF(
            _makeKernlessMasterDesignSpace(FontClass, withMarks=True),
            variableFeatures=False,
            **kwargs,
        )

    varfea = compileVariableTTF(
        _makeKernlessMasterDesignSpace(FontClass, withMarks=True),
        variableFeatures=True,
        **kwargs,
    )
    features = {fr.FeatureTag for fr in varfea["GPOS"].table.FeatureList.FeatureRecord}
    assert {"kern", "mark"} <= features, features
    # The kern interpolates across the kernless master (stays 100) rather than
    # being pinned to 0 there, and the marks survived alongside it.
    buf = io.BytesIO()
    varfea.save(buf)
    face = hb.Face(buf.getvalue())
    for wght in (0, 500, 1000):
        assert _shapeKern(face, hb, "AX", wght) == 100


# Shared feature/lookup tail for the exact-FEA cases.
_KERN_FEATURE_TAIL = """
    feature kern {
        script DFLT;
        language dflt;
        lookup kern_Latn;

        script latn;
        language dflt;
        lookup kern_Latn;
    } kern;
"""


def _normalizeFea(text):
    # feaLib pads some blank lines with whitespace; rstrip each line so the
    # golden strings can stay clean, and drop leading/trailing blank lines.
    return "\n".join(line.rstrip() for line in dedent(text).strip("\n").splitlines())


@pytest.mark.parametrize("mode", list(_DIVERGENT_CASES))
def test_variable_kern_divergent_groups_fea(mode, FontClass):
    designspace = _makeDivergentGroupsDesignSpace(FontClass, mode)
    tmp = io.StringIO()
    compileVariableTTF(designspace, debugFeatureFile=tmp)
    expected = (
        _normalizeFea(_DIVERGENT_CASES[mode].fea)
        + "\n\n"
        + _normalizeFea(_KERN_FEATURE_TAIL)
    )
    assert _normalizeFea(tmp.getvalue()) == expected


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
