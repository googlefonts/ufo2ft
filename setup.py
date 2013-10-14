#!/usr/bin/env python

import sys
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

if "sdist" in sys.argv:
    import os
    import subprocess
    import shutil
    docFolder = os.path.join(os.getcwd(), "documentation")
    # remove existing
    doctrees = os.path.join(docFolder, "build", "doctrees")
    if os.path.exists(doctrees):
        shutil.rmtree(doctrees)
    # compile
    p = subprocess.Popen(["make", "html"], cwd=docFolder)
    p.wait()
    # remove doctrees
    shutil.rmtree(doctrees)



setup(name="ufo2fdk",
    version="0.1",
    description="A bridge between UFOs and the AFKDO",
    author="Tal Leming",
    author_email="tal@typesupply.com",
    url="http://code.typesupply.com",
    license="MIT",
    packages=["ufo2fdk", "ufo2fdk.pens"],
    package_dir={"":"Lib"}
)
