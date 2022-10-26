from __future__ import annotations

from ufo2ft.featureWriters.kernFeatureWriter import KerningPair, split_kerning


def test_split_basic() -> None:
    pairs = [
        KerningPair(["a"], ["a"], 20, scripts={"Latn"}),
        KerningPair(["a"], ["period"], 20, scripts={"Latn"}),
        KerningPair(["period"], ["a"], 20, scripts={"Latn"}),
        KerningPair(["period"], ["period"], 20, scripts={"Zyyy"}),
    ]
    glyphScripts = {
        "a": {"Latn"},
        "period": {"Zyyy"},
    }
    kerning_per_script = split_kerning(pairs, glyphScripts)
    assert kerning_per_script == {
        "Latn": [
            KerningPair(["a"], ["a"], 20, scripts={"Latn"}),
            KerningPair(["a"], ["period"], 20, scripts={"Latn"}),
            KerningPair(["period"], ["a"], 20, scripts={"Latn"}),
        ],
        "Zyyy": [
            KerningPair(["period"], ["period"], 20, scripts={"Zyyy"}),
        ],
    }


def test_split_basic_explicit_and_implicit_script() -> None:
    pairs = [
        KerningPair(["a"], ["a"], 20, scripts={"Latn"}),
        KerningPair(["a"], ["period"], 20, scripts={"Latn"}),
        KerningPair(["period"], ["a"], 20, scripts={"Latn"}),
        KerningPair(["period"], ["period"], 20, scripts={"Zyyy"}),
    ]
    glyphScripts = {
        "a": {"Latn"},
        "period": {"Latn", "Zyyy"},
    }
    kerning_per_script = split_kerning(pairs, glyphScripts)
    assert kerning_per_script == {
        "Latn": [
            KerningPair(["a"], ["a"], 20, scripts={"Latn"}),
            KerningPair(["a"], ["period"], 20, scripts={"Latn"}),
            KerningPair(["period"], ["a"], 20, scripts={"Latn"}),
            KerningPair(["period"], ["period"], 20, scripts={"Latn"}),
        ],
        "Zyyy": [
            KerningPair(["period"], ["period"], 20, scripts={"Zyyy"}),
        ],
    }


def test_split_multi_glyph_class() -> None:
    pairs = [
        # Glyph-to-glyph
        KerningPair("a", "a", 1, scripts={"Latn"}),
        KerningPair("a", "b", 2, scripts={"Latn"}),
        KerningPair("a", "something", 3, scripts={"Latn"}),
        KerningPair("b", "a", 4, scripts={"Latn"}),
        KerningPair("b", "b", 5, scripts={"Latn"}),
        KerningPair("b", "something", 6, scripts={"Latn"}),
        KerningPair("something", "a", 7, scripts={"Latn"}),
        KerningPair("something", "b", 8, scripts={"Latn"}),
        KerningPair("something", "something", 9, scripts={"Zyyy"}),
        # Class-to-glyph
        KerningPair(["a", "something"], "b", 10, scripts={"Latn"}),
        KerningPair(["a", "something"], "something", 11, scripts={"Latn"}),
        # Glyph-to-class
        KerningPair("a", ["b", "something"], 12, scripts={"Latn"}),
        KerningPair("something", ["b", "something"], 13, scripts={"Latn"}),
        # Class-to-class
        KerningPair(["a", "something"], ["b", "something"], 14, scripts={"Latn"}),
    ]
    glyphScripts = {
        "a": {"Latn"},
        "b": {"Latn"},
        "something": {"Zyyy"},
    }
    kerning_per_script = split_kerning(pairs, glyphScripts)
    assert kerning_per_script == {
        "Latn": [
            KerningPair("a", "a", 1, scripts={"Latn"}),
            KerningPair("a", "b", 2, scripts={"Latn"}),
            KerningPair("a", "something", 3, scripts={"Latn"}),
            KerningPair("b", "a", 4, scripts={"Latn"}),
            KerningPair("b", "b", 5, scripts={"Latn"}),
            KerningPair("b", "something", 6, scripts={"Latn"}),
            KerningPair("something", "a", 7, scripts={"Latn"}),
            KerningPair("something", "b", 8, scripts={"Latn"}),
            KerningPair("a", ["b"], 12, scripts={"Latn"}),
            KerningPair("a", ["something"], 12, scripts={"Latn"}),
            KerningPair("something", ["b"], 13, scripts={"Latn"}),
            KerningPair(["a"], "b", 10, scripts={"Latn"}),
            KerningPair(["a"], "something", 11, scripts={"Latn"}),
            KerningPair(["something"], "b", 10, scripts={"Latn"}),
            KerningPair(["a"], ["b"], 14, scripts={"Latn"}),
            KerningPair(["a"], ["something"], 14, scripts={"Latn"}),
            KerningPair(["something"], ["b"], 14, scripts={"Latn"}),
        ],
        "Zyyy": [
            KerningPair("something", "something", 9, scripts={"Zyyy"}),
            KerningPair("something", ["something"], 13, scripts={"Zyyy"}),
            KerningPair(["something"], "something", 11, scripts={"Zyyy"}),
            KerningPair(["something"], ["something"], 14, scripts={"Zyyy"}),
        ],
    }


def test_split_multi_explicit_and_implicit_script() -> None:
    pairs = [
        # Glyph-to-glyph
        KerningPair("a", "a", 1, scripts={"Latn"}),
        KerningPair("a", "b", 2, scripts={"Latn"}),
        KerningPair("a", "something", 3, scripts={"Latn"}),
        KerningPair("b", "a", 4, scripts={"Latn"}),
        KerningPair("b", "b", 5, scripts={"Latn"}),
        KerningPair("b", "something", 6, scripts={"Latn"}),
        KerningPair("something", "a", 7, scripts={"Latn"}),
        KerningPair("something", "b", 8, scripts={"Latn"}),
        KerningPair("something", "something", 9, scripts={"Zyyy"}),
        # Class-to-glyph
        KerningPair(["a", "something"], "b", 10, scripts={"Latn"}),
        KerningPair(["a", "something"], "something", 11, scripts={"Latn"}),
        # Glyph-to-class
        KerningPair("a", ["b", "something"], 12, scripts={"Latn"}),
        KerningPair("something", ["b", "something"], 13, scripts={"Latn"}),
        # Class-to-class
        KerningPair(["a", "something"], ["b", "something"], 14, scripts={"Latn"}),
    ]
    glyphScripts = {
        "a": {"Latn"},
        "b": {"Latn"},
        "something": {"Latn", "Zyyy"},
    }
    kerning_per_script = split_kerning(pairs, glyphScripts)
    assert kerning_per_script == {
        # TODO
    }


def test_weird_split3() -> None:
    pairs = [
        KerningPair(["a"], ["something"], 20, scripts={"Latn"}),
        KerningPair(["something"], ["a"], 20, scripts={"Latn"}),
    ]
    glyphScripts = {
        "a": {"Latn"},
        "something": {"Arab", "Zyyy"},
    }
    kerning_per_script = split_kerning(pairs, glyphScripts)
    assert kerning_per_script == {
        "Latn": [
            KerningPair(["a"], ["something"], 20, scripts={"Latn"}),
            KerningPair(["something"], ["a"], 20, scripts={"Latn"}),
        ]
    }


def test_weird_split4() -> None:
    pairs = [
        KerningPair(["a"], ["b"], 20, scripts={"Zyyy"}),
        KerningPair(["b"], ["a"], 20, scripts={"Zyyy"}),
    ]
    glyphScripts = {
        "a": {"Zyyy"},
        "b": {"Zyyy"},
    }
    kerning_per_script = split_kerning(pairs, glyphScripts)
    assert kerning_per_script == {
        "Zyyy": [
            KerningPair(["a"], ["b"], 20, scripts={"Zyyy"}),
            KerningPair(["b"], ["a"], 20, scripts={"Zyyy"}),
        ]
    }


def test_weird_split7() -> None:
    pairs = [
        KerningPair(
            ["a", "delta", "danda"], ["a-cy", "arabic", "period"], 20, scripts={"Latn"}
        ),
        KerningPair(
            ["a-cy", "arabic", "period"], ["a", "delta", "danda"], 20, scripts={"Latn"}
        ),
    ]
    glyphScripts = {
        "a": {"Latn"},
        "delta": {"Grek"},
        "danda": {"Odia"},
        "a-cy": {"Cyrl"},
        "arabic": {"Arab"},
        "period": {"Zyyy"},
    }
    kerning_per_script = split_kerning(pairs, glyphScripts)
    assert kerning_per_script == {
        "Grek": [
            KerningPair(["delta"], ["period"], 20, scripts={"Grek"}),
            KerningPair(["period"], ["delta"], 20, scripts={"Grek"}),
        ],
        "Latn": [
            KerningPair(["a"], ["period"], 20, scripts={"Latn"}),
            KerningPair(["period"], ["a"], 20, scripts={"Latn"}),
        ],
        "Odia": [
            KerningPair(["danda"], ["period"], 20, scripts={"Odia"}),
            KerningPair(["period"], ["danda"], 20, scripts={"Odia"}),
        ],
    }


def test_weird_split8() -> None:
    pairs = [
        KerningPair(["A-cy", "increment"], "Che-cy", 20, scripts={"Cyrl", "Zyyy"}),
        KerningPair(["A-cy", "increment"], "backslash", 20, scripts={"Cyrl", "Zyyy"}),
    ]
    glyphScripts = {
        "A-cy": {"Cyrl"},
        "Che-cy": {"Cyrl"},
        "increment": {"Zyyy"},
        "backslash": {"Zyyy"},
    }
    kerning_per_script = split_kerning(pairs, glyphScripts)
    assert kerning_per_script == {
        "Cyrl": [
            KerningPair(["A-cy"], "Che-cy", 20, scripts={"Cyrl"}),
            KerningPair(["A-cy"], "backslash", 20, scripts={"Cyrl"}),
        ],
        "Zyyy": [
            KerningPair(["increment"], "backslash", 20, scripts={"Zyyy"}),
        ],
    }
