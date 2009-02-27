#!/usr/bin/env python

from distutils.core import setup

try:
    import fontTools
except:
    print "*** Warning: ufo2fdk requires FontTools, see:"
    print "    fonttools.sf.net"

try:
    import robofab
except:
    print "*** Warning: ufo2fdk requires RoboFab, see:"
    print "    robofab.com"

setup(name="ufo2fdk",
    version="0.1",
    description="A bridge between UFOs and the AFKDO",
    author="Tal Leming",
    author_email="tal@typesupply.com",
    url="http://code.typesupply.com",
    license="MIT",
    packages=["ufo2fdk"],
    package_dir={"":"Lib"}
)