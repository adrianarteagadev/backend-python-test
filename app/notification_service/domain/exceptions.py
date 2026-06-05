class RequestNotFoundError(Exception):
    """Raised when a notification request cannot be found."""


class ProviderError(Exception):
    """Base provider integration error."""


class RetryableProviderError(ProviderError):
    """Raised for transient provider failures that can be retried."""


class NonRetryableProviderError(ProviderError):
    """Raised for provider failures that should not be retried."""
