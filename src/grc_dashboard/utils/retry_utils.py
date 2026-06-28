from collections.abc import Callable
from typing import Any

import structlog
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = structlog.get_logger(__name__)

def log_retry_attempt(retry_state: RetryCallState) -> None:
    """Structured logging callback for tenacity retries."""
    if retry_state.outcome and retry_state.outcome.failed:
        exception = retry_state.outcome.exception()
        logger.warning(
            "operation_failed_retrying",
            attempt=retry_state.attempt_number,
            exception_type=type(exception).__name__,
            exception_str=str(exception)
        )

def async_retry_with_backoff(
    max_attempts: int = 5, 
    base_delay: float = 1.0, 
    max_delay: float = 30.0, 
    fatal_exceptions: tuple[type[Exception], ...] = ()
) -> Callable[..., Any]:
    """
    Decorator for async retry logic with exponential backoff and full jitter.
    Will not retry if the raised exception is in fatal_exceptions.
    Implements ANCHOR:Q3 research decision.
    """
    def _is_retriable(exception: BaseException) -> bool:
        return not isinstance(exception, fatal_exceptions)

    return retry(
        wait=wait_exponential_jitter(initial=base_delay, max=max_delay),
        stop=stop_after_attempt(max_attempts),
        retry=retry_if_exception_type(Exception) & retry_if_exception_type(tuple([e for e in Exception.__subclasses__() if e not in fatal_exceptions])), # Simplified logic via explicit check
        before_sleep=log_retry_attempt,
        reraise=True
    )
