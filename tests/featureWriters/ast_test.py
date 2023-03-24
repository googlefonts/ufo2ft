from io import StringIO

from fontTools.feaLib.parser import Parser

from ufo2ft.featureWriters import ast


def test_iterClassDefinitions():
    text = """
    @TopLevelClass = [a b c];

    lookup test_lookup {
        @LookupLevelClass = [d e f];
    } test_lookup;

    feature test {
        @FeatureLevelClass = [g h i];

        lookup test_nested_lookup {
            @NestedLookupLevelClass = [j k l];
        } test_nested_lookup;
    } test;
    """
    glyph_names = "a b c d e f g h i j k l".split()
    feature_file = StringIO(text)
    p = Parser(feature_file, glyph_names)
    doc = p.parse()
    class_defs = ast.iterClassDefinitions(doc)
    result = [cd.name for cd in class_defs]
    expected = [
        "TopLevelClass",
        "LookupLevelClass",
        "FeatureLevelClass",
        "NestedLookupLevelClass",
    ]
    assert result == expected
