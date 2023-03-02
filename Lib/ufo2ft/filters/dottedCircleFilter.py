"""This is a redirection stub, because the original module was
misnamed."""

import warnings

from .dottedCircle import DottedCircleFilter  # noqa

warnings.warn(
    "Please update your filter name from `DottedCircleFilter` to " "`dottedCircle`.",
    UserWarning,
    stacklevel=1,
)
