"""NOTE: This is a redirection stub, because the original module was misnamed.

It ended in "Filter", which messed with the assumptions in ``getFilterClass``.
Make an alias for the class here to steer the importer in the right
direction.
"""

import logging

from .dottedCircle import DottedCircleFilter

LOGGER = logging.getLogger(__name__)


class DottedCircleFilterFilter(DottedCircleFilter):
    def __init__(self, *args, **kwargs):
        LOGGER.warning(
            "Please update your filter name from `DottedCircleFilter` to "
            "`dottedCircle`."
        )
        super().__init__(*args, **kwargs)
