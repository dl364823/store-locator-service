"""
Custom exception hierarchy. Each maps to a specific HTTP status code.
Handlers in main.py convert these to consistent JSON error responses.
"""


class StoreLocatorError(Exception):
    status_code: int = 500
    default_code: str = "ERROR"

    def __init__(self, message: str, code: str | None = None):
        self.message = message
        self.code = code or self.default_code
        super().__init__(message)


class ValidationError(StoreLocatorError):
    status_code = 400
    default_code = "VALIDATION_ERROR"


class AuthenticationError(StoreLocatorError):
    status_code = 401
    default_code = "AUTHENTICATION_ERROR"


class AuthorizationError(StoreLocatorError):
    status_code = 403
    default_code = "AUTHORIZATION_ERROR"


class NotFoundError(StoreLocatorError):
    status_code = 404
    default_code = "NOT_FOUND"


class ConflictError(StoreLocatorError):
    status_code = 409
    default_code = "CONFLICT"


class RateLimitError(StoreLocatorError):
    status_code = 429
    default_code = "RATE_LIMIT_EXCEEDED"


class ExternalServiceError(StoreLocatorError):
    # 502 when an upstream dependency fails
    status_code = 502
    default_code = "EXTERNAL_SERVICE_ERROR"


class ServiceUnavailableError(StoreLocatorError):
    # 503 when a core dependency (DB) is unreachable
    status_code = 503
    default_code = "SERVICE_UNAVAILABLE"
