#!/usr/bin/env python

from __future__ import print_function, division, absolute_import
from setuptools import setup

try:
    import fontTools
except:
    print("*** Warning: ufo2ft requires FontTools, see:")
    print("    fonttools.sf.net")

try:
    import ufoLib
except:
    print("*** Warning: ufo2ft requires ufoLib, see:")
    print("    https://github.com/unified-font-object/ufoLib")


setup(name="ufo2ft",
    version="0.1",
    description="A bridge between UFOs and FontTools.",
    author="Tal Leming",
    author_email="tal@typesupply.com",
    url="http://code.typesupply.com",
    license="MIT",
    packages=["ufo2ft"],
    package_dir={"":"Lib"}
)
