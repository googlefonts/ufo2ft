import logging

import fontTools.designspaceLib as designspaceLib
import pytest
from fontTools.pens.recordingPen import RecordingPen

import ufo2ft.instantiator
from ufo2ft.util import openFont, openFontFactory


def test_interpolation_weight_width_class(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "MutatorSans" / "MutatorSans.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    generator = ufo2ft.instantiator.Instantiator.from_designspace(
        designspace, round_geometry=True
    )

    for instance in designspace.instances:
        instance.font = generator.generate_instance(instance)

    # LightCondensed
    font = designspace.instances[0].font
    assert font.info.openTypeOS2WeightClass == 1
    assert font.info.openTypeOS2WidthClass == 1

    # BoldCondensed
    font = designspace.instances[1].font
    assert font.info.openTypeOS2WeightClass == 1000
    assert font.info.openTypeOS2WidthClass == 1

    # LightWide
    font = designspace.instances[2].font
    assert font.info.openTypeOS2WeightClass == 1
    assert font.info.openTypeOS2WidthClass == 9

    # BoldWide
    font = designspace.instances[3].font
    assert font.info.openTypeOS2WeightClass == 1000
    assert font.info.openTypeOS2WidthClass == 9

    # Medium_Narrow_I
    font = designspace.instances[4].font
    assert font.info.openTypeOS2WeightClass == 500
    assert font.info.openTypeOS2WidthClass == 9

    # Medium_Wide_I
    font = designspace.instances[5].font
    assert font.info.openTypeOS2WeightClass == 500
    assert font.info.openTypeOS2WidthClass == 9

    # Two
    font = designspace.instances[6].font
    assert font.info.openTypeOS2WeightClass == 1000
    assert font.info.openTypeOS2WidthClass == 9

    # One
    font = designspace.instances[7].font
    assert font.info.openTypeOS2WeightClass == 500
    assert font.info.openTypeOS2WidthClass == 9


def test_default_groups_only(ufo_module, data_dir, caplog):
    """Test that only the default source's groups end up in instances."""

    d = designspaceLib.DesignSpaceDocument()
    d.addAxisDescriptor(
        name="Weight", tag="wght", minimum=300, default=300, maximum=900
    )
    d.addSourceDescriptor(location={"Weight": 300}, font=ufo_module.Font())
    d.addSourceDescriptor(location={"Weight": 900}, font=ufo_module.Font())
    d.addInstanceDescriptor(styleName="2", location={"Weight": 400})

    d.sources[0].font.groups["public.kern1.GRK_alpha_alt_LC_1ST"] = [
        "alpha.alt",
        "alphatonos.alt",
    ]
    d.sources[1].font.groups["public.kern1.GRK_alpha_LC_1ST"] = [
        "alpha.alt",
        "alphatonos.alt",
    ]

    generator = ufo2ft.instantiator.Instantiator.from_designspace(d)
    assert "contains different groups than the default source" in caplog.text

    instance = generator.generate_instance(d.instances[0])
    assert instance.groups == {
        "public.kern1.GRK_alpha_alt_LC_1ST": ["alpha.alt", "alphatonos.alt"]
    }


def test_default_groups_only2(ufo_module, data_dir, caplog):
    """Test that the group difference warning is not triggered if non-default
    source groups are empty."""

    d = designspaceLib.DesignSpaceDocument()
    d.addAxisDescriptor(
        name="Weight", tag="wght", minimum=300, default=300, maximum=900
    )
    d.addSourceDescriptor(location={"Weight": 300}, font=ufo_module.Font())
    d.addSourceDescriptor(location={"Weight": 900}, font=ufo_module.Font())
    d.addInstanceDescriptor(styleName="2", location={"Weight": 400})

    d.sources[0].font.groups["public.kern1.GRK_alpha_alt_LC_1ST"] = [
        "alpha.alt",
        "alphatonos.alt",
    ]

    generator = ufo2ft.instantiator.Instantiator.from_designspace(d)
    assert "contains different groups than the default source" not in caplog.text

    instance = generator.generate_instance(d.instances[0])
    assert instance.groups == {
        "public.kern1.GRK_alpha_alt_LC_1ST": ["alpha.alt", "alphatonos.alt"]
    }


def test_interpolation_no_rounding(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "MutatorSans" / "MutatorSans.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    designspace.instances[4].location = {"weight": 123.456, "width": 789.123}
    generator = ufo2ft.instantiator.Instantiator.from_designspace(
        designspace, round_geometry=False
    )

    instance_font = generator.generate_instance(designspace.instances[4])
    assert isinstance(instance_font.info.ascender, float)
    assert isinstance(instance_font.kerning[("A", "J")], float)
    assert isinstance(instance_font["A"].contours[0][0].x, float)


def test_interpolation_rounding(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "MutatorSans" / "MutatorSans.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    designspace.instances[4].location = {"weight": 123.456, "width": 789.123}
    generator = ufo2ft.instantiator.Instantiator.from_designspace(
        designspace, round_geometry=True
    )

    instance_font = generator.generate_instance(designspace.instances[4])
    assert isinstance(instance_font.info.ascender, int)
    assert isinstance(instance_font.kerning[("A", "J")], int)
    assert isinstance(instance_font["A"].contours[0][0].x, int)


def test_weight_class_from_wght_axis():
    assert ufo2ft.instantiator.weight_class_from_wght_value(-500) == 1
    assert ufo2ft.instantiator.weight_class_from_wght_value(1.1) == 1
    assert ufo2ft.instantiator.weight_class_from_wght_value(1) == 1
    assert ufo2ft.instantiator.weight_class_from_wght_value(500.6) == 501
    assert ufo2ft.instantiator.weight_class_from_wght_value(1000) == 1000
    assert ufo2ft.instantiator.weight_class_from_wght_value(1000.0) == 1000
    assert ufo2ft.instantiator.weight_class_from_wght_value(1000.1) == 1000
    assert ufo2ft.instantiator.weight_class_from_wght_value(2000.1) == 1000


def test_width_class_from_wdth_axis():
    assert ufo2ft.instantiator.width_class_from_wdth_value(-500) == 1
    assert ufo2ft.instantiator.width_class_from_wdth_value(50) == 1
    assert ufo2ft.instantiator.width_class_from_wdth_value(62.5) == 2
    assert ufo2ft.instantiator.width_class_from_wdth_value(75) == 3
    assert ufo2ft.instantiator.width_class_from_wdth_value(87.5) == 4
    assert ufo2ft.instantiator.width_class_from_wdth_value(100) == 5
    assert ufo2ft.instantiator.width_class_from_wdth_value(112) == 6
    assert ufo2ft.instantiator.width_class_from_wdth_value(112.5) == 6
    assert ufo2ft.instantiator.width_class_from_wdth_value(125) == 7
    assert ufo2ft.instantiator.width_class_from_wdth_value(130) == 7
    assert ufo2ft.instantiator.width_class_from_wdth_value(150) == 8
    assert ufo2ft.instantiator.width_class_from_wdth_value(190) == 9
    assert ufo2ft.instantiator.width_class_from_wdth_value(200) == 9
    assert ufo2ft.instantiator.width_class_from_wdth_value(1000) == 9


def test_swap_glyph_names(ufo_module, data_dir):
    ufo = openFont(data_dir / "SwapGlyphNames" / "A.ufo", ufo_module=ufo_module)

    ufo2ft.instantiator.swap_glyph_names(ufo, "a", "a.swap")

    # Test swapped outlines.
    assert ufo["a"].unicode == 0x61
    assert len(ufo["a"]) == 1
    assert len(ufo["a"][0]) == 8
    assert ufo["a"].width == 666
    assert ufo["a.swap"].unicode is None
    assert len(ufo["a.swap"]) == 1
    assert len(ufo["a.swap"][0]) == 4
    assert ufo["a.swap"].width == 600

    # Test swapped components.
    assert sorted(c.baseGlyph for c in ufo["aaa"].components) == [
        "a.swap",
        "a.swap",
        "x",
    ]
    assert sorted(c.baseGlyph for c in ufo["aaa.swap"].components) == ["a", "a", "y"]

    # Test swapped anchors.
    assert [dict(a) for a in ufo["a"].anchors] == [
        dict(x=153, y=0, name="bottom"),
        dict(x=153, y=316, name="top"),
    ]
    assert [dict(a) for a in ufo["a.swap"].anchors] == [
        dict(x=351, y=0, name="bottom"),
        dict(x=351, y=613, name="top"),
    ]

    # Test swapped glyph kerning.
    assert ufo.kerning == {
        ("public.kern1.a", "x"): 10,
        ("public.kern1.aswap", "x"): 20,
        ("a", "y"): 40,
        ("a.swap", "y"): 30,
        ("y", "a"): 60,
        ("y", "a.swap"): 50,
    }

    # Test swapped group membership.
    assert ufo.groups == {
        "public.kern1.a": ["a.swap"],
        "public.kern1.aswap": ["a"],
        "public.kern2.a": ["a.swap", "a"],
    }

    # Swap a second time.
    ufo2ft.instantiator.swap_glyph_names(ufo, "aaa", "aaa.swap")

    # Test swapped glyphs.
    assert sorted(c.baseGlyph for c in ufo["aaa"].components) == ["a", "a", "y"]
    assert sorted(c.baseGlyph for c in ufo["aaa.swap"].components) == [
        "a.swap",
        "a.swap",
        "x",
    ]

    # Test for no leftover temporary glyphs.
    assert {g.name for g in ufo} == {
        "space",
        "a",
        "a.swap",
        "aaa",
        "aaa.swap",
        "x",
        "y",
    }

    with pytest.raises(ufo2ft.instantiator.InstantiatorError, match="Cannot swap"):
        ufo2ft.instantiator.swap_glyph_names(ufo, "aaa", "aaa.swapa")


def test_swap_glyph_names_spec(ufo_module, data_dir):
    """Test that the rule example in the designspaceLib spec works.

    `adieresis` should look the same as before the rule application.

    [1]: fonttools/Doc/source/designspaceLib#ufo-instances
    """
    ufo = openFont(data_dir / "SwapGlyphNames" / "B.ufo", ufo_module=ufo_module)
    ufo2ft.instantiator.swap_glyph_names(ufo, "a", "a.alt")

    assert sorted(c.baseGlyph for c in ufo["adieresis"].components) == [
        "a.alt",
        "dieresiscomb",
    ]
    assert sorted(c.baseGlyph for c in ufo["adieresis.alt"].components) == [
        "a",
        "dieresiscomb",
    ]


def test_rules_are_applied_deterministically(ufo_module, data_dir):
    """Test that a combination of designspace rules that end up mapping
    serveral input glyphs to the same destination glyph result in a correct and
    deterministic series of glyph swaps.

    The example is a font with 2 Q designs that depend on a style axis
        style < 0.5: Q        style >= 0.5: Q.ss01
    and each Q also has an alternative shape in bolder weights (like Skia)
        weight < 780: Q       weight >= 780: Q.alt
        weight < 730: Q.ss01  weight >= 730: Q.ss01.alt

    Then we generate an instance at style = 1, weight = 900. From the rules,
    the default CMAP entry for Q should have the outlines of Q.ss01.alt from
    the black UFO.
    """
    doc = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "DesignspaceRuleOrder" / "MyFont.designspace"
    )
    doc.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    generator = ufo2ft.instantiator.Instantiator.from_designspace(doc)
    instance = generator.generate_instance(doc.instances[0])
    pen = RecordingPen()
    instance["Q"].draw(pen)
    instance_recording = pen.value

    black_ufo = openFont(
        data_dir / "DesignspaceRuleOrder" / "MyFont_Black.ufo", ufo_module=ufo_module
    )
    pen = RecordingPen()
    black_ufo["Q.ss01.alt"].draw(pen)
    black_ufo_recording = pen.value

    assert instance_recording == black_ufo_recording


def test_raise_no_default_master(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "MutatorSans" / "MutatorSans_no_default.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))

    with pytest.raises(ufo2ft.instantiator.InstantiatorError, match="no default"):
        ufo2ft.instantiator.Instantiator.from_designspace(
            designspace, round_geometry=True
        )


def test_raise_failed_glyph_interpolation(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "DesignspaceBrokenTest" / "DesignspaceTest.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    generator = ufo2ft.instantiator.Instantiator.from_designspace(designspace)

    with pytest.raises(
        ufo2ft.instantiator.InstantiatorError, match="Failed to generate instance"
    ):
        for instance in designspace.instances:
            instance.font = generator.generate_instance(instance)


def test_ignore_failed_glyph_interpolation(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "DesignspaceBrokenTest" / "DesignspaceTest.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    generator = ufo2ft.instantiator.Instantiator.from_designspace(designspace)
    generator.skip_export_glyphs.append("asas")

    for instance in designspace.instances:
        instance.font = generator.generate_instance(instance)
        assert (
            not instance.font["asas"].contours and not instance.font["asas"].components
        )


def test_raise_anisotropic_location(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "MutatorSans" / "MutatorSans-width-only.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    designspace.instances[0].location["width"] = (100, 900)

    with pytest.raises(
        ufo2ft.instantiator.InstantiatorError, match="anisotropic instance locations"
    ):
        ufo2ft.instantiator.Instantiator.from_designspace(
            designspace, round_geometry=True
        )


def test_copy_nonkerning_group(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "DesignspaceTest" / "DesignspaceTest.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    generator = ufo2ft.instantiator.Instantiator.from_designspace(designspace)

    instance_font = generator.generate_instance(designspace.instances[0])
    assert instance_font.groups == {
        "nonkerning_group": ["A"],
        "public.kern2.asdf": ["A"],
    }


def test_interpolation(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "DesignspaceTest" / "DesignspaceTest.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    generator = ufo2ft.instantiator.Instantiator.from_designspace(
        designspace, round_geometry=True
    )

    instance_font = generator.generate_instance(designspace.instances[0])
    assert instance_font["l"].width == 220


def test_interpolation_only_default(ufo_module, data_dir, caplog):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "MutatorSans" / "MutatorSans.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    for name in designspace.default.font.glyphOrder:
        if name != "A":
            del designspace.default.font[name]

    with caplog.at_level(logging.WARNING):
        generator = ufo2ft.instantiator.Instantiator.from_designspace(
            designspace, round_geometry=True
        )
    assert "contains glyphs that are missing from the" in caplog.text

    instance_font = generator.generate_instance(designspace.instances[0])
    assert {g.name for g in instance_font} == {"A"}


def test_interpolation_masters_as_instances(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir
        / "DesignspaceBrokenTest"
        / "Designspace-MastersAsInstances.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    generator = ufo2ft.instantiator.Instantiator.from_designspace(
        designspace, round_geometry=True
    )

    instance_font = generator.generate_instance(designspace.instances[0])
    assert instance_font.info.styleName == "Light ASDF"
    assert instance_font["l"].width == 160
    instance_font = generator.generate_instance(designspace.instances[1])
    assert instance_font.info.styleName == "Bold ASDF"
    assert instance_font["l"].width == 280


def test_non_default_layer(ufo_module, data_dir, caplog):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "MutatorSans" / "MutatorSans-non-default-layer.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    generator = ufo2ft.instantiator.Instantiator.from_designspace(
        designspace, round_geometry=True
    )
    instance_font = generator.generate_instance(designspace.instances[0])
    assert {g.name for g in instance_font} == {"A", "S", "W"}


def test_instance_attributes(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "DesignspaceTest" / "DesignspaceTest-instance-attrs.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    generator = ufo2ft.instantiator.Instantiator.from_designspace(
        designspace, round_geometry=True
    )

    instance_font = generator.generate_instance(designspace.instances[0])
    assert instance_font.info.familyName == "aaa"
    assert instance_font.info.styleName == "sss"
    assert instance_font.info.postscriptFontName == "ppp"
    assert instance_font.info.styleMapFamilyName == "yyy"
    assert instance_font.info.styleMapStyleName == "xxx"


def test_instance_no_attributes(ufo_module, data_dir, caplog):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "DesignspaceTest" / "DesignspaceTest-bare.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    generator = ufo2ft.instantiator.Instantiator.from_designspace(
        designspace, round_geometry=True
    )

    with caplog.at_level(logging.WARNING):
        instance_font = generator.generate_instance(designspace.instances[0])
    assert "missing the stylename attribute" in caplog.text

    assert instance_font.info.familyName == "MyFont"
    assert instance_font.info.styleName == "Light"
    assert instance_font.info.postscriptFontName is None
    assert instance_font.info.styleMapFamilyName is None
    assert instance_font.info.styleMapStyleName is None


def test_axis_mapping(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "DesignspaceTest" / "DesignspaceTest-wght-wdth.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    generator = ufo2ft.instantiator.Instantiator.from_designspace(
        designspace, round_geometry=True
    )

    instance_font = generator.generate_instance(designspace.instances[0])
    assert instance_font.info.openTypeOS2WeightClass == 400
    assert instance_font.info.openTypeOS2WidthClass == 5
    assert instance_font.info.italicAngle is None
    assert instance_font.lib["designspace.location"] == [
        ("weight", 100.0),
        ("width", 100.0),
    ]


def test_axis_mapping_manual_os2_classes(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "DesignspaceTest" / "DesignspaceTest-wght-wdth.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    designspace.sources[0].font.info.openTypeOS2WeightClass = 800
    designspace.sources[0].font.info.openTypeOS2WidthClass = 7
    designspace.sources[1].font.info.openTypeOS2WeightClass = 900
    designspace.sources[1].font.info.openTypeOS2WidthClass = 9
    generator = ufo2ft.instantiator.Instantiator.from_designspace(
        designspace, round_geometry=True
    )

    instance_font = generator.generate_instance(designspace.instances[0])
    assert instance_font.info.openTypeOS2WeightClass == 850
    assert instance_font.info.openTypeOS2WidthClass == 8
    assert instance_font.info.italicAngle is None
    assert instance_font.lib["designspace.location"] == [
        ("weight", 100.0),
        ("width", 100.0),
    ]


def test_axis_mapping_no_os2_width_class_inference(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "DesignspaceTest" / "DesignspaceTest-bare.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    designspace.sources[0].font.info.openTypeOS2WeightClass = 800
    designspace.sources[1].font.info.openTypeOS2WeightClass = 900
    generator = ufo2ft.instantiator.Instantiator.from_designspace(
        designspace, round_geometry=True
    )

    instance_font = generator.generate_instance(designspace.instances[0])
    assert instance_font.info.openTypeOS2WeightClass == 850
    assert instance_font.info.openTypeOS2WidthClass is None
    assert instance_font.info.italicAngle is None
    assert instance_font.lib["designspace.location"] == [("weight", 100.0)]


def test_axis_mapping_no_os2_class_inference(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "DesignspaceTest" / "DesignspaceTest-opsz.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    generator = ufo2ft.instantiator.Instantiator.from_designspace(
        designspace, round_geometry=True
    )

    instance_font = generator.generate_instance(designspace.instances[0])
    assert instance_font.info.openTypeOS2WeightClass is None
    assert instance_font.info.openTypeOS2WidthClass is None
    assert instance_font.info.italicAngle is None
    assert instance_font.lib["designspace.location"] == [("optical", 15.0)]


def test_axis_mapping_italicAngle_inference(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "DesignspaceTest" / "DesignspaceTest-slnt.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    generator = ufo2ft.instantiator.Instantiator.from_designspace(
        designspace, round_geometry=True
    )

    instance_font = generator.generate_instance(designspace.instances[0])
    assert instance_font.info.openTypeOS2WeightClass is None
    assert instance_font.info.openTypeOS2WidthClass is None
    assert instance_font.info.italicAngle == 40.123
    assert instance_font.lib["designspace.location"] == [("slant", 40.123)]


def test_lib_into_instance(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "DesignspaceTest" / "DesignspaceTest-lib.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    generator = ufo2ft.instantiator.Instantiator.from_designspace(
        designspace, round_geometry=True
    )

    assert designspace.default.font.lib["blorb"] == "asasa"
    assert "public.skipExportGlyphs" not in designspace.sources[0].font.lib

    instance_font = generator.generate_instance(designspace.instances[0])
    assert instance_font.lib["blorb"] == "asasa"
    assert instance_font.lib["public.skipExportGlyphs"] == ["a", "b", "c"]

    instance_font2 = generator.generate_instance(designspace.instances[1])
    assert instance_font2.lib["blorb"] == "asasa"
    assert instance_font2.lib["public.skipExportGlyphs"] == ["a", "b", "c"]


def test_data_independence(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "DesignspaceTest" / "DesignspaceTest.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    generator = ufo2ft.instantiator.Instantiator.from_designspace(
        designspace, round_geometry=True
    )
    instance_font1 = generator.generate_instance(designspace.instances[0])
    designspace.instances[0].lib["aaaaaaaa"] = 1
    instance_font2 = generator.generate_instance(designspace.instances[0])

    instance_font1["l"].unicodes.append(2)
    assert instance_font1["l"].unicodes == [0x6C, 2]
    assert instance_font2["l"].unicodes == [0x6C]

    instance_font1["l"].lib["asdf"] = 1
    assert instance_font1["l"].lib == {"asdf": 1}
    assert not instance_font2["l"].lib

    generator.copy_lib["sdjkhsjdhjdf"] = 1
    instance_font1.lib["asdf"] = 1
    assert instance_font1.lib == {
        "asdf": 1,
        "blorb": "asasa",
        "designspace.location": [("weight", 100.0)],
        "public.skipExportGlyphs": [],
    }
    assert instance_font2.lib == {
        "blorb": "asasa",
        "designspace.location": [("weight", 100.0)],
        "public.skipExportGlyphs": [],
    }

    assert generator.copy_info.openTypeOS2Panose == [2, 11, 5, 4, 2, 2, 2, 2, 2, 4]
    generator.copy_info.openTypeOS2Panose.append(1000)
    assert instance_font1.info.openTypeOS2Panose is None
    assert instance_font2.info.openTypeOS2Panose is None

    # copy_feature_text not tested because it is a(n immutable) string

    assert not generator.skip_export_glyphs
    generator.skip_export_glyphs.extend(["a", "b"])
    assert not instance_font1.lib["public.skipExportGlyphs"]
    assert not instance_font2.lib["public.skipExportGlyphs"]
    instance_font1.lib["public.skipExportGlyphs"].append("z")
    assert not instance_font2.lib["public.skipExportGlyphs"]


def test_skipped_fontinfo_attributes():
    """Test that we consider all available font info attributes for copying."""
    import fontMath.mathInfo
    import fontTools.ufoLib

    SKIPPED_ATTRS = {
        "guidelines",
        "macintoshFONDFamilyID",
        "macintoshFONDName",
        "openTypeNameCompatibleFullName",
        "openTypeNamePreferredFamilyName",
        "openTypeNamePreferredSubfamilyName",
        "openTypeNameUniqueID",
        "openTypeNameWWSFamilyName",
        "openTypeNameWWSSubfamilyName",
        "openTypeOS2Panose",
        "postscriptFontName",
        "postscriptFullName",
        "postscriptUniqueID",
        "styleMapFamilyName",
        "styleMapStyleName",
        "styleName",
        "woffMetadataUniqueID",
        "year",
    }

    assert (
        fontTools.ufoLib.fontInfoAttributesVersion3
        - set(fontMath.mathInfo._infoAttrs.keys())
        - {"postscriptWeightName"}  # Handled in fontMath specially.
        - ufo2ft.instantiator.UFO_INFO_ATTRIBUTES_TO_COPY_TO_INSTANCES
        == SKIPPED_ATTRS
    )


def test_designspace_v5_discrete_axis_raises_error(data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "MutatorSansLite" / "MutatorFamily_v5_discrete_axis.designspace"
    )
    # The error message should advise to use `splitInterpolable()`
    with pytest.raises(
        ufo2ft.instantiator.InstantiatorError, match="splitInterpolable"
    ):
        ufo2ft.instantiator.Instantiator.from_designspace(designspace)


def test_strict_math_glyph(ufo_module, data_dir):
    designspace = designspaceLib.DesignSpaceDocument.fromfile(
        data_dir / "InstantiatorStrictMathGlyph" / "StrictMathGlyph.designspace"
    )
    designspace.loadSourceFonts(openFontFactory(ufo_module=ufo_module))
    generator = ufo2ft.instantiator.Instantiator.from_designspace(
        designspace, round_geometry=True
    )
    fonts = [
        generator.generate_instance(instance) for instance in designspace.instances
    ]
    assert len(fonts) == 1
    glyph = fonts[0]["test"]
    assert len(glyph.contours) == 1
    assert len(glyph.contours[0].points) == 16
