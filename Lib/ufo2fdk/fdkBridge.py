"""
This module is the bridge between Python and the FDK.
It uses subprocess.Popen to create a process that
executes an FDK program.
"""


import sys
import os
import re
import subprocess
import tempfile

# ----------------
# Public Functions
# ----------------


minMakeOTFVersion = (2, 0, 39)
minMakeOTFVersionRE = re.compile(
    "\s*"
    "makeotf"
    "\s+"
    "v"
    "(\d+)"
    "."
    "(\d+)"
    "."
    "(\d+)"
)


def haveFDK():
    """
    This will return a bool indicating if the FDK
    can be found. It searches for the FDK by using
    *which* to find the commandline *makeotf*,
    *checkoutlines* and *autohint* programs. If one
    of those cannot be found, this FDK is considered
    to be unavailable.
    """
    if _fdkToolDirectory is None:
        return False
    env = _makeEnviron()
    for tool in ["makeotf", "checkoutlines", "autohint"]:
        cmds = "which %s" % tool
        popen = subprocess.Popen(cmds, stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=env, shell=True)
        popen.wait()
        text = popen.stderr.read()
        text += popen.stdout.read()
        if not text:
            return False
    # now test to make sure that makeotf is new enough
    help = _execute(["makeotf", "-h"])[1]
    m = minMakeOTFVersionRE.match(help)
    if m is None:
        return False
    v1 = int(m.group(1))
    v2 = int(m.group(2))
    v3 = int(m.group(3))
    if (v1, v2, v3) < minMakeOTFVersion:
        return False
    return True

def makeotf(outputPath, outlineSourcePath=None, featuresPath=None, glyphOrderPath=None, menuNamePath=None, releaseMode=False):
    """
    Run makeotf.
    The arguments will be converted into arguments
    for makeotf as follows:

    =================  ===
    outputPath         -o
    outlineSourcePath  -f
    featuresPath       -ff
    glyphOrderPath     -gf
    menuNamePath       -mf
    releaseMode        -r
    =================  ===
    """
    cmds = ["makeotf", "-o", outputPath]
    if outlineSourcePath:
        cmds.extend(["-f", outlineSourcePath])
    if featuresPath:
        cmds.extend(["-ff", featuresPath])
    if glyphOrderPath:
        cmds.extend(["-gf", glyphOrderPath])
    if menuNamePath:
        cmds.extend(["-mf", menuNamePath])
    if releaseMode:
        cmds.append("-r")
    stderr, stdout = _execute(cmds)
    return stderr, stdout

def autohint(fontPath):
    """
    Run autohint.
    The following arguments will be passed to autohint.

    * -nb
    * -a
    * -r
    * -q
    """
    cmds = ["autohint", "-nb", "-a", "-r", "-q", fontPath]
    stderr, stdout = _execute(cmds)
    return stderr, stdout

def checkOutlines(fontPath, removeOverlap=True, correctContourDirection=True):
    """
    Run checkOutlines.
    The arguments will be converted into arguments
    for makeotf as follows:

    The following arguments will be passed to autohint.

    =============================  ===
    removeOverlap=False            -V
    correctContourDirection=False  -O
    =============================  ===

    Additionally, the following arguments will be passed to checkOutlines.

    * -e
    """
    cmds = ["checkoutlines", "-e"]
    if not removeOverlap:
        cmds.append("-V")
    if not correctContourDirection:
        cmds.append("-O")
    cmds.append(fontPath)
    stderr, stdout = _execute(cmds)
    return stderr, stdout

# --------------
# Internal Tools
# --------------

if sys.platform == "darwin":
    _fdkToolDirectory = os.path.join(os.environ["HOME"], "bin/FDK/Tools/osx")
else:
    _fdkToolDirectory = None

def _makeEnviron():
    env = dict(os.environ)
    if _fdkToolDirectory not in env["PATH"].split(":"):
        env["PATH"] += (":%s" % _fdkToolDirectory)
    kill = ["ARGVZERO", "EXECUTABLEPATH", "PYTHONHOME", "PYTHONPATH", "RESOURCEPATH"]
    for key in kill:
        if key in env:
            del env[key]
    return env

def _execute(cmds):
    # for some reason, autohint and/or checkoutlines
    # locks up when subprocess.PIPE is given. subprocess
    # requires a real file so StringIO is not acceptable
    # here. thus, make a temporary file.
    stderrPath = tempfile.mkstemp()[1]
    stdoutPath = tempfile.mkstemp()[1]
    stderrFile = open(stderrPath, "w")
    stdoutFile = open(stdoutPath, "w")
    # get the os.environ
    env = _makeEnviron()
    # make a string of escaped commands
    cmds = subprocess.list2cmdline(cmds)
    # go
    popen = subprocess.Popen(cmds, stderr=stderrFile, stdout=stdoutFile, env=env, shell=True)
    popen.wait()
    # get the output
    stderrFile.close()
    stdoutFile.close()
    stderrFile = open(stderrPath, "r")
    stdoutFile = open(stdoutPath, "r")
    stderr = stderrFile.read()
    stdout = stdoutFile.read()
    stderrFile.close()
    stdoutFile.close()
    # trash the temp files
    os.remove(stderrPath)
    os.remove(stdoutPath)
    # done
    return stderr, stdout

