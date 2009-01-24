import sys
import os
import subprocess
import tempfile

# ----------------
# Public Functions
# ----------------

def haveFDK():
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
    return True

def makeotf(outputPath, outlineSourcePath=None, featuresPath=None, glyphOrderPath=None, menuNamePath=None, releaseMode=False):
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
    cmds = ["autohint", "-nb", "-a", "-r", "-q", fontPath]
    stderr, stdout = _execute(cmds)
    return stderr, stdout

def checkOutlines(fontPath, removeOverlap=True, correctContourDirection=True):
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

