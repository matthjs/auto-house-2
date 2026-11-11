"""
Errors shared by the site scrapers and the run loop.
"""


class SendError(RuntimeError):
    """
    Raised when a message to a landlord could not be delivered.
    """
