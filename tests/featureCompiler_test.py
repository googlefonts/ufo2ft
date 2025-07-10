import logging
import re
from textwrap import dedent

import py
import pytest
from fontTools import ttLib
from fontTools.feaLib.error import FeatureLibError, IncludedFeaNotFound

from ufo2ft.featureCompiler import (
    FeatureCompiler,
    logger,
    parseLayoutFeatures,
    tokenizeLayoutFeatures,
)
from ufo2ft.featureWriters import (
    FEATURE_WRITERS_KEY,
    BaseFeatureWriter,
    KernFeatureWriter,
    ast,
)


class ParseLayoutFeaturesTest:
    def test_include(self, FontClass, tmpdir):
        tmpdir.join("test.fea").write_text(
            dedent(
                """\
            # hello world
            """
            ),
            encoding="utf-8",
        )
        ufo = FontClass()
        ufo.features.text = dedent(
            """\
            include(test.fea)
            """
        )
        ufo.save(str(tmpdir.join("Test.ufo")))

        fea = parseLayoutFeatures(ufo)

        assert "# hello world" in str(fea)

    def test_include_no_ufo_path(self, FontClass, tmpdir, monkeypatch):
        ufo = FontClass()
        ufo.features.text = dedent(
            """\
            include(test.fea)
            """
        )
        with monkeypatch.context() as context:
            context.chdir(str(tmpdir))
            ufo.save("Test.ufo")
            with pytest.raises(IncludedFeaNotFound):
                parseLayoutFeatures(ufo)

    def test_include_not_found(self, FontClass, tmpdir, caplog):
        caplog.set_level(logging.ERROR)

        tmpdir.join("test.fea").write_text(
            dedent(
                """\
            # hello world
            """
            ),
            encoding="utf-8",
        )
        ufo = FontClass()
        ufo.features.text = dedent(
            """\
            include(../test.fea)
            """
        )
        ufo.save(str(tmpdir.join("Test.ufo")))

        with caplog.at_level(logging.WARNING, logger=logger.name):
            with pytest.raises(IncludedFeaNotFound):
                parseLayoutFeatures(ufo)

        assert len(caplog.records) == 1
        assert "change the file name in the include" in caplog.text

    def test_include_dir(self, FontClass, tmp_path, caplog):
        features_dir = tmp_path / "features"
        features_dir.mkdir()
        (features_dir / "test.fea").write_text(
            dedent(
                """\
                # hello world
                """
            ),
            encoding="utf-8",
        )
        ufo = FontClass()
        ufo.features.text = dedent(
            """\
            include(test.fea)
            """
        )
        ufo.save(tmp_path / "Test.ufo")

        fea = parseLayoutFeatures(ufo, features_dir)

        assert "# hello world" in str(fea)

    def test_include_dir_cwd(self, FontClass, tmp_path, monkeypatch):
        (tmp_path / "test.fea").write_text("# hello world", encoding="utf-8")
        ufo = FontClass()
        ufo.features.text = "include(test.fea)"

        with monkeypatch.context() as context:
            context.chdir(tmp_path)
            ufo.save("Test.ufo")
            fea = parseLayoutFeatures(ufo)

        assert "# hello world" in str(fea)


class TokenizeLayoutFeaturesTest:
    def tokenize(self, ufo, includeDir=None):
        return [tok for _, tok in tokenizeLayoutFeatures(ufo, includeDir=includeDir)]

    def test_include(self, FontClass, tmp_path):
        (tmp_path / "test.fea").write_text(
            dedent(
                """\
            # hello world
            feature kern {
                pos A V -40;
            } kern;
            """
            ),
            encoding="utf-8",
        )
        ufo = FontClass()
        ufo.features.text = dedent(
            """\
            include(test.fea)
            """
        )
        ufo.save(tmp_path / "Test.ufo")

        assert self.tokenize(ufo) == [
            "feature",
            "kern",
            "{",
            "pos",
            "A",
            "V",
            -40,
            ";",
            "}",
            "kern",
            ";",
        ]

    def test_include_does_not_exist(self, FontClass, tmp_path, monkeypatch):
        ufo = FontClass()
        ufo.features.text = dedent(
            """\
            include(test.fea)
            """
        )
        with monkeypatch.context() as context:
            context.chdir(tmp_path)
            ufo.save("Test.ufo")
            with pytest.raises(IncludedFeaNotFound):
                tokenizeLayoutFeatures(ufo)

    def test_include_no_ufo_path_nor_include_dir(self, FontClass, tmp_path):
        ufo = FontClass()
        ufo.features.text = dedent(
            """\
            include(test.fea)
            """
        )
        assert ufo.path is None
        with pytest.raises(IncludedFeaNotFound):
            tokenizeLayoutFeatures(ufo, includeDir=None)

    def test_include_not_found_with_warning(self, FontClass, tmp_path, caplog):
        caplog.set_level(logging.ERROR)

        (tmp_path / "test.fea").write_text(
            dedent(
                """\
            # hello world
            """
            ),
            encoding="utf-8",
        )
        ufo = FontClass()
        ufo.features.text = dedent(
            """\
            include(../test.fea)
            """
        )
        ufo.save(tmp_path / "Test.ufo")

        # the included 'test.fea' is in the same directory as the ufo, but the include
        # statement appears to be relative to the inner ufo/features.fea, treating ufo as
        # if it were a directory. The spec wants include paths to be relative to the ufo
        # itself as a whole, hence we expect the include error plus a warning
        with caplog.at_level(logging.WARNING, logger=logger.name):
            with pytest.raises(IncludedFeaNotFound):
                tokenizeLayoutFeatures(ufo)

        assert len(caplog.records) == 1
        assert "change the file name in the include" in caplog.text

    def test_include_dir(self, FontClass, tmp_path, caplog):
        features_dir = tmp_path / "features"
        features_dir.mkdir()
        (features_dir / "test.fea").write_text(
            dedent(
                """\
                # hello world
                feature kern {
                    pos A V -40;
                } kern;
                """
            ),
            encoding="utf-8",
        )
        ufo = FontClass()
        ufo.features.text = dedent(
            """\
            include(test.fea)
            """
        )
        ufo.save(tmp_path / "Test.ufo")

        assert self.tokenize(ufo, includeDir=features_dir) == [
            "feature",
            "kern",
            "{",
            "pos",
            "A",
            "V",
            -40,
            ";",
            "}",
            "kern",
            ";",
        ]

    def test_include_dir_defaults_to_cwd(self, FontClass, tmp_path, monkeypatch):
        (tmp_path / "test.fea").write_text("# hello world", encoding="utf-8")
        ufo = FontClass()
        ufo.features.text = "include(test.fea)"

        with monkeypatch.context() as context:
            context.chdir(tmp_path)
            # even without ufo.path or an explicit includeDir, we expect no exceptions
            # because we cd to test.fea's directory.
            # (result is empty because comments are ignored)
            assert ufo.path is None
            assert self.tokenize(ufo) == []


class DummyFeatureWriter:
    tableTag = "GPOS"

    def write(self, font, feaFile, compiler=None):
        pass


class FeatureCompilerTest:
    def test_ttFont(self, FontClass):
        ufo = FontClass()
        ufo.newGlyph("f")
        ufo.newGlyph("f_f")
        ufo.features.text = dedent(
            """\
            feature liga {
                sub f f by f_f;
            } liga;
            """
        )
        ttFont = ttLib.TTFont()
        ttFont.setGlyphOrder(["f", "f_f"])

        compiler = FeatureCompiler(ufo, ttFont)
        compiler.compile()

        assert "GSUB" in ttFont

        gsub = ttFont["GSUB"].table
        assert gsub.FeatureList.FeatureCount == 1
        assert gsub.FeatureList.FeatureRecord[0].FeatureTag == "liga"

    def test_ttFont_None(self, FontClass):
        ufo = FontClass()
        ufo.newGlyph("f")
        ufo.newGlyph("f_f")
        ufo.features.text = dedent(
            """\
            feature liga {
                sub f f by f_f;
            } liga;
            """
        )

        compiler = FeatureCompiler(ufo)
        ttFont = compiler.compile()

        assert "GSUB" in ttFont

        gsub = ttFont["GSUB"].table
        assert gsub.FeatureList.FeatureCount == 1
        assert gsub.FeatureList.FeatureRecord[0].FeatureTag == "liga"

    def test_deprecated_methods(self, FontClass):
        compiler = FeatureCompiler(FontClass())
        with pytest.warns(UserWarning, match="method is deprecated"):
            compiler.setupFile_features()

        compiler.features = ""
        with pytest.warns(UserWarning, match="method is deprecated"):
            compiler.setupFile_featureTables()

        class UserCompiler(FeatureCompiler):
            def setupFile_features(self):
                self.features = "# hello world"

            def setupFile_featureTables(self):
                self.ttFont = ttLib.TTFont()

        compiler = UserCompiler(FontClass())
        with pytest.warns(UserWarning, match="method is deprecated"):
            compiler.compile()

    def test_deprecated_mtiFeatures_argument(self, FontClass):
        with pytest.warns(UserWarning, match="argument is ignored"):
            FeatureCompiler(FontClass(), mtiFeatures="whatever")

    def test_featureWriters_empty(self, FontClass):
        kernWriter = KernFeatureWriter(ignoreMarks=False)
        ufo = FontClass()
        ufo.newGlyph("a")
        ufo.newGlyph("v")
        ufo.kerning.update({("a", "v"): -40})
        compiler = FeatureCompiler(ufo, featureWriters=[kernWriter])
        ttFont1 = compiler.compile()
        assert "GPOS" in ttFont1

        compiler = FeatureCompiler(ufo, featureWriters=[])
        ttFont2 = compiler.compile()
        assert "GPOS" not in ttFont2

    def test_loadFeatureWriters_from_UFO_lib(self, FontClass):
        ufo = FontClass()
        ufo.newGlyph("a")
        ufo.newGlyph("v")
        ufo.kerning.update({("a", "v"): -40})
        ufo.lib[FEATURE_WRITERS_KEY] = [{"class": "KernFeatureWriter"}]
        compiler = FeatureCompiler(ufo)
        ttFont = compiler.compile()

        assert len(compiler.featureWriters) == 1
        assert isinstance(compiler.featureWriters[0], KernFeatureWriter)
        assert "GPOS" in ttFont

    def test_loadFeatureWriters_from_both_UFO_lib_and_argument(self, FontClass):
        ufo = FontClass()
        ufo.lib[FEATURE_WRITERS_KEY] = [{"class": "KernFeatureWriter"}]
        compiler = FeatureCompiler(ufo, featureWriters=[..., DummyFeatureWriter])

        assert len(compiler.featureWriters) == 2
        assert isinstance(compiler.featureWriters[0], KernFeatureWriter)
        assert isinstance(compiler.featureWriters[1], DummyFeatureWriter)

    def test_loadFeatureWriters_from_both_defaults_and_argument(self, FontClass):
        ufo = FontClass()
        compiler = FeatureCompiler(ufo, featureWriters=[DummyFeatureWriter, ...])

        assert len(compiler.featureWriters) == 1 + len(
            FeatureCompiler.defaultFeatureWriters
        )
        assert isinstance(compiler.featureWriters[0], DummyFeatureWriter)

    def test_GSUB_writers_run_first(self, FontClass):
        class FooFeatureWriter(BaseFeatureWriter):
            tableTag = "GSUB"

            def write(self, font, feaFile, compiler=None):
                foo = ast.FeatureBlock("FOO ")
                foo.statements.append(
                    ast.SingleSubstStatement(
                        [ast.GlyphName("a")],
                        [ast.GlyphName("v")],
                        prefix="",
                        suffix="",
                        forceChain=None,
                    )
                )
                feaFile.statements.append(foo)

        featureWriters = [KernFeatureWriter, FooFeatureWriter]

        ufo = FontClass()
        ufo.newGlyph("a")
        ufo.newGlyph("v")
        ufo.kerning.update({("a", "v"): -40})

        compiler = FeatureCompiler(ufo, featureWriters=featureWriters)

        assert len(compiler.featureWriters) == 2
        assert compiler.featureWriters[0].tableTag == "GSUB"
        assert compiler.featureWriters[1].tableTag == "GPOS"

        ttFont = compiler.compile()

        assert "GSUB" in ttFont

        gsub = ttFont["GSUB"].table
        assert gsub.FeatureList.FeatureCount == 1
        assert gsub.FeatureList.FeatureRecord[0].FeatureTag == "FOO "

    def test_buildTables_FeatureLibError(self, FontClass, caplog):
        caplog.set_level(logging.CRITICAL)

        ufo = FontClass()
        ufo.newGlyph("f")
        ufo.newGlyph("f.alt01")
        ufo.newGlyph("f.alt02")
        ufo.newGlyph("f_f")
        features = dedent(
            """\
            feature BUGS {
                # invalid
                lookup MIXED_TYPE {
                    sub f by f.alt01;
                    sub f from [f.alt01 f.alt02];
                } MIXED_TYPE;

            } BUGS;
            """
        )
        ufo.features.text = features

        compiler = FeatureCompiler(ufo)

        tmpfile = None
        try:
            with caplog.at_level(logging.ERROR, logger=logger.name):
                with pytest.raises(FeatureLibError):
                    compiler.compile()

            assert len(caplog.records) == 1
            assert "Compilation failed! Inspect temporary file" in caplog.text

            tmpfile = py.path.local(re.findall(".*: '(.*)'$", caplog.text)[0])

            assert tmpfile.exists()
            assert tmpfile.read_text("utf-8") == features
        finally:
            if tmpfile is not None:
                tmpfile.remove(ignore_errors=True)

    def test_setupFeatures_custom_feaIncludeDir(self, FontClass, tmp_path):
        (tmp_path / "family.fea").write_text(
            """\
            feature liga {
                sub f f by f_f;
            } liga;
            """
        )
        ufo = FontClass()
        ufo.newGlyph("a")
        ufo.newGlyph("v")
        ufo.newGlyph("f")
        ufo.newGlyph("f_f")
        ufo.kerning.update({("a", "v"): -40})
        ufo.features.text = dedent(
            """\
            include(family.fea);
            """
        )
        compiler = FeatureCompiler(ufo, feaIncludeDir=str(tmp_path))

        compiler.setupFeatures()

        assert compiler.features == dedent(
            """\
            feature liga {
                sub f f by f_f;
            } liga;

            lookup kern_Default {
                lookupflag IgnoreMarks;
                pos a v -40;
            } kern_Default;

            feature kern {
                script DFLT;
                language dflt;
                lookup kern_Default;
            } kern;
            """
        )
