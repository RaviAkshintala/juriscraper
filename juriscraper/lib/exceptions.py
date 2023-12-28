from juriscraper.lib.log_tools import make_default_logger


class JuriscraperException(Exception):
    """
    Base class for Juriscraper custom exceptions
    """

    logger = make_default_logger()


class SkipRowError(JuriscraperException):
    """
    Raise when a row or record has to be skipped
    For example, when collecting opinions and finding an order
    """

    def __init__(self, message: str):
        self.logger.debug(message)


class SlownessException(Exception):
    """Raised when things are too slow."""

    def __init__(self, message):
        Exception.__init__(self, message)


class ParsingException(Exception):
    """Raised when parsing fails."""

    def __init__(self, message):
        Exception.__init__(self, message)


class InsanityException(Exception):
    """Raised when data validation fails."""

    def __init__(self, message):
        Exception.__init__(self, message)


class PacerLoginException(Exception):
    """Raised when the system cannot authenticate with PACER"""

    def __init__(self, message):
        Exception.__init__(self, message)
