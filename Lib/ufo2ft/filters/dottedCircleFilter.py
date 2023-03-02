"""This is a redirection stub, because the original module was
misnamed."""

import warnings

from .dottedCircle import DottedCircleFilter  # noqa

warnings.warn(
    "The dottedCircleFilter module is deprecated, please import dottedCircle instead.",
    UserWarning,
    stacklevel=1,
)
