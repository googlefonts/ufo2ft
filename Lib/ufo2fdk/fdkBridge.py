import os
import subprocess
import time


def haveFDK():
    try:
        cmds = ["makeotf"]
        popen = subprocess.Popen(cmds, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        popen.wait()
        return True
    except OSError:
        return False

def _execute(cmds):
    popen = subprocess.Popen(cmds, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    popen.wait()
    stderr = popen.stderr.read()
    stdout = popen.stdout.read()
    return stderr, stdout

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
    return stderr, stdout # XXX this should probably parse and raise errors

def autohint(fontPath, ignoreExistingHints=True):
    cmds = ["autohint", "-nb"]
    if ignoreExistingHints:
        cmds.extend(["-a", "-r"])
    cmds.append(fontPath)
    stderr, stdout = _execute(cmds)
    return stderr, stdout # XXX this should probably parse and raise errors

def checkOutlines(fontPath):
    cmds = ["checkOutlines", "-e", fontPath]
    stderr, stdout = _execute(cmds)
    return stderr, stdout # XXX this should probably parse and raise errors

