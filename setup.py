#!/usr/bin/env python

from __future__ import print_function, division, absolute_import
import sys
from setuptools import setup, find_packages


needs_pytest = {"pytest", "test"}.intersection(sys.argv)
pytest_runner = ["pytest_runner"] if needs_pytest else []
needs_wheel = {"bdist_wheel"}.intersection(sys.argv)
wheel = ["wheel"] if needs_wheel else []

with open("README.rst", "r") as f:
    long_description = f.read()

setup(
    name="ufo2ft",
    use_scm_version={"write_to": "Lib/ufo2ft/_version.py"},
    author="Tal Leming, James Godfrey-Kittle",
    author_email="tal@typesupply.com",
    maintainer="Cosimo Lupo",
    maintainer_email="cosimo@anthrotype.com",
    description="A bridge between UFOs and FontTools.",
    long_description=long_description,
    url="https://github.com/googlefonts/ufo2ft",
    package_dir={"": "Lib"},
    packages=find_packages("Lib"),
    include_package_data=True,
    license="MIT",
    setup_requires=pytest_runner + wheel + ["setuptools_scm"],
    tests_require=["pytest>=2.8"],
    install_requires=[
        "fonttools[ufo]>=3.41.2",
        "defcon>=0.6.0",
        "cu2qu>=1.6.5",
        "compreffor>=0.4.6",
        "booleanOperations>=0.8.2",
        "enum34>=1.1.6 ; python_version < '3.4'",
    ],
    extras_require={"pathops": ["skia-pathops>=0.2.0"]},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Environment :: Other Environment",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
        "Topic :: Multimedia :: Graphics",
        "Topic :: Multimedia :: Graphics :: Graphics Conversion",
        "Topic :: Multimedia :: Graphics :: Editors :: Vector-Based",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
