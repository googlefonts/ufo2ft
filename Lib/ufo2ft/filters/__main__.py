import argparse
import importlib
import logging

from fontTools.misc.cliTools import makeOutputFileName

from ufo2ft.filters import getFilterClass, loadFilterFromString, logger

try:
    import ufoLib2

    loader = ufoLib2.Font
except ImportError:
    import defcon

    loader = defcon.Font

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

ufo = loader(args.ufo)

filterargs = ""
if args.include:
    filterargs = "(include=%s)" % ",".join(
        ['"%s"' % g for g in args.include.split(",")]
    )
if args.exclude:
    filterargs = "(exclude=%s)" % ",".join(
        ['"%s"' % g for g in args.exclude.split(",")]
    )


for filtername in args.filters:
    f = loadFilterFromString(filtername + filterargs)
    f(ufo)

logger.info("Written on %s" % args.output)
ufo.save(args.output)
