import argparse
import importlib
import logging

import defcon
from fontTools.misc.cliTools import makeOutputFileName

from ufo2ft.filters import getFilterClass, logger

logging.basicConfig(level=logging.INFO)

parser = argparse.ArgumentParser(description="Filter a UFO file")
parser.add_argument("--output", "-o", metavar="OUTPUT", help="output file name")
parser.add_argument(
    "--include", metavar="GLYPHS", help="comma-separated list of glyphs to filter"
)
parser.add_argument(
    "--exclude", metavar="GLYPHS", help="comma-separated list of glyphs to not filter"
)
parser.add_argument("ufo", metavar="UFO", help="UFO file")
parser.add_argument("filters", metavar="FILTER", nargs="+", help="filter name")

args = parser.parse_args()
if not args.output:
    args.output = makeOutputFileName(args.ufo)

ufo = defcon.Font(args.ufo)

filterargs = {}
if args.include:
    filterargs["include"] = args.include.split(",")
if args.exclude:
    filterargs["exclude"] = args.exclude.split(",")


for filtername in args.filters:
    try:
        if "." in filtername:
            module = importlib.import_module(filtername)
            shortfiltername = (filtername.split("."))[-1]
            className = shortfiltername[0].upper() + shortfiltername[1:] + "Filter"
            f = getattr(module, className)(**filterargs)
        else:
            f = getFilterClass(filtername)(**filterargs)
    except Exception as e:
        raise ValueError("Couldn't find filter %s: %s" % (filtername, e))
    f(ufo)

logger.info("Written on %s" % args.output)
ufo.save(args.output)
