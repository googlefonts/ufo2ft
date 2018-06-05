from __future__ import (
    print_function,
    division,
    absolute_import,
    unicode_literals,
)
from textwrap import dedent
import logging
from fontTools.feaLib.error import IncludedFeaNotFound
from ufo2ft.featureCompiler import (
    FeatureCompiler,
    MtiFeatureCompiler,
    parseLayoutFeatures,
)
import pytest
from .testSupport import pushd


class ParseLayoutFeaturesTest(object):

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

    def test_include_no_ufo_path(self, FontClass, tmpdir):
        ufo = FontClass()
        ufo.features.text = dedent(
            """\
            include(test.fea)
            """
        )
        with pushd(str(tmpdir)):
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

        logger = "ufo2ft.featureCompiler"
        with caplog.at_level(logging.WARNING, logger=logger):
            with pytest.raises(IncludedFeaNotFound):
                parseLayoutFeatures(ufo)

        assert len(caplog.records) == 1
        assert "change the file name in the include" in caplog.text
