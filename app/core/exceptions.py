"""Custom exception classes for the application."""


class AppError(Exception):
    """Base exception for application errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)


class AuthenticationError(AppError):
    """Authentication failed."""

    pass


class ValidationError(AppError):
    """Input validation failed."""

    pass


class QueueError(AppError):
    """Queue operation failed."""

    pass


class AppsFlyerError(AppError):
    """AppsFlyer API error."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        retryable: bool = False,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details)
        self.status_code = status_code
        self.retryable = retryable


class RateLimitError(AppError):
    """Rate limit exceeded."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after
