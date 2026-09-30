"""Domain errors raised by the service layer.

Services don't know about HTTP; main.py turns these into the standard
{"error": {"code", "message"}} response with the matching status code.
"""


class DomainError(Exception):
    status_code = 400

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class Invalid(DomainError):
    """Input that is well-formed but breaks a business rule (e.g. a past deadline)."""

    status_code = 422


class NotFound(DomainError):
    status_code = 404


class Forbidden(DomainError):
    status_code = 403


class Conflict(DomainError):
    status_code = 409
