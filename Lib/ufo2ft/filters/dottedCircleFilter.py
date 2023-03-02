"""NOTE: This is a redirection stub, because the original module was misnamed.

It ended in "Filter", which messed with the assumptions in ``getFilterClass``.
Make an alias for the class here to steer the importer in the right
direction.
"""

import warnings

from .dottedCircle import DottedCircleFilter


class DottedCircleFilterFilter(DottedCircleFilter):
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "Please update your filter name from `DottedCircleFilter` to "
            "`dottedCircle`.",
            UserWarning,
            stacklevel=1,
        )
        super().__init__(*args, **kwargs)
