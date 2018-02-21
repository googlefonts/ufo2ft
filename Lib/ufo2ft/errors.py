
class Error(Exception):
    """Base exception class for all ufo2ft errors."""
    pass


class InvalidFontData(Error):
    """Raised when input font contains invalid data."""
    pass
